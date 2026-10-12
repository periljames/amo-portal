"""External provider WebAuthn step-up using the portal's existing verifier.

The account password or verified TOTP is still required to start registration.
All challenges are short-lived, one-use and tenant RLS controlled.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from webauthn import (
    base64url_to_bytes, generate_authentication_options,
    generate_registration_options, options_to_json,
    verify_authentication_response, verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)
from amodb.database import get_db
from amodb.security import verify_password
from . import external_auth_core as core

router=APIRouter(tags=["External provider passkey MFA"])

class RegistrationStart(BaseModel):
    password: str

class WebAuthnCompletion(BaseModel):
    challenge_id: str = Field(min_length=36,max_length=36)
    credential: dict[str,Any]
    nickname: str | None = Field(default=None,max_length=80)

def _rp(request:Request):
    host=(request.url.hostname or "").lower()
    origin=f"{request.url.scheme}://{request.url.netloc}"
    production=core.SECURE
    rp=(os.getenv("EXTERNAL_WEBAUTHN_RP_ID") or "").lower()
    allowed={x.strip().rstrip("/") for x in os.getenv("EXTERNAL_WEBAUTHN_ORIGINS","").split(",") if x.strip()}
    if production and (not rp or not allowed):
        raise HTTPException(503,"External WebAuthn RP and origins must be configured")
    if not rp:rp=host
    if not allowed:allowed={origin}
    if origin not in allowed or not rp:
        raise HTTPException(403,"Passkey origin not authorized")
    if request.url.scheme!="https" and host not in {"localhost","127.0.0.1","::1"}:
        raise HTTPException(403,"Passkey ceremonies require HTTPS")
    return rp,origin

def _b64(data:bytes):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def _decode(data:str):
    return base64.urlsafe_b64decode(data+"="*((-len(data))%4))

def _credentials(db,person:str):
    return core.many("""SELECT id,credential_id,public_key,sign_count,nickname,created_at,last_used_at
        FROM external_passkey_credentials WHERE identity_id=:person AND is_active=true
        ORDER BY created_at DESC""",db,person=person)

def _challenge(db,session,kind,raw):
    cid=core.new_id()
    core.run("""INSERT INTO external_passkey_challenges
        (id,amo_id,identity_id,challenge_type,challenge_b64,expires_at)
        VALUES (:id,:amo,:identity,:kind,:challenge,:expires)""",db,id=cid,
        amo=session["amo_id"],identity=session["identity_id"],kind=kind,
        challenge=_b64(raw),expires=core.now()+timedelta(minutes=5))
    return cid

def _redeem(db,session,cid,kind):
    row=core.one("""SELECT * FROM external_passkey_challenges WHERE id=:id
        AND amo_id=:amo AND identity_id=:identity AND challenge_type=:kind FOR UPDATE""",
        db,id=cid,amo=session["amo_id"],identity=session["identity_id"],kind=kind)
    if not row or row["consumed_at"] or core.aware(row["expires_at"])<=core.now():
        raise HTTPException(400,"Passkey challenge invalid or expired")
    core.run("""UPDATE external_passkey_challenges SET consumed_at=:at WHERE id=:id""",
             db,id=cid,at=core.now())
    return _decode(row["challenge_b64"])

@router.post("/passkeys/register/options")
def register_options(payload:RegistrationStart,request:Request,db:Session=Depends(get_db)):
    session=core.active_session(db,request,required="profile.read",write=True)
    core.auth_limit(request,str(session["identity_id"]),"passkey-register")
    credential=core.one("SELECT password_hash FROM external_credentials WHERE identity_id=:id",
                        db,id=session["identity_id"])
    if not credential or not verify_password(payload.password,credential["password_hash"]):
        raise HTTPException(401,"Password reauthentication required")
    existing_totp=core.one("""SELECT totp_confirmed_at FROM external_credentials
        WHERE identity_id=:id""",db,id=session["identity_id"])
    if existing_totp and existing_totp["totp_confirmed_at"]:
        core.require_recent_mfa(db,session)
    rp,_=_rp(request)
    ident=core.one("SELECT email,display_name FROM external_identities WHERE id=:id",
                   db,id=session["identity_id"])
    challenge=secrets.token_bytes(32)
    options=generate_registration_options(
        rp_id=rp,rp_name="AMO Portal External Provider",
        user_id=f"vendor:{session['identity_id']}".encode(),
        user_name=ident["email"],user_display_name=ident["display_name"],
        challenge=challenge,
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=bytes(c["credential_id"])) for c in _credentials(db,session["identity_id"])],
    )
    cid=_challenge(db,session,"REGISTER",challenge)
    db.commit()
    return {"challenge_id":cid,"options":json.loads(options_to_json(options))}

@router.post("/passkeys/register/verify",status_code=201)
def register_verify(payload:WebAuthnCompletion,request:Request,db:Session=Depends(get_db)):
    session=core.active_session(db,request,required="profile.read",write=True)
    rp,origin=_rp(request)
    challenge=_redeem(db,session,payload.challenge_id,"REGISTER")
    try:
        proof=verify_registration_response(
            credential=payload.credential,expected_challenge=challenge,
            expected_rp_id=rp,expected_origin=origin,require_user_verification=True,
        )
    except Exception as exc:
        db.commit()
        raise HTTPException(400,"Passkey registration proof invalid") from exc
    if core.one("SELECT id FROM external_passkey_credentials WHERE credential_id=:id",
                db,id=proof.credential_id):
        db.commit();raise HTTPException(409,"Credential already enrolled")
    core.run("""INSERT INTO external_passkey_credentials
        (id,identity_id,credential_id,public_key,sign_count,nickname)
        VALUES(:id,:person,:credential,:key,:counter,:name)""",
        db,id=core.new_id(),person=session["identity_id"],credential=proof.credential_id,
        key=proof.credential_public_key,counter=int(proof.sign_count or 0),
        name=(payload.nickname or "External provider passkey")[:80])
    core.event(db,amo=session["amo_id"],identity=session["identity_id"],grant=session["grant_id"],
               action="PASSKEY_REGISTERED",actor_identity=session["identity_id"])
    db.commit()
    return {"status":"PASSKEY_REGISTERED"}

@router.post("/passkeys/challenge/options")
def assertion_options(request:Request,db:Session=Depends(get_db)):
    session=core.active_session(db,request,required="profile.read",write=True)
    core.auth_limit(request,str(session["identity_id"]),"passkey-assert")
    credentials=_credentials(db,session["identity_id"])
    if not credentials:raise HTTPException(409,"No passkey registered")
    rp,_=_rp(request)
    challenge=secrets.token_bytes(32)
    options=generate_authentication_options(
        rp_id=rp,challenge=challenge,
        allow_credentials=[PublicKeyCredentialDescriptor(id=bytes(c["credential_id"])) for c in credentials],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    cid=_challenge(db,session,"ASSERT",challenge)
    db.commit()
    return {"challenge_id":cid,"options":json.loads(options_to_json(options))}

@router.post("/passkeys/challenge/verify")
def assertion_verify(payload:WebAuthnCompletion,request:Request,db:Session=Depends(get_db)):
    session=core.active_session(db,request,required="profile.read",write=True)
    rp,origin=_rp(request)
    challenge=_redeem(db,session,payload.challenge_id,"ASSERT")
    try:
        cred_id=base64url_to_bytes(str(payload.credential.get("id","")))
    except Exception:
        db.commit();raise HTTPException(400,"Invalid credential ID")
    cred=core.one("""SELECT * FROM external_passkey_credentials
        WHERE identity_id=:person AND credential_id=:id AND is_active=true FOR UPDATE""",
        db,person=session["identity_id"],id=cred_id)
    if not cred:
        db.commit();raise HTTPException(403,"Passkey does not belong to this external identity")
    try:
        proof=verify_authentication_response(
            credential=payload.credential,expected_challenge=challenge,
            expected_rp_id=rp,expected_origin=origin,
            credential_public_key=bytes(cred["public_key"]),
            credential_current_sign_count=int(cred["sign_count"] or 0),
            require_user_verification=True,
        )
    except Exception as exc:
        db.commit()
        raise HTTPException(400,"Passkey assertion failed") from exc
    core.run("""UPDATE external_passkey_credentials SET sign_count=:count,last_used_at=:at
        WHERE id=:id""",db,count=int(proof.new_sign_count or 0),at=core.now(),id=cred["id"])
    core.run("UPDATE external_sessions SET mfa_verified_at=:at WHERE id=:id",
             db,at=core.now(),id=session["id"])
    core.event(db,amo=session["amo_id"],identity=session["identity_id"],grant=session["grant_id"],
               action="PASSKEY_VERIFIED",actor_identity=session["identity_id"])
    db.commit()
    return {"status":"MFA_VERIFIED","method":"PASSKEY"}

@router.get("/passkeys")
def list_passkeys(request:Request,db:Session=Depends(get_db)):
    session=core.active_session(db,request,required="profile.read")
    return {"items":[{"id":str(x["id"]),"nickname":x["nickname"],
        "created_at":x["created_at"],"last_used_at":x["last_used_at"]}
        for x in _credentials(db,session["identity_id"])]}
