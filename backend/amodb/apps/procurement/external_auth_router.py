"""Persistent vendor authentication and Quality-controlled tenant privileges.

No endpoint grants internal User, certifying-staff or QMS approval authority.
All provider business endpoints must use require_provider(), not staff JWT auth.
"""
from __future__ import annotations

import base64
import hmac
import json
import os
import secrets
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user, get_password_hash, verify_password
from amodb.apps.accounts import models as accounts
from amodb.apps.accounts.tenant_authority import is_tenant_admin
from amodb.apps.notifications import service as notifications
from . import service
from . import external_auth_core as core
from .external_passkey_router import router as provider_passkey_router

router=APIRouter(prefix="/api/external-provider",tags=["External provider authentication"])
router.include_router(provider_passkey_router)
quality_router=APIRouter(prefix="/api/maintenance/{amo_code}/quality/external-accounts",
                        tags=["Quality external account governance"])

class Login(BaseModel):
    amo_slug: str = Field(min_length=2,max_length=64)
    email: EmailStr
    password: str
    vendor_key: str | None = Field(default=None,max_length=64)
    totp_code: str | None = Field(default=None,pattern=r"^\d{6}$")

class AccountAction(BaseModel):
    code: str = Field(min_length=20,max_length=256)
    password: str | None = Field(default=None,min_length=8,max_length=128)
    display_name: str | None = Field(default=None,max_length=255)

class RecoveryRequest(BaseModel):
    amo_slug: str
    email: EmailStr

class PasswordReset(BaseModel):
    code: str = Field(min_length=20,max_length=256)
    password: str = Field(min_length=8,max_length=128)

class PasswordChange(BaseModel):
    current_password: str
    new_password: str
    totp_code: str | None = None

class Invitation(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2,max_length=255)
    role_code: str = "READ_ONLY"
    capabilities: list[str] | None = None
    object_scope: dict[str,list[str]] = Field(default_factory=dict)

class QualityInvite(Invitation):
    supplier_id: int
    organization_id: str | None = None

class Decision(BaseModel):
    state: Literal["ACTIVE","SUSPENDED","REVOKED","PENDING"]
    reason: str = Field(min_length=8,max_length=2000)
    restrict_new_work: bool = False

class GrantUpdate(BaseModel):
    role_code: str
    capabilities: list[str]
    object_scope: dict[str,list[str]] = Field(default_factory=dict)
    reason: str = Field(min_length=8,max_length=2000)
    version: int = Field(ge=1)

class TotpCode(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")

class SensitivePassword(BaseModel):
    password: str

def _authorized_quality(db,amo_code,user):
    if not is_tenant_admin(user) and user.role not in {accounts.AccountRole.QUALITY_MANAGER, accounts.AccountRole.QUALITY_OFFICER}:
        raise HTTPException(403,"Quality account-control role required")
    tenant=service.resolve_tenant_amo_id(db,amo_code=amo_code,current_user=user)
    core.context(db,tenant,str(user.id))
    return tenant

def _quality_manager(user):
    if not is_tenant_admin(user) and user.role!=accounts.AccountRole.QUALITY_MANAGER:
        raise HTTPException(403,"Quality Manager approval required")

def _caps(role,proposed=None,bound=None):
    if role not in core.ROLE_CAPS and role!="CUSTOM":
        raise HTTPException(422,"Unknown external role")
    allowed=set(core.ROLE_CAPS.get(role,core.CAPABILITIES))
    if role=="CUSTOM" and not proposed:
        raise HTTPException(422,"Custom external profiles require an explicit nonempty capability subset")
    requested=set(proposed if proposed is not None else allowed)
    if requested-allowed or requested-core.CAPABILITIES or (bound is not None and requested-set(bound)):
        raise HTTPException(403,"External capability exceeds authorized profile")
    return sorted(requested)

DELEGABLE_OBJECT_SCOPES=frozenset({"contracts","documents","assignments","rfqs","purchase_orders"})
MANAGER_CONTROLLED_SCOPES=frozenset({"contracted_work"})
ALL_OBJECT_SCOPES=DELEGABLE_OBJECT_SCOPES|MANAGER_CONTROLLED_SCOPES

def _scope(value):
    if not isinstance(value,dict) or set(value)-ALL_OBJECT_SCOPES:
        raise HTTPException(422,"Unknown object scope type")
    if any(not isinstance(v,list) or any(
        not isinstance(x,str) or not x.strip() or len(x)>128 for x in v
    ) for v in value.values()):
        raise HTTPException(422,"Invalid provider object scope")
    if sum(len(v) for v in value.values())>500:
        raise HTTPException(422,"Provider object scope exceeds record limit")
    return value


def _check_provider_delegation(scopes, parent_scope):
    # All delegable categories must be subsets of the current membership's
    # grant. Contracted maintenance is assigned ONLY by a Maintenance Manager.
    if scopes.get("contracted_work"):
        raise HTTPException(403,"Only the responsible Maintenance Manager may assign contracted work")
    for key in DELEGABLE_OBJECT_SCOPES:
        if set(scopes.get(key,[]))-set(parent_scope.get(key,[])):
            raise HTTPException(403,"Cannot delegate an object outside the administrator's assigned scope")


def _merge_manager_scopes(proposed, existing):
    # Full-object Quality UI submissions must preserve separately authorized
    # maintenance work IDs, including across unrelated role/capability edits.
    merged=dict(_scope(proposed))
    existing=_scope(existing)
    for key in MANAGER_CONTROLLED_SCOPES:
        if key in merged and set(merged[key])!=set(existing.get(key,[])):
            raise HTTPException(403,"Contracted-work assignments are controlled by the responsible Maintenance Manager")
        if key in existing:
            merged[key]=existing[key]
    return merged

def _send(db,amo,email,code,kind):
    # Invitation issuance commits before delivery; restore SET LOCAL tenant
    # context in the new transaction so notification preferences and log RLS
    # continue to resolve against the right AMO.
    core.context(db,amo)
    # Token travels only in the email body, not a URL, log, API response or telemetry.
    # The existing essential account-message template is reused.
    msg=f"AMO Portal external account {kind} code: {code}. Enter this code in the vendor portal. The code expires and can be used once."
    outcome=notifications.send_email(
        template_key="password-reset", recipient=email,
        subject=f"AMO Portal external provider {kind}",
        context={"message":msg,"action_url":None},
        audit_context={"purpose":"external-provider-account", "event":kind},
        correlation_id=f"external-account:{core.new_id()}",
        critical=False,email_class="ESSENTIAL",
        recipient_user_id=None,amo_id=amo,db=db,
    )
    return str(getattr(outcome.status,"value",outcome.status))

def _invite(db,*,amo,supplier_id,inviter,req,organization_id=None,provider_id=None,
            cap_limit=None,caller_scope=None,internal=True):
    supplier=core.one("""SELECT id, legal_name, supplier_code FROM procurement_suppliers
          WHERE amo_id=:amo AND id=:supplier""",db,amo=amo,supplier=supplier_id)
    if not supplier:
        raise HTTPException(404,"Provider supplier not found")
    # Organization is global, tenant-provider link is explicit, never inferred
    # from an unverified legal-name match.
    link=core.one("""SELECT * FROM external_tenant_providers WHERE amo_id=:amo
                     AND supplier_id=:supplier""",db,amo=amo,supplier=supplier_id)
    if link:
        if organization_id and organization_id!=link["organization_id"]:
            raise HTTPException(409,"Existing supplier is linked to another organization")
        org_id=link["organization_id"]; tenant_provider_id=link["id"]
    else:
        if not internal:
            raise HTTPException(403,"Only Quality may register an organization")
        org_id=organization_id or core.new_id()
        if organization_id:
            if not core.one("SELECT id FROM external_organizations WHERE id=:id",db,id=org_id):
                raise HTTPException(404,"External organization not found")
        else:
            core.run("INSERT INTO external_organizations(id,legal_name) VALUES (:id,:name)",
                     db,id=org_id,name=supplier["legal_name"])
        tenant_provider_id=core.new_id()
        core.run("""INSERT INTO external_tenant_providers
            (id,amo_id,supplier_id,organization_id,portal_state)
            VALUES (:id,:amo,:supplier,:org,'PENDING')""",db,
            id=tenant_provider_id,amo=amo,supplier=supplier_id,org=org_id)
    email=str(req.email).lower()
    identity=core.one("SELECT * FROM external_identities WHERE email=:email FOR UPDATE",db,email=email)
    if identity:
        if identity["status"]=="REVOKED":
            raise HTTPException(409,"Account requires Quality recovery review")
        identity_id=identity["id"]
    else:
        identity_id=core.new_id()
        core.run("""INSERT INTO external_identities(id,email,display_name,status)
            VALUES(:id,:email,:name,'INVITED')""",db,id=identity_id,email=email,name=req.name.strip())
        core.run("INSERT INTO external_credentials(identity_id) VALUES(:id)",db,id=identity_id)
    membership=core.one("""SELECT * FROM external_organization_memberships
                            WHERE identity_id=:identity AND organization_id=:org FOR UPDATE""",
                        db,identity=identity_id,org=org_id)
    if membership and membership["status"]=="ACTIVE":
        member_id=membership["id"]
    elif membership:
        member_id=membership["id"]
    else:
        member_id=core.new_id()
        core.run("""INSERT INTO external_organization_memberships
          (id,organization_id,identity_id,role_code,status)
          VALUES(:id,:org,:identity,:role,'INVITED')""",
          db,id=member_id,org=org_id,identity=identity_id,role=req.role_code)
    caps=_caps(req.role_code,req.capabilities,cap_limit)
    scopes=_scope(req.object_scope)
    if not internal:
        # A Provider Administrator can delegate only the exact records granted
        # to their own tenant/provider membership, never new contract or DMS IDs.
        parent_scope=_scope(caller_scope or {})
        _check_provider_delegation(scopes,parent_scope)
    existing=core.one("""SELECT id FROM external_tenant_grants WHERE amo_id=:amo
                         AND tenant_provider_id=:provider AND identity_id=:identity""",
                      db,amo=amo,provider=tenant_provider_id,identity=identity_id)
    if existing:
        raise HTTPException(409,"This provider user already has a tenant grant; use controlled grant updates")
    grant=core.new_id()
    core.run("""INSERT INTO external_tenant_grants
        (id,amo_id,tenant_provider_id,membership_id,identity_id,role_code,
         capabilities_json,object_scope_json,status)
        VALUES(:id,:amo,:provider,:member,:identity,:role,CAST(:caps AS JSON),CAST(:scope AS JSON),'PENDING')""",
        db,id=grant,amo=amo,provider=tenant_provider_id,member=member_id,identity=identity_id,
        role=req.role_code,caps=json.dumps(caps),scope=json.dumps(scopes))
    raw=core.token(db,tenant_id=amo,grant_id=grant,identity_id=identity_id,kind="INVITE",hours=48)
    core.event(db,amo=amo,identity=identity_id,grant=grant,action="INVITED",
               actor_user=inviter if internal else None,actor_identity=None if internal else inviter)
    db.commit()
    delivery=_send(db,amo,email,raw,"invitation")
    db.commit()
    return {"id":grant,"status":"PENDING","delivery_status":delivery,
            "organization_id":org_id,"supplier_id":supplier_id}

@quality_router.post("/invitations",status_code=201)
def quality_invite(amo_code:str,payload:QualityInvite, db:Session=Depends(get_db),
                   user:accounts.User=Depends(get_current_active_user)):
    amo=_authorized_quality(db,amo_code,user)
    return _invite(db,amo=amo,supplier_id=payload.supplier_id,inviter=str(user.id),
                   req=payload,organization_id=payload.organization_id)

@router.post("/invitations/accept")
def accept_invitation(payload:AccountAction,request:Request,db:Session=Depends(get_db)):
    core.auth_limit(request,core.digest(payload.code),"invitation-accept")
    t=core.redeem_token(db,payload.code,"INVITE")
    person=core.one("SELECT * FROM external_identities WHERE id=:id FOR UPDATE",db,id=t["identity_id"])
    if not person or person["status"] in {"LOCKED","REVOKED"}:
        raise HTTPException(409,"Identity is locked or revoked; contact Quality for controlled recovery")
    cred=core.one("SELECT * FROM external_credentials WHERE identity_id=:id FOR UPDATE",db,id=t["identity_id"])
    if not cred["password_hash"]:
        if not payload.password:
            raise HTTPException(422,"Set your account password to accept the invitation")
        core.password_is_valid(payload.password)
        core.run("""UPDATE external_credentials SET password_hash=:hash,
                    password_version=password_version+1,changed_at=:at WHERE identity_id=:id""",
                 db,hash=get_password_hash(payload.password),at=core.now(),id=t["identity_id"])
    core.run("""UPDATE external_identities SET status='ACTIVE',verified_at=:at,
                updated_at=:at WHERE id=:id AND status!='REVOKED'""",
             db,at=core.now(),id=t["identity_id"])
    core.run("""UPDATE external_organization_memberships SET status='ACTIVE',joined_at=COALESCE(joined_at,:at)
      WHERE id=(SELECT membership_id FROM external_tenant_grants WHERE id=:grant)
      AND status='INVITED'""",db,at=core.now(),grant=t["grant_id"])
    core.event(db,amo=t["amo_id"],identity=t["identity_id"],grant=t["grant_id"],action="EMAIL_VERIFIED")
    db.commit()
    return {"status":"VERIFIED","account_activation":"AWAITING_TENANT_APPROVAL"}

@router.post("/login")
def login(payload:Login,request:Request,response:Response,db:Session=Depends(get_db)):
    email=str(payload.email).lower()
    core.auth_limit(request,email,"login")
    amo=core.tenant(db,payload.amo_slug)
    core.context(db,amo)
    identity=core.one("""SELECT i.*,c.password_hash,c.totp_secret_encrypted,c.totp_confirmed_at,
                      c.failed_attempts,c.locked_until FROM external_identities i
                      JOIN external_credentials c ON c.identity_id=i.id WHERE i.email=:email""",db,email=email)
    # Lookup includes tenant-specific supplier code when provided; never use
    # vendor_key without email/password and tenant.
    candidates=core.many("""SELECT g.id grant_id,g.status,p.portal_state,p.supplier_id,s.supplier_code,
          p.restrict_new_work,m.status member_status
          FROM external_tenant_grants g
          JOIN external_tenant_providers p ON p.id=g.tenant_provider_id AND p.amo_id=g.amo_id
          JOIN procurement_suppliers s ON s.id=p.supplier_id AND s.amo_id=p.amo_id
          JOIN external_organization_memberships m ON m.id=g.membership_id AND m.identity_id=g.identity_id
          WHERE g.amo_id=:amo AND g.identity_id=:identity""",db,amo=amo,identity=identity["id"] if identity else "")
    active=[g for g in candidates if g["status"]=="ACTIVE" and g["portal_state"] in {"ACTIVE","SUSPENDED"}
            and g["member_status"]=="ACTIVE"
            and (not payload.vendor_key or hmac.compare_digest(str(g["supplier_code"]).casefold(),payload.vendor_key.casefold()))]
    authenticated=bool(identity and identity["password_hash"] and verify_password(payload.password,identity["password_hash"]))
    if not authenticated or not active:
        if identity and not authenticated:
            attempts=int(identity["failed_attempts"] or 0)+1
            core.run("""UPDATE external_credentials SET failed_attempts=:attempts,
                locked_until=:until WHERE identity_id=:id""",db,attempts=attempts,
                until=core.now()+timedelta(minutes=30) if attempts>=5 else None,id=identity["id"])
        core.event(db,amo=amo,identity=identity["id"] if identity else None,grant=None,action="LOGIN_REJECTED")
        db.commit()
        raise HTTPException(401,"Invalid credentials or access not enabled")
    if identity["status"]!="ACTIVE" or not identity["verified_at"] or (
        identity["locked_until"] and core.aware(identity["locked_until"])>core.now()
    ):
        raise HTTPException(403,"External identity locked or not verified")
    if identity["totp_confirmed_at"]:
        if not payload.totp_code or not core.totp_valid(identity["totp_secret_encrypted"],payload.totp_code):
            raise HTTPException(401,"MFA verification required")
    if len(active)>1:
        raise HTTPException(409,"Multiple provider accounts found. Specify the vendor key.")
    grant=active[0]
    # Switching an authenticated browser to another external organization
    # must revoke its previous cookie session; do not leave both principals
    # active merely because the browser replaces its HttpOnly cookie.
    previous=request.cookies.get(core.COOKIE)
    if previous:
        previous_tenant,sep,_=previous.partition(".")
        if sep and len(previous_tenant)==36:
            core.context(db,previous_tenant)
            core.run("""UPDATE external_sessions SET revoked_at=:at
                WHERE amo_id=:amo AND session_hash=:hash AND revoked_at IS NULL""",
                db,at=core.now(),amo=previous_tenant,hash=core.digest(previous))
            core.context(db,amo,identity["id"])
    csrf=core.issue_session(db,response,amo=amo,identity=identity["id"],grant=grant["grant_id"],
                            request=request,mfa=bool(identity["totp_confirmed_at"]))
    core.run("UPDATE external_credentials SET failed_attempts=0,locked_until=NULL WHERE identity_id=:id",
             db,id=identity["id"])
    db.commit()
    return {"status":"AUTHENTICATED","csrf":csrf,"expires_in":core.MAX_AGE}

@router.get("/session")
def session(request:Request,db:Session=Depends(get_db)):
    s=core.active_session(db,request)
    # On page refresh, rotate the CSRF secret. Browser never reads HttpOnly auth.
    csrf=secrets.token_urlsafe(32)
    core.run("UPDATE external_sessions SET csrf_hash=:hash,last_seen_at=:now WHERE id=:id",
             db,hash=core.digest(csrf),now=core.now(),id=s["id"])
    db.commit()
    return {"csrf":csrf,"identity_id":s["identity_id"],"amo_id":s["amo_id"],
        "supplier_id":s["supplier_id"],"role":s["role_code"],"capabilities":s["capabilities_json"],
        "object_scope":s["object_scope_json"],"restricted":s["restrict_new_work"],
        "portal_state":s["portal_state"],"mfa_verified":bool(s["mfa_verified_at"])}

@router.post("/session/rotate")
def rotate(request:Request,response:Response,db:Session=Depends(get_db)):
    s=core.active_session(db,request,write=True)
    core.run("UPDATE external_sessions SET revoked_at=:at WHERE id=:id",db,at=core.now(),id=s["id"])
    csrf=core.issue_session(db,response,amo=s["amo_id"],identity=s["identity_id"],
                            grant=s["grant_id"],request=request,mfa=bool(s["mfa_verified_at"]))
    core.event(db,amo=s["amo_id"],identity=s["identity_id"],grant=s["grant_id"],action="SESSION_ROTATED",actor_identity=s["identity_id"])
    db.commit()
    return {"csrf":csrf,"expires_in":core.MAX_AGE}

@router.post("/logout")
def logout(request:Request,response:Response,db:Session=Depends(get_db)):
    try:
        s=core.active_session(db,request,write=True)
    except HTTPException as exc:
        # A revoked/expired cookie has no authority, but its holder must be
        # able to clear it even after Quality has terminated access.
        if exc.status_code not in {401,403}:
            raise
        core.cookie(response,None)
        return {"status":"SIGNED_OUT"}
    core.run("UPDATE external_sessions SET revoked_at=:at WHERE id=:id",db,at=core.now(),id=s["id"])
    core.event(db,amo=s["amo_id"],identity=s["identity_id"],grant=s["grant_id"],action="LOGOUT",actor_identity=s["identity_id"])
    db.commit();core.cookie(response,None)
    return {"status":"SIGNED_OUT"}

@router.get("/sessions")
def sessions(request:Request,db:Session=Depends(get_db)):
    s=core.active_session(db,request,required="sessions.manage")
    items=core.many("""SELECT id,created_at,last_seen_at,expires_at,revoked_at,
      ip_hash,user_agent_hash FROM external_sessions
      WHERE amo_id=:amo AND identity_id=:id ORDER BY created_at DESC LIMIT 100""",
      db,amo=s["amo_id"],id=s["identity_id"])
    return {"current_session_id":s["id"],"items":items}

@router.post("/sessions/revoke/{session_id}")
def revoke_session(session_id:str,request:Request,response:Response,db:Session=Depends(get_db)):
    s=core.active_session(db,request,required="sessions.manage",write=True)
    result=core.run("""UPDATE external_sessions SET revoked_at=:at
      WHERE amo_id=:amo AND identity_id=:person AND id=:target AND revoked_at IS NULL""",
      db,at=core.now(),amo=s["amo_id"],person=s["identity_id"],target=session_id)
    if not result.rowcount:
        raise HTTPException(404,"Session not found")
    core.event(db,amo=s["amo_id"],identity=s["identity_id"],grant=s["grant_id"],action="SESSION_REVOKED",actor_identity=s["identity_id"])
    db.commit()
    if s["id"]==session_id:core.cookie(response,None)
    return {"status":"REVOKED"}

@router.post("/logout-all")
def logout_all(request:Request,response:Response,db:Session=Depends(get_db)):
    s=core.active_session(db,request,required="sessions.manage",write=True)
    core.revoke_identity_sessions(db,s["identity_id"])
    core.context(db,s["amo_id"],s["identity_id"])
    core.event(db,amo=s["amo_id"],identity=s["identity_id"],grant=s["grant_id"],action="ALL_SESSIONS_REVOKED",actor_identity=s["identity_id"])
    db.commit();core.cookie(response,None)
    return {"status":"ALL_REVOKED"}

@router.post("/password/change")
def change_password(payload:PasswordChange,request:Request,response:Response,db:Session=Depends(get_db)):
    s=core.active_session(db,request,write=True)
    core.auth_limit(request,str(s["identity_id"]),"password-change")
    credential=core.one("SELECT * FROM external_credentials WHERE identity_id=:id FOR UPDATE",db,id=s["identity_id"])
    if not verify_password(payload.current_password,credential["password_hash"]):
        raise HTTPException(401,"Invalid current credentials")
    enrolled_passkey=core.one("""SELECT id FROM external_passkey_credentials
        WHERE identity_id=:identity AND is_active=true LIMIT 1""",db,identity=s["identity_id"])
    if credential["totp_confirmed_at"]:
        if not payload.totp_code or not core.totp_valid(credential["totp_secret_encrypted"],payload.totp_code):
            raise HTTPException(403,"Verified second factor required")
    elif enrolled_passkey:
        core.require_recent_mfa(db,s)
    core.password_is_valid(payload.new_password)
    core.run("""UPDATE external_credentials SET password_hash=:hash,
        password_version=password_version+1,changed_at=:at WHERE identity_id=:id""",
        db,hash=get_password_hash(payload.new_password),at=core.now(),id=s["identity_id"])
    core.revoke_identity_sessions(db,s["identity_id"])
    core.consume_other_reset_tokens(db,s["identity_id"])
    core.context(db,s["amo_id"],s["identity_id"])
    core.event(db,amo=s["amo_id"],identity=s["identity_id"],grant=s["grant_id"],action="PASSWORD_CHANGED",actor_identity=s["identity_id"])
    db.commit();core.cookie(response,None)
    return {"status":"PASSWORD_CHANGED_RELOGIN"}

@router.post("/password/forgot",status_code=202)
def forgot(payload:RecoveryRequest,request:Request,db:Session=Depends(get_db)):
    core.auth_limit(request,str(payload.email),"reset")
    msg={"message":"If the account exists, a recovery code will be sent."}
    try:amo=core.tenant(db,payload.amo_slug)
    except HTTPException:return msg
    core.context(db,amo)
    grant=core.one("""SELECT g.id,g.identity_id,i.email FROM external_tenant_grants g
        JOIN external_identities i ON i.id=g.identity_id
        WHERE g.amo_id=:amo AND i.email=:email AND i.status='ACTIVE'
        AND g.status='ACTIVE' LIMIT 1""",db,amo=amo,email=str(payload.email).lower())
    if grant:
        code=core.token(db,tenant_id=amo,grant_id=grant["id"],
                        identity_id=grant["identity_id"],kind="RESET",hours=1)
        core.event(db,amo=amo,identity=grant["identity_id"],grant=grant["id"],action="RESET_REQUESTED")
        db.commit();_send(db,amo,grant["email"],code,"password recovery");db.commit()
    return msg

@router.post("/password/reset")
def reset(payload:PasswordReset,request:Request,response:Response,db:Session=Depends(get_db)):
    core.auth_limit(request,core.digest(payload.code),"password-reset")
    core.password_is_valid(payload.password)
    t=core.redeem_token(db,payload.code,"RESET")
    core.run("""UPDATE external_credentials SET password_hash=:hash,password_version=password_version+1,
        failed_attempts=0,locked_until=NULL,changed_at=:at WHERE identity_id=:identity""",
        db,hash=get_password_hash(payload.password),at=core.now(),identity=t["identity_id"])
    # A reset never removes the verified TOTP requirement.
    core.revoke_identity_sessions(db,t["identity_id"])
    core.consume_other_reset_tokens(db,t["identity_id"])
    core.context(db,t["amo_id"],t["identity_id"])
    core.event(db,amo=t["amo_id"],identity=t["identity_id"],grant=t["grant_id"],action="PASSWORD_RESET")
    db.commit();core.cookie(response,None)
    return {"status":"PASSWORD_RESET_RELOGIN"}

@router.post("/mfa/enroll")
def mfa_enroll(payload:SensitivePassword,request:Request,db:Session=Depends(get_db)):
    s=core.active_session(db,request,write=True)
    core.auth_limit(request,str(s["identity_id"]),"mfa-enrollment")
    cred=core.one("SELECT * FROM external_credentials WHERE identity_id=:id FOR UPDATE",db,id=s["identity_id"])
    if not verify_password(payload.password,cred["password_hash"]):
        raise HTTPException(401,"Reauthentication required")
    if cred["totp_confirmed_at"]:
        raise HTTPException(409,"MFA already enrolled; Quality-assisted recovery required")
    # A signed-in identity that already owns a passkey must step up before
    # adding a new authentication method, preventing credential takeover.
    enrolled_passkey=core.one("""SELECT id FROM external_passkey_credentials
        WHERE identity_id=:id AND is_active=true LIMIT 1""",db,id=s["identity_id"])
    if enrolled_passkey:
        core.require_recent_mfa(db,s)
    raw=base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    encrypted=core.secret_box().encrypt(raw.encode()).decode()
    core.run("""UPDATE external_credentials SET totp_secret_encrypted=:secret,
        totp_confirmed_at=NULL WHERE identity_id=:id""",db,secret=encrypted,id=s["identity_id"])
    core.event(db,amo=s["amo_id"],identity=s["identity_id"],grant=s["grant_id"],action="MFA_ENROLLMENT_STARTED",actor_identity=s["identity_id"])
    db.commit()
    return {"secret":raw,"method":"TOTP","pending_verification":True}

@router.post("/mfa/verify")
def mfa_verify(payload:TotpCode,request:Request,db:Session=Depends(get_db)):
    s=core.active_session(db,request,write=True)
    core.auth_limit(request,str(s["identity_id"]),"mfa-verify")
    cred=core.one("SELECT * FROM external_credentials WHERE identity_id=:id FOR UPDATE",db,id=s["identity_id"])
    if not cred or not cred["totp_secret_encrypted"] or not core.totp_valid(cred["totp_secret_encrypted"],payload.code):
        raise HTTPException(401,"Invalid verification code")
    core.run("UPDATE external_credentials SET totp_confirmed_at=:at WHERE identity_id=:id",
             db,at=core.now(),id=s["identity_id"])
    core.revoke_identity_sessions(db,s["identity_id"],except_session_id=s["id"])
    core.context(db,s["amo_id"],s["identity_id"])
    core.run("UPDATE external_sessions SET mfa_verified_at=:at WHERE id=:id",db,at=core.now(),id=s["id"])
    core.event(db,amo=s["amo_id"],identity=s["identity_id"],grant=s["grant_id"],action="MFA_VERIFIED",actor_identity=s["identity_id"])
    db.commit()
    return {"status":"MFA_ENABLED"}

@router.get("/members")
def members(request:Request,db:Session=Depends(get_db)):
    s=core.active_session(db,request,required="members.read")
    return {"items":core.many("""SELECT g.id,g.role_code,g.status,g.capabilities_json,
        g.object_scope_json,i.email,i.display_name
        FROM external_tenant_grants g JOIN external_identities i ON i.id=g.identity_id
        WHERE g.amo_id=:amo AND g.tenant_provider_id=:provider ORDER BY i.email""",
        db,amo=s["amo_id"],provider=s["tenant_provider_id"])}

@router.post("/members/invite",status_code=201)
def provider_invite(payload:Invitation,request:Request,db:Session=Depends(get_db)):
    s=core.active_session(db,request,required="members.manage",write=True)
    if s["restrict_new_work"] or s["portal_state"]!="ACTIVE":
        raise HTTPException(403,"Provider is restricted from inviting members")
    core.require_recent_mfa(db,s)
    return _invite(db,amo=s["amo_id"],supplier_id=s["supplier_id"],inviter=s["identity_id"],
        req=payload,organization_id=s["organization_id"],cap_limit=s["capabilities_json"],
        caller_scope=s["object_scope_json"],internal=False)

@quality_router.get("/suppliers")
def eligible_supplier_search(amo_code:str,search:str="",limit:int=30,offset:int=0,
                             db:Session=Depends(get_db),
                             user:accounts.User=Depends(get_current_active_user)):
    """Tenant-scoped canonical supplier selector; never guess numeric vendor IDs."""
    amo=_authorized_quality(db,amo_code,user)
    limit=max(1,min(50,limit))
    offset=max(0,min(10000,offset))
    query=f"%{search.strip().lower()[:100]}%"
    rows=core.many("""SELECT id,supplier_code,legal_name,status,is_active,
          external_import_pending_activation
        FROM procurement_suppliers
        WHERE amo_id=:amo AND (lower(legal_name) LIKE :search_term OR lower(supplier_code) LIKE :search_term)
        ORDER BY legal_name,id LIMIT :limit OFFSET :offset""",
        db,amo=amo,search_term=query,limit=limit,offset=offset)
    return {"items":rows,"limit":limit,"offset":offset,"has_more":len(rows)==limit}

@quality_router.get("")
def quality_list(amo_code:str,db:Session=Depends(get_db),
                 user:accounts.User=Depends(get_current_active_user)):
    amo=_authorized_quality(db,amo_code,user)
    return {"items":core.many("""SELECT g.id grant_id,g.status grant_state,g.role_code,g.capabilities_json,
         g.object_scope_json,g.version,p.id provider_id,p.supplier_id,p.portal_state,
         p.restrict_new_work,s.legal_name,s.supplier_code,i.id identity_id,i.email,i.display_name,
         i.status identity_state,i.verified_at
         FROM external_tenant_grants g
         JOIN external_tenant_providers p ON p.id=g.tenant_provider_id AND p.amo_id=g.amo_id
         JOIN procurement_suppliers s ON s.id=p.supplier_id AND s.amo_id=p.amo_id
         JOIN external_identities i ON i.id=g.identity_id
         WHERE g.amo_id=:amo ORDER BY s.legal_name,i.email LIMIT 500""",db,amo=amo)}

@quality_router.post("/grants/{grant_id}/decision")
def quality_decision(amo_code:str,grant_id:str,payload:Decision,db:Session=Depends(get_db),
                     user:accounts.User=Depends(get_current_active_user)):
    _quality_manager(user);amo=_authorized_quality(db,amo_code,user)
    row=core.one("""SELECT g.*,p.portal_state,i.verified_at,i.status identity_state,
      m.status member_state FROM external_tenant_grants g
      JOIN external_tenant_providers p ON p.id=g.tenant_provider_id AND p.amo_id=g.amo_id
      JOIN external_identities i ON i.id=g.identity_id
      JOIN external_organization_memberships m ON m.id=g.membership_id
      WHERE g.id=:id AND g.amo_id=:amo FOR UPDATE OF g""",db,id=grant_id,amo=amo)
    if not row:raise HTTPException(404,"Grant not found")
    if payload.state=="ACTIVE":
        accepted=core.one("""SELECT id FROM external_identity_tokens WHERE amo_id=:amo
            AND grant_id=:grant AND kind='INVITE' AND used_at IS NOT NULL AND revoked_at IS NULL
            LIMIT 1""",db,amo=amo,grant=grant_id)
        if not row["verified_at"] or row["identity_state"]!="ACTIVE" or row["member_state"]!="ACTIVE" or not accepted:
            raise HTTPException(409,"This exact tenant invitation must be accepted and email verified before activation")
        reverify=core.one("""SELECT id,used_at FROM external_identity_tokens
            WHERE amo_id=:amo AND grant_id=:grant AND kind='VERIFY'
            ORDER BY created_at DESC LIMIT 1""",db,amo=amo,grant=grant_id)
        if reverify and reverify["used_at"] is None:
            raise HTTPException(409,"Complete required identity re-verification before restoring access")
    core.run("""UPDATE external_tenant_grants SET status=:state,
      approved_by_user_id=:actor,approved_at=:at,version=version+1 WHERE id=:id AND amo_id=:amo""",
      db,state=payload.state,actor=str(user.id),at=core.now(),id=grant_id,amo=amo)
    if payload.state in {"REVOKED","SUSPENDED","PENDING"}:
        core.run("""UPDATE external_sessions SET revoked_at=:at
          WHERE amo_id=:amo AND grant_id=:grant AND revoked_at IS NULL""",
          db,at=core.now(),amo=amo,grant=grant_id)
    core.event(db,amo=amo,identity=row["identity_id"],grant=grant_id,action=f"GRANT_{payload.state}",
               actor_user=str(user.id),details={"reason":payload.reason})
    db.commit()
    return {"status":payload.state}

@quality_router.post("/providers/{provider_id}/decision")
def provider_decision(amo_code:str,provider_id:str,payload:Decision,db:Session=Depends(get_db),
                      user:accounts.User=Depends(get_current_active_user)):
    _quality_manager(user);amo=_authorized_quality(db,amo_code,user)
    row=core.one("SELECT * FROM external_tenant_providers WHERE amo_id=:amo AND id=:id FOR UPDATE",
                 db,amo=amo,id=provider_id)
    if not row:raise HTTPException(404,"Provider association not found")
    core.run("""UPDATE external_tenant_providers SET portal_state=:state,restrict_new_work=:restricted
         WHERE id=:id AND amo_id=:amo""",db,state=payload.state,restricted=payload.restrict_new_work,
         id=provider_id,amo=amo)
    if payload.state in {"SUSPENDED","REVOKED","PENDING"}:
        core.run("""UPDATE external_sessions SET revoked_at=:at
         WHERE amo_id=:amo AND grant_id IN (
           SELECT id FROM external_tenant_grants WHERE tenant_provider_id=:provider)
         AND revoked_at IS NULL""",db,at=core.now(),amo=amo,provider=provider_id)
    core.event(db,amo=amo,identity=None,grant=None,action=f"PROVIDER_PORTAL_{payload.state}",
               actor_user=str(user.id),details={"provider_id":provider_id,"reason":payload.reason})
    db.commit()
    return {"portal_state":payload.state,"restricted":payload.restrict_new_work}

@quality_router.patch("/grants/{grant_id}")
def quality_grant_update(amo_code:str,grant_id:str,payload:GrantUpdate,db:Session=Depends(get_db),
                         user:accounts.User=Depends(get_current_active_user)):
    _quality_manager(user);amo=_authorized_quality(db,amo_code,user)
    row=core.one("SELECT * FROM external_tenant_grants WHERE amo_id=:amo AND id=:id FOR UPDATE",db,amo=amo,id=grant_id)
    if not row:raise HTTPException(404,"Grant not found")
    if row["version"]!=payload.version:raise HTTPException(409,"Grant was modified; reload before saving")
    caps=_caps(payload.role_code,payload.capabilities)
    scopes=_merge_manager_scopes(payload.object_scope,row["object_scope_json"] or {})
    core.run("""UPDATE external_tenant_grants SET role_code=:role,capabilities_json=CAST(:caps AS JSON),
      object_scope_json=CAST(:scope AS JSON),version=version+1 WHERE amo_id=:amo AND id=:id""",
      db,amo=amo,id=grant_id,role=payload.role_code,caps=json.dumps(caps),scope=json.dumps(scopes))
    core.run("UPDATE external_sessions SET revoked_at=:at WHERE amo_id=:amo AND grant_id=:id AND revoked_at IS NULL",
             db,at=core.now(),amo=amo,id=grant_id)
    core.event(db,amo=amo,identity=row["identity_id"],grant=grant_id,action="GRANT_RESTRICTED",
               actor_user=str(user.id),details={"reason":payload.reason,"role":payload.role_code,"capabilities":caps})
    db.commit()
    return {"status":"UPDATED","version":payload.version+1}

@quality_router.get("/events")
def quality_events(amo_code:str,db:Session=Depends(get_db),
                   user:accounts.User=Depends(get_current_active_user)):
    amo=_authorized_quality(db,amo_code,user)
    return {"items":core.many("""SELECT e.id,e.event_type,e.details_json,e.occurred_at,
        COALESCE(target.email,'Provider organization') identity_label,
        COALESCE(staff.full_name,origin.email,'System account') actor_label
        FROM external_security_events e
        LEFT JOIN external_identities target ON target.id=e.identity_id
        LEFT JOIN external_identities origin ON origin.id=e.actor_identity_id
        LEFT JOIN users staff ON staff.id=e.actor_user_id AND staff.amo_id=e.amo_id
        WHERE e.amo_id=:amo ORDER BY e.occurred_at DESC,e.id DESC LIMIT 250""",db,amo=amo)}

@quality_router.post("/identities/{identity_id}/lock")
def quality_lock(amo_code:str,identity_id:str,payload:Decision,db:Session=Depends(get_db),
                 user:accounts.User=Depends(get_current_active_user)):
    _quality_manager(user);amo=_authorized_quality(db,amo_code,user)
    member=core.one("""SELECT id FROM external_tenant_grants
          WHERE amo_id=:amo AND identity_id=:identity LIMIT 1""",db,amo=amo,identity=identity_id)
    if not member:raise HTTPException(404,"Identity not granted for this tenant")
    state="LOCKED" if payload.state in {"SUSPENDED","REVOKED"} else "ACTIVE"
    # Tenant Quality may lock this tenant's grants, never another AMO's
    # identity. Global identity access requires platform governance.
    core.run("""UPDATE external_tenant_grants SET status=:state,version=version+1
      WHERE amo_id=:amo AND identity_id=:identity""",
      db,state="SUSPENDED" if state=="LOCKED" else "PENDING",amo=amo,identity=identity_id)
    core.run("""UPDATE external_sessions SET revoked_at=:at WHERE amo_id=:amo
      AND identity_id=:identity AND revoked_at IS NULL""",
      db,at=core.now(),amo=amo,identity=identity_id)
    core.event(db,amo=amo,identity=identity_id,grant=None,action=f"TENANT_IDENTITY_{state}",
               actor_user=str(user.id),details={"reason":payload.reason})
    db.commit()
    return {"tenant_identity_access":state,"restore_requires_grant_review":state=="ACTIVE"}

def require_provider(capability:str):
    """Future provider APIs call this and scope_allows(); never staff OAuth2."""
    def _dependency(request:Request,db:Session=Depends(get_db)):
        return core.active_session(db,request,required=capability,
                                   write=request.method.upper() not in {"GET","HEAD"})
    return _dependency


@router.post("/mfa/challenge")
def challenge_mfa(payload:TotpCode,request:Request,db:Session=Depends(get_db)):
    session=core.active_session(db,request,write=True)
    core.auth_limit(request,str(session["identity_id"]),"mfa-challenge")
    cred=core.one("SELECT totp_secret_encrypted,totp_confirmed_at FROM external_credentials WHERE identity_id=:id",
        db,id=session["identity_id"])
    if not cred or not cred["totp_confirmed_at"] or not core.totp_valid(cred["totp_secret_encrypted"],payload.code):
        raise HTTPException(401,"Second-factor verification failed")
    core.run("UPDATE external_sessions SET mfa_verified_at=:at WHERE id=:id",
        db,at=core.now(),id=session["id"])
    core.event(db,amo=session["amo_id"],identity=session["identity_id"],grant=session["grant_id"],
        action="MFA_REAUTHENTICATED",actor_identity=session["identity_id"])
    db.commit()
    return {"status":"MFA_VERIFIED"}


@quality_router.get("/grants/{grant_id}/sessions")
def quality_sessions(amo_code:str,grant_id:str,db:Session=Depends(get_db),
                     user:accounts.User=Depends(get_current_active_user)):
    amo=_authorized_quality(db,amo_code,user)
    if not core.one("""SELECT id FROM external_tenant_grants WHERE amo_id=:amo
        AND id=:grant""",db,amo=amo,grant=grant_id):
        raise HTTPException(404,"Provider account not found")
    return {"items":core.many("""SELECT id,created_at,last_seen_at,expires_at,revoked_at
       FROM external_sessions WHERE amo_id=:amo AND grant_id=:grant
       ORDER BY created_at DESC LIMIT 100""",db,amo=amo,grant=grant_id)}

@quality_router.post("/grants/{grant_id}/sessions/revoke")
def quality_revoke_sessions(amo_code:str,grant_id:str,payload:Decision,
                            db:Session=Depends(get_db),
                            user:accounts.User=Depends(get_current_active_user)):
    _quality_manager(user);amo=_authorized_quality(db,amo_code,user)
    grant=core.one("""SELECT identity_id FROM external_tenant_grants WHERE
       amo_id=:amo AND id=:grant""",db,amo=amo,grant=grant_id)
    if not grant:raise HTTPException(404,"Provider account not found")
    result=core.run("""UPDATE external_sessions SET revoked_at=:at
       WHERE amo_id=:amo AND grant_id=:grant AND revoked_at IS NULL""",
       db,at=core.now(),amo=amo,grant=grant_id)
    core.event(db,amo=amo,identity=grant["identity_id"],grant=grant_id,
        action="QUALITY_SESSIONS_REVOKED",actor_user=str(user.id),
        details={"reason":payload.reason,"sessions_revoked":result.rowcount})
    db.commit()
    return {"sessions_revoked":result.rowcount}

@quality_router.post("/grants/{grant_id}/resend-invitation")
def resend_invitation(amo_code:str,grant_id:str,db:Session=Depends(get_db),
                      user:accounts.User=Depends(get_current_active_user)):
    amo=_authorized_quality(db,amo_code,user)
    grant=core.one("""SELECT g.*,i.email,i.verified_at FROM external_tenant_grants g
      JOIN external_identities i ON i.id=g.identity_id
      WHERE g.amo_id=:amo AND g.id=:grant FOR UPDATE OF g""",db,amo=amo,grant=grant_id)
    if not grant:raise HTTPException(404,"Invitation grant not found")
    if grant["status"]!="PENDING":
        raise HTTPException(409,"Only pending invitations can be resent")
    accepted=core.one("""SELECT id FROM external_identity_tokens
        WHERE amo_id=:amo AND grant_id=:grant AND kind='INVITE' AND used_at IS NOT NULL AND revoked_at IS NULL
        LIMIT 1""",db,amo=amo,grant=grant_id)
    if accepted:
        raise HTTPException(409,"Invitation already accepted; use controlled account decisions")
    core.run("""UPDATE external_identity_tokens SET revoked_at=:at
      WHERE amo_id=:amo AND grant_id=:grant AND kind='INVITE' AND used_at IS NULL AND revoked_at IS NULL""",
      db,at=core.now(),amo=amo,grant=grant_id)
    raw=core.token(db,tenant_id=amo,grant_id=grant_id,
                   identity_id=grant["identity_id"],kind="INVITE",hours=48)
    core.event(db,amo=amo,identity=grant["identity_id"],grant=grant_id,
               action="INVITATION_RESENT",actor_user=str(user.id))
    db.commit()
    delivery=_send(db,amo,grant["email"],raw,"invitation")
    db.commit()
    return {"status":"PENDING","delivery_status":delivery}

@quality_router.post("/grants/{grant_id}/reverify")
def quality_reverify(amo_code:str,grant_id:str,payload:Decision,db:Session=Depends(get_db),
                     user:accounts.User=Depends(get_current_active_user)):
    _quality_manager(user);amo=_authorized_quality(db,amo_code,user)
    grant=core.one("""SELECT g.id,g.identity_id,i.email FROM external_tenant_grants g
      JOIN external_identities i ON i.id=g.identity_id
      WHERE g.amo_id=:amo AND g.id=:id FOR UPDATE OF g""",db,amo=amo,id=grant_id)
    if not grant:raise HTTPException(404,"Account grant not found")
    core.run("""UPDATE external_tenant_grants SET status='PENDING',version=version+1
       WHERE amo_id=:amo AND id=:id""",db,amo=amo,id=grant_id)
    core.run("""UPDATE external_sessions SET revoked_at=:at WHERE amo_id=:amo
       AND grant_id=:id AND revoked_at IS NULL""",db,at=core.now(),amo=amo,id=grant_id)
    raw=core.token(db,tenant_id=amo,grant_id=grant_id,identity_id=grant["identity_id"],kind="VERIFY",hours=24)
    core.event(db,amo=amo,identity=grant["identity_id"],grant=grant_id,action="REVERIFICATION_REQUIRED",
               actor_user=str(user.id),details={"reason":payload.reason})
    db.commit();delivery=_send(db,amo,grant["email"],raw,"reverification");db.commit()
    return {"status":"REVERIFICATION_REQUIRED","delivery_status":delivery}

@router.post("/verification/confirm")
def verify_again(payload:AccountAction,request:Request,db:Session=Depends(get_db)):
    core.auth_limit(request,core.digest(payload.code),"reverification")
    row=core.redeem_token(db,payload.code,"VERIFY")
    core.run("""UPDATE external_identities SET verified_at=:at,updated_at=:at
        WHERE id=:id AND status='ACTIVE'""",db,at=core.now(),id=row["identity_id"])
    core.event(db,amo=row["amo_id"],identity=row["identity_id"],grant=row["grant_id"],action="IDENTITY_REVERIFIED")
    db.commit()
    return {"status":"REVERIFIED_AWAITING_QUALITY_ACTIVATION"}

@quality_router.post("/identities/{identity_id}/unlock")
def quality_unlock(amo_code:str,identity_id:str,payload:Decision,db:Session=Depends(get_db),
                   user:accounts.User=Depends(get_current_active_user)):
    _quality_manager(user);amo=_authorized_quality(db,amo_code,user)
    if not core.one("""SELECT id FROM external_tenant_grants
        WHERE amo_id=:amo AND identity_id=:id""",db,amo=amo,id=identity_id):
        raise HTTPException(404,"Identity not associated with this tenant")
    # The identity credential is global. Tenant Quality cannot clear a
    # cross-tenant login lock; the person must use verified email recovery.
    linked=[]
    for tenant_id in db.execute(__import__("sqlalchemy").text("SELECT id FROM amos")).scalars().all():
        core.context(db,str(tenant_id),identity_id)
        result=core.one("""SELECT id FROM external_tenant_grants
            WHERE amo_id=:amo AND identity_id=:person LIMIT 1""",
            db,amo=str(tenant_id),person=identity_id)
        if result:linked.append(str(tenant_id))
        if len(linked)>1:break
    core.context(db,amo,str(user.id))
    if len(linked)>1:
        raise HTTPException(409,"Shared identity login lock requires verified account recovery; tenant Quality cannot unlock other AMOs")
    core.run("""UPDATE external_credentials SET failed_attempts=0,locked_until=NULL
        WHERE identity_id=:id""",db,id=identity_id)
    core.event(db,amo=amo,identity=identity_id,grant=None,action="LOGIN_LOCK_CLEARED",
               actor_user=str(user.id),details={"reason":payload.reason})
    db.commit()
    return {"status":"LOGIN_LOCK_CLEARED"}

class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=2,max_length=255)

@router.patch("/profile")
def update_profile(payload:ProfileUpdate,request:Request,db:Session=Depends(get_db)):
    session=core.active_session(db,request,required="profile.read",write=True)
    core.run("""UPDATE external_identities SET display_name=:name,updated_at=:at
        WHERE id=:person AND status='ACTIVE'""",db,name=payload.display_name.strip(),
        at=core.now(),person=session["identity_id"])
    core.event(db,amo=session["amo_id"],identity=session["identity_id"],grant=session["grant_id"],
        action="PROFILE_UPDATED",actor_identity=session["identity_id"])
    db.commit()
    return {"status":"UPDATED","display_name":payload.display_name.strip()}

@router.post("/members/{grant_id}/revoke")
def member_revoke(grant_id:str,request:Request,db:Session=Depends(get_db)):
    session=core.active_session(db,request,required="members.manage",write=True)
    core.require_recent_mfa(db,session)
    row=core.one("""SELECT id,identity_id,role_code,capabilities_json FROM external_tenant_grants
        WHERE amo_id=:amo AND tenant_provider_id=:provider AND id=:target FOR UPDATE""",
        db,amo=session["amo_id"],provider=session["tenant_provider_id"],target=grant_id)
    if not row:raise HTTPException(404,"Member not found for this provider")
    if row["identity_id"]==session["identity_id"]:
        raise HTTPException(409,"Provider administrators cannot revoke their own administrative membership")
    if set(row["capabilities_json"] or [])-set(session["capabilities_json"] or []):
        raise HTTPException(403,"Member has privileges outside your delegated authority")
    core.run("""UPDATE external_tenant_grants SET status='REVOKED',version=version+1
        WHERE amo_id=:amo AND id=:id""",db,amo=session["amo_id"],id=grant_id)
    core.run("""UPDATE external_sessions SET revoked_at=:at
        WHERE amo_id=:amo AND grant_id=:id AND revoked_at IS NULL""",
        db,amo=session["amo_id"],id=grant_id,at=core.now())
    core.event(db,amo=session["amo_id"],identity=row["identity_id"],grant=grant_id,
        action="MEMBERSHIP_ACCESS_REVOKED",actor_identity=session["identity_id"])
    db.commit()
    return {"status":"REVOKED"}

@router.get("/mfa/methods")
def mfa_methods(request:Request,db:Session=Depends(get_db)):
    session=core.active_session(db,request,required="profile.read")
    credential=core.one("""SELECT totp_confirmed_at FROM external_credentials
        WHERE identity_id=:person""",db,person=session["identity_id"])
    registered=core.one("""SELECT count(*) AS total FROM external_passkey_credentials
        WHERE identity_id=:id AND is_active=true""",db,id=session["identity_id"])
    return {"totp_enabled":bool(credential and credential["totp_confirmed_at"]),
            "passkeys_supported":True,
            "registered_passkeys":registered["total"] if registered else 0}
