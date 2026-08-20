from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor, UserVerificationRequirement

from amodb.database import get_db

from .audit_external_access_router import (
    AuditAccessExchange,
    _GUEST_COOKIE,
    _active_grant,
    _append_access_event,
    _public_read_model,
    _utcnow,
)
from .audit_external_session_guard_router import _CANONICAL_GUEST_COOKIE_PATH
from .audit_live_completion_models import QualityAuditWebAuthnChallenge, QualityAuditWebAuthnCredential
from .router import public_router


# ``public_router`` already owns the /quality prefix. Keep this child router
# prefix-free so these handlers are exposed exactly at
# /quality/audit-access/passkey/* rather than /quality/quality/audit-access/*.
router = APIRouter(tags=["Quality / External Audit Passkey"])


class ExternalPasskeyVerify(BaseModel):
    token: str = Field(min_length=32, max_length=2048)
    challenge_id: str = Field(min_length=8, max_length=36)
    credential: dict[str, Any]
    nickname: str | None = Field(default=None, max_length=80)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _options_payload(options: Any) -> dict[str, Any]:
    return json.loads(options_to_json(options))


def _configured_webauthn(request: Request) -> tuple[str, str]:
    host = (request.url.hostname or "").strip().lower()
    origin = f"{request.url.scheme}://{request.url.netloc}".rstrip("/")
    production = os.getenv("APP_ENV", "").strip().lower() in {"prod", "production"}
    rp_id = (os.getenv("QMS_WEBAUTHN_RP_ID") or "").strip().lower()
    origins = [item.strip().rstrip("/") for item in (os.getenv("QMS_WEBAUTHN_EXPECTED_ORIGINS") or "").split(",") if item.strip()]
    if production and (not rp_id or not origins):
        raise HTTPException(status_code=503, detail="QMS WebAuthn is disabled until the RP ID and expected origins are configured.")
    if not rp_id:
        rp_id = host
    if not origins:
        origins = [origin]
    if not rp_id or origin not in origins:
        raise HTTPException(status_code=403, detail="This origin is not authorized for QMS passkey ceremonies.")
    if request.url.scheme != "https" and host not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="QMS passkey ceremonies require a secure HTTPS context.")
    return rp_id, origin


def _ttl_seconds() -> int:
    try:
        value = int(os.getenv("QMS_WEBAUTHN_CHALLENGE_TTL_SECONDS", "300"))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="QMS WebAuthn challenge policy is invalid.") from exc
    if not 60 <= value <= 900:
        raise HTTPException(status_code=503, detail="QMS WebAuthn challenge TTL must be between 60 and 900 seconds.")
    return value


def _passkey_grant(db: Session, token: str):
    grant = _active_grant(db, token)
    participant = grant.participant
    identity = participant.external_identity if participant else None
    if participant is None or identity is None or participant.participant_type != "EXTERNAL_AUDITOR":
        raise HTTPException(status_code=403, detail="Passkey assurance is only available to an assigned external auditor identity.")
    if identity.assurance_level != "PASSKEY":
        raise HTTPException(status_code=409, detail="This external audit identity does not require passkey assurance.")
    return grant, participant, identity


def _credentials(db: Session, grant) -> list[QualityAuditWebAuthnCredential]:
    identity_id = grant.participant.external_identity_id
    return db.query(QualityAuditWebAuthnCredential).filter(
        QualityAuditWebAuthnCredential.amo_id == grant.amo_id,
        QualityAuditWebAuthnCredential.owner_type == "EXTERNAL_IDENTITY",
        QualityAuditWebAuthnCredential.external_identity_id == identity_id,
        QualityAuditWebAuthnCredential.is_active.is_(True),
    ).order_by(QualityAuditWebAuthnCredential.created_at.asc()).all()


def _set_guest_cookie(response: Response, request: Request, token: str, expires_at) -> None:
    max_age = max(1, int((expires_at - _utcnow()).total_seconds()))
    production = os.getenv("APP_ENV", "").strip().lower() in {"prod", "production"}
    response.set_cookie(
        key=_GUEST_COOKIE,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=request.url.scheme == "https" or production,
        samesite="strict",
        path=_CANONICAL_GUEST_COOKIE_PATH,
    )


def _activate_session(db: Session, grant, response: Response, request: Request, token: str, reason: str) -> dict[str, Any]:
    now = _utcnow()
    participant = grant.participant
    grant.last_used_at = now
    if participant.accepted_at is None:
        participant.accepted_at = now
    participant.status = "ACTIVE"
    _append_access_event(db, grant, "EXCHANGED", reason)
    db.commit()
    _set_guest_cookie(response, request, token, grant.expires_at)
    return _public_read_model(db, grant)


def _credential_id(payload: dict[str, Any]) -> bytes:
    raw = payload.get("rawId") or payload.get("id")
    if not raw:
        raise HTTPException(status_code=400, detail="Passkey credential ID is missing.")
    try:
        return base64url_to_bytes(str(raw))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Passkey credential ID is invalid.") from exc


@router.post("/audit-access/passkey/status")
def external_passkey_status(payload: AuditAccessExchange, db: Session = Depends(get_db)) -> dict[str, Any]:
    grant, participant, identity = _passkey_grant(db, payload.token)
    credentials = _credentials(db, grant)
    return {
        "required": True,
        "registered": bool(credentials),
        "participant_type": participant.participant_type,
        "display_name": identity.display_name,
        "organisation": identity.organisation,
        "expires_at": grant.expires_at.isoformat(),
    }


@router.post("/audit-access/passkey/registration/options")
def external_passkey_registration_options(payload: AuditAccessExchange, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    grant, _, identity = _passkey_grant(db, payload.token)
    rp_id, _ = _configured_webauthn(request)
    existing = _credentials(db, grant)
    challenge = secrets.token_bytes(32)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name="AMO Portal Quality Management",
        user_id=f"external:{identity.id}".encode("utf-8"),
        user_name=identity.email,
        user_display_name=identity.display_name,
        challenge=challenge,
        authenticator_selection=AuthenticatorSelectionCriteria(user_verification=UserVerificationRequirement.REQUIRED),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=bytes(item.credential_id)) for item in existing],
    )
    row = QualityAuditWebAuthnChallenge(
        amo_id=grant.amo_id,
        owner_type="EXTERNAL_IDENTITY",
        external_identity_id=identity.id,
        audit_id=grant.audit_id,
        challenge_type="REGISTRATION",
        challenge_b64=_b64(challenge),
        challenge_hash=hashlib.sha256(challenge).hexdigest(),
        expires_at=_utcnow() + timedelta(seconds=_ttl_seconds()),
    )
    db.add(row)
    db.commit()
    return {"challenge_id": row.id, "options": _options_payload(options)}


@router.post("/audit-access/passkey/registration/verify", status_code=status.HTTP_201_CREATED)
def external_passkey_registration_verify(
    payload: ExternalPasskeyVerify,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    grant, _, identity = _passkey_grant(db, payload.token)
    rp_id, origin = _configured_webauthn(request)
    now = _utcnow()
    challenge = db.query(QualityAuditWebAuthnChallenge).filter(
        QualityAuditWebAuthnChallenge.id == payload.challenge_id,
        QualityAuditWebAuthnChallenge.amo_id == grant.amo_id,
        QualityAuditWebAuthnChallenge.owner_type == "EXTERNAL_IDENTITY",
        QualityAuditWebAuthnChallenge.external_identity_id == identity.id,
        QualityAuditWebAuthnChallenge.audit_id == grant.audit_id,
        QualityAuditWebAuthnChallenge.challenge_type == "REGISTRATION",
        QualityAuditWebAuthnChallenge.consumed_at.is_(None),
        QualityAuditWebAuthnChallenge.expires_at > now,
    ).with_for_update().first()
    if challenge is None:
        raise HTTPException(status_code=400, detail="External-auditor passkey registration challenge is expired or invalid.")
    challenge.consumed_at = now
    try:
        verification = verify_registration_response(
            credential=payload.credential,
            expected_challenge=_b64decode(challenge.challenge_b64),
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except Exception as exc:
        db.commit()
        raise HTTPException(status_code=400, detail="External-auditor passkey registration could not be verified.") from exc
    duplicate = db.query(QualityAuditWebAuthnCredential).filter(
        QualityAuditWebAuthnCredential.amo_id == grant.amo_id,
        QualityAuditWebAuthnCredential.credential_id == verification.credential_id,
    ).first()
    if duplicate is not None:
        db.commit()
        raise HTTPException(status_code=409, detail="This passkey is already registered.")
    db.add(QualityAuditWebAuthnCredential(
        amo_id=grant.amo_id,
        owner_type="EXTERNAL_IDENTITY",
        external_identity_id=identity.id,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=int(verification.sign_count or 0),
        transports=list((payload.credential.get("response") or {}).get("transports") or []),
        nickname=(payload.nickname or "External audit passkey").strip() or None,
        is_active=True,
    ))
    db.flush()
    return _activate_session(db, grant, response, request, payload.token, "External auditor passkey registration verified; purpose-bound audit session activated.")


@router.post("/audit-access/passkey/assertion/options")
def external_passkey_assertion_options(payload: AuditAccessExchange, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    grant, _, identity = _passkey_grant(db, payload.token)
    rp_id, _ = _configured_webauthn(request)
    credentials = _credentials(db, grant)
    if not credentials:
        raise HTTPException(status_code=409, detail="No passkey is registered for this external auditor. Complete registration first.")
    challenge = secrets.token_bytes(32)
    options = generate_authentication_options(
        rp_id=rp_id,
        challenge=challenge,
        allow_credentials=[PublicKeyCredentialDescriptor(id=bytes(item.credential_id)) for item in credentials],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    row = QualityAuditWebAuthnChallenge(
        amo_id=grant.amo_id,
        owner_type="EXTERNAL_IDENTITY",
        external_identity_id=identity.id,
        audit_id=grant.audit_id,
        challenge_type="EXTERNAL_ASSERTION",
        challenge_b64=_b64(challenge),
        challenge_hash=hashlib.sha256(challenge).hexdigest(),
        expires_at=_utcnow() + timedelta(seconds=_ttl_seconds()),
    )
    db.add(row)
    db.commit()
    return {"challenge_id": row.id, "options": _options_payload(options)}


@router.post("/audit-access/passkey/assertion/verify")
def external_passkey_assertion_verify(
    payload: ExternalPasskeyVerify,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    grant, _, identity = _passkey_grant(db, payload.token)
    rp_id, origin = _configured_webauthn(request)
    now = _utcnow()
    challenge = db.query(QualityAuditWebAuthnChallenge).filter(
        QualityAuditWebAuthnChallenge.id == payload.challenge_id,
        QualityAuditWebAuthnChallenge.amo_id == grant.amo_id,
        QualityAuditWebAuthnChallenge.owner_type == "EXTERNAL_IDENTITY",
        QualityAuditWebAuthnChallenge.external_identity_id == identity.id,
        QualityAuditWebAuthnChallenge.audit_id == grant.audit_id,
        QualityAuditWebAuthnChallenge.challenge_type == "EXTERNAL_ASSERTION",
        QualityAuditWebAuthnChallenge.consumed_at.is_(None),
        QualityAuditWebAuthnChallenge.expires_at > now,
    ).with_for_update().first()
    if challenge is None:
        raise HTTPException(status_code=400, detail="External-auditor passkey assertion challenge is expired or invalid.")
    challenge.consumed_at = now
    credential_id = _credential_id(payload.credential)
    credential = db.query(QualityAuditWebAuthnCredential).filter(
        QualityAuditWebAuthnCredential.amo_id == grant.amo_id,
        QualityAuditWebAuthnCredential.owner_type == "EXTERNAL_IDENTITY",
        QualityAuditWebAuthnCredential.external_identity_id == identity.id,
        QualityAuditWebAuthnCredential.credential_id == credential_id,
        QualityAuditWebAuthnCredential.is_active.is_(True),
    ).first()
    if credential is None:
        db.commit()
        raise HTTPException(status_code=403, detail="This passkey is not registered for the assigned external auditor.")
    try:
        verification = verify_authentication_response(
            credential=payload.credential,
            expected_challenge=_b64decode(challenge.challenge_b64),
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=bytes(credential.public_key),
            credential_current_sign_count=int(credential.sign_count or 0),
            require_user_verification=True,
        )
    except Exception as exc:
        db.commit()
        raise HTTPException(status_code=400, detail="External-auditor passkey assertion could not be verified.") from exc
    credential.sign_count = int(verification.new_sign_count or 0)
    credential.last_used_at = now
    credential.updated_at = now
    return _activate_session(db, grant, response, request, payload.token, "External auditor passkey assertion verified; purpose-bound audit session activated.")


public_router.include_router(router)
