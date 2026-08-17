from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session, selectinload
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)

from amodb.apps.accounts import models as account_models
from amodb.database import get_db, get_read_db, get_write_db
from amodb.security import SECRET_KEY
from amodb.user_id import generate_user_id

from . import models
from .audit_closing_assurance_models import QualityAuditAssuranceArtifact, QualityAuditSignatureAttempt, QualityAuditSignatureEvidence
from .audit_external_access_models import QualityAuditAccessEvent, QualityAuditParticipant
from .audit_external_access_router import _GUEST_COOKIE, _active_grant, _append_access_event, _set_public_tenant_context
from .audit_live_completion_models import (
    QualityAuditClosingAcknowledgement,
    QualityAuditVerificationToken,
    QualityAuditWebAuthnChallenge,
    QualityAuditWebAuthnCredential,
)
from .audit_report_governance_models import QualityAuditReportEvent, QualityAuditReportRevision
from .audit_report_governance_router import _add_event, _audit, _revision_dict, _sha256, _state_snapshot
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality audit completion ceremony"])
public_router = APIRouter(prefix="/quality", tags=["Quality / Audit Completion Ceremony"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _configured_webauthn(request: Request) -> tuple[str, str]:
    host = (request.url.hostname or "").strip().lower()
    origin = f"{request.url.scheme}://{request.url.netloc}"
    production = os.getenv("APP_ENV", "").strip().lower() in {"prod", "production"}
    rp_id = (os.getenv("QMS_WEBAUTHN_RP_ID") or "").strip().lower()
    configured_origins = [item.strip().rstrip("/") for item in (os.getenv("QMS_WEBAUTHN_EXPECTED_ORIGINS") or "").split(",") if item.strip()]
    if production and (not rp_id or not configured_origins):
        raise HTTPException(status_code=503, detail="QMS WebAuthn is disabled until the RP ID and expected origins are configured.")
    if not rp_id:
        rp_id = host
    if not configured_origins:
        configured_origins = [origin]
    if not rp_id or origin.rstrip("/") not in configured_origins:
        raise HTTPException(status_code=403, detail="This origin is not authorized for QMS passkey ceremonies.")
    if request.url.scheme != "https" and host not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="QMS passkey ceremonies require a secure HTTPS context.")
    return rp_id, origin.rstrip("/")


def _challenge_ttl() -> int:
    try:
        value = int(os.getenv("QMS_WEBAUTHN_CHALLENGE_TTL_SECONDS", "300"))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="QMS WebAuthn challenge policy is invalid.") from exc
    if value < 60 or value > 900:
        raise HTTPException(status_code=503, detail="QMS WebAuthn challenge TTL must be between 60 and 900 seconds.")
    return value


def _options_payload(options: Any) -> dict[str, Any]:
    return json.loads(options_to_json(options))


def _client_data(credential: dict[str, Any]) -> dict[str, Any]:
    try:
        encoded = credential["response"]["clientDataJSON"]
        return json.loads(base64url_to_bytes(encoded).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Malformed WebAuthn client data.") from exc


def _credential_bytes(credential: dict[str, Any]) -> bytes:
    raw = credential.get("rawId") or credential.get("id")
    if not raw:
        raise HTTPException(status_code=400, detail="WebAuthn credential ID is missing.")
    try:
        return base64url_to_bytes(str(raw))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="WebAuthn credential ID is invalid.") from exc


def _user(db: Session, *, amo_id: str, user_id: str) -> account_models.User:
    row = db.query(account_models.User).filter(account_models.User.amo_id == amo_id, account_models.User.id == user_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Signing user not found.")
    return row


def _credential_dict(row: QualityAuditWebAuthnCredential) -> dict[str, Any]:
    encoded = _b64(bytes(row.credential_id))
    return {
        "id": row.id,
        "credential_id_masked": f"{encoded[:8]}…{encoded[-5:]}" if len(encoded) > 16 else encoded,
        "nickname": row.nickname,
        "transports": list(row.transports or []),
        "sign_count": int(row.sign_count or 0),
        "is_active": bool(row.is_active),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
    }


def _signature_dict(row: QualityAuditSignatureEvidence) -> dict[str, Any]:
    return {
        "id": row.id,
        "audit_id": str(row.audit_id),
        "report_revision_id": row.report_revision_id,
        "signer_user_id": row.signer_user_id,
        "method": row.method,
        "purpose": row.purpose,
        "artifact_sha256": row.artifact_sha256,
        "reason": row.reason,
        "signature_digest": row.signature_digest,
        "credential_id_hash": row.credential_id_hash,
        "webauthn_sign_count": row.webauthn_sign_count,
        "webauthn_origin": row.webauthn_origin,
        "webauthn_rp_id": row.webauthn_rp_id,
        "ceremony_sha256": row.ceremony_sha256,
        "signed_at": row.signed_at.isoformat() if row.signed_at else None,
    }


def _ack_dict(row: QualityAuditClosingAcknowledgement) -> dict[str, Any]:
    return {
        "id": row.id,
        "audit_id": str(row.audit_id),
        "participant_id": row.participant_id,
        "report_revision_id": row.report_revision_id,
        "report_sha256": row.report_sha256,
        "acknowledgement_status": row.acknowledgement_status,
        "comments": row.comments,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _signable_report(db: Session, *, amo_id: str, audit_id: uuid.UUID, revision_id: str, signer_user_id: str) -> QualityAuditReportRevision:
    row = db.query(QualityAuditReportRevision).filter(
        QualityAuditReportRevision.amo_id == amo_id,
        QualityAuditReportRevision.audit_id == audit_id,
        QualityAuditReportRevision.id == revision_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Governed audit report revision not found.")
    if row.status != "APPROVED":
        raise HTTPException(status_code=409, detail="Only an APPROVED report revision may enter the passkey signing ceremony.")
    if row.approved_by_user_id and row.approved_by_user_id != signer_user_id:
        raise HTTPException(status_code=403, detail="The approving Quality user must complete the passkey signing ceremony for this revision.")
    path = Path(row.file_ref)
    if not path.is_file() or _sha256(path) != row.sha256:
        raise HTTPException(status_code=409, detail="The approved report file no longer matches its governed checksum.")
    return row


def _latest_ack(db: Session, row: QualityAuditReportRevision) -> QualityAuditClosingAcknowledgement | None:
    return db.query(QualityAuditClosingAcknowledgement).filter(
        QualityAuditClosingAcknowledgement.amo_id == row.amo_id,
        QualityAuditClosingAcknowledgement.audit_id == row.audit_id,
        QualityAuditClosingAcknowledgement.report_revision_id == row.id,
        QualityAuditClosingAcknowledgement.report_sha256 == row.sha256,
    ).order_by(QualityAuditClosingAcknowledgement.created_at.desc()).first()


def _requires_auditee_ack(db: Session, row: QualityAuditReportRevision) -> bool:
    return db.query(QualityAuditParticipant.id).filter(
        QualityAuditParticipant.amo_id == row.amo_id,
        QualityAuditParticipant.audit_id == row.audit_id,
        QualityAuditParticipant.participant_type == "AUDITEE_GUEST",
        QualityAuditParticipant.status.in_(["INVITED", "ACTIVE"]),
        QualityAuditParticipant.expires_at > _utcnow(),
    ).first() is not None


def _require_closing_ack(db: Session, row: QualityAuditReportRevision) -> None:
    if _requires_auditee_ack(db, row) and _latest_ack(db, row) is None:
        raise HTTPException(
            status_code=409,
            detail="Record the auditee closing-meeting acknowledgement or comments against this exact report revision before continuing.",
        )


def _valid_passkey_signature(db: Session, row: QualityAuditReportRevision) -> QualityAuditSignatureEvidence | None:
    query = db.query(QualityAuditSignatureEvidence).filter(
        QualityAuditSignatureEvidence.amo_id == row.amo_id,
        QualityAuditSignatureEvidence.audit_id == row.audit_id,
        QualityAuditSignatureEvidence.report_revision_id == row.id,
        QualityAuditSignatureEvidence.method == "WEBAUTHN",
        QualityAuditSignatureEvidence.purpose == "APPROVED_REPORT",
        QualityAuditSignatureEvidence.artifact_sha256 == row.sha256,
    )
    if row.approved_at is not None:
        query = query.filter(QualityAuditSignatureEvidence.signed_at >= row.approved_at)
    return query.order_by(QualityAuditSignatureEvidence.signed_at.desc()).first()


class WebAuthnRegistrationVerify(BaseModel):
    challenge_id: str = Field(min_length=8, max_length=36)
    credential: dict[str, Any]
    nickname: str | None = Field(default=None, max_length=80)


class WebAuthnReportSignatureVerify(BaseModel):
    challenge_id: str = Field(min_length=8, max_length=36)
    credential: dict[str, Any]
    reason: str = Field(min_length=8, max_length=4000)


class ClosingAcknowledgementCreate(BaseModel):
    report_revision_id: str = Field(min_length=8, max_length=36)
    report_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    acknowledgement_status: Literal["ACKNOWLEDGED", "COMMENTED", "DECLINED_TO_ACKNOWLEDGE"]
    comments: str | None = Field(default=None, max_length=8000)

    @model_validator(mode="after")
    def validate_comments(self):
        if self.acknowledgement_status in {"COMMENTED", "DECLINED_TO_ACKNOWLEDGE"} and not (self.comments or "").strip():
            raise ValueError("Comments are required for this acknowledgement status.")
        return self


class VerificationTokenCreate(BaseModel):
    assurance_artifact_id: str | None = Field(default=None, max_length=36)
    expires_in_days: int = Field(default=180, ge=1, le=3650)


class HashCompare(BaseModel):
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


@router.post("/audit-webauthn/registration/options")
def webauthn_registration_options(
    request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rp_id, _ = _configured_webauthn(request)
    user = _user(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    challenge = secrets.token_bytes(32)
    current = db.query(QualityAuditWebAuthnCredential).filter(
        QualityAuditWebAuthnCredential.amo_id == ctx.amo_id,
        QualityAuditWebAuthnCredential.owner_type == "INTERNAL_USER",
        QualityAuditWebAuthnCredential.user_id == ctx.user_id,
        QualityAuditWebAuthnCredential.is_active.is_(True),
    ).all()
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name="AMO Portal Quality Management",
        user_id=str(ctx.user_id).encode("utf-8"),
        user_name=str(getattr(user, "email", None) or ctx.user_id),
        user_display_name=str(getattr(user, "full_name", None) or getattr(user, "email", None) or ctx.user_id),
        challenge=challenge,
        authenticator_selection=AuthenticatorSelectionCriteria(user_verification=UserVerificationRequirement.REQUIRED),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=bytes(item.credential_id)) for item in current],
    )
    row = QualityAuditWebAuthnChallenge(
        amo_id=ctx.amo_id,
        owner_type="INTERNAL_USER",
        user_id=ctx.user_id,
        challenge_type="REGISTRATION",
        challenge_b64=_b64(challenge),
        challenge_hash=hashlib.sha256(challenge).hexdigest(),
        expires_at=_utcnow() + timedelta(seconds=_challenge_ttl()),
    )
    db.add(row)
    db.commit()
    return {"challenge_id": row.id, "options": _options_payload(options)}


@router.post("/audit-webauthn/registration/verify", status_code=status.HTTP_201_CREATED)
def webauthn_registration_verify(
    payload: WebAuthnRegistrationVerify,
    request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rp_id, origin = _configured_webauthn(request)
    now = _utcnow()
    challenge = db.query(QualityAuditWebAuthnChallenge).filter(
        QualityAuditWebAuthnChallenge.id == payload.challenge_id,
        QualityAuditWebAuthnChallenge.amo_id == ctx.amo_id,
        QualityAuditWebAuthnChallenge.owner_type == "INTERNAL_USER",
        QualityAuditWebAuthnChallenge.user_id == ctx.user_id,
        QualityAuditWebAuthnChallenge.challenge_type == "REGISTRATION",
        QualityAuditWebAuthnChallenge.consumed_at.is_(None),
        QualityAuditWebAuthnChallenge.expires_at > now,
    ).with_for_update().first()
    if challenge is None:
        raise HTTPException(status_code=400, detail="Passkey registration challenge is expired or invalid.")
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
        raise HTTPException(status_code=400, detail="Passkey registration could not be verified.") from exc
    existing = db.query(QualityAuditWebAuthnCredential).filter(
        QualityAuditWebAuthnCredential.amo_id == ctx.amo_id,
        QualityAuditWebAuthnCredential.credential_id == verification.credential_id,
    ).first()
    if existing is not None:
        db.commit()
        raise HTTPException(status_code=409, detail="This passkey is already registered.")
    row = QualityAuditWebAuthnCredential(
        amo_id=ctx.amo_id,
        owner_type="INTERNAL_USER",
        user_id=ctx.user_id,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=int(verification.sign_count or 0),
        transports=list((payload.credential.get("response") or {}).get("transports") or []),
        nickname=(payload.nickname or "").strip() or None,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _credential_dict(row)


@router.get("/audit-webauthn/credentials")
def list_webauthn_credentials(
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = db.query(QualityAuditWebAuthnCredential).filter(
        QualityAuditWebAuthnCredential.amo_id == ctx.amo_id,
        QualityAuditWebAuthnCredential.owner_type == "INTERNAL_USER",
        QualityAuditWebAuthnCredential.user_id == ctx.user_id,
    ).order_by(QualityAuditWebAuthnCredential.created_at.desc()).all()
    return {"items": [_credential_dict(row) for row in rows]}


@router.delete("/audit-webauthn/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_webauthn_credential(
    credential_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> None:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAuditWebAuthnCredential).filter(
        QualityAuditWebAuthnCredential.id == credential_id,
        QualityAuditWebAuthnCredential.amo_id == ctx.amo_id,
        QualityAuditWebAuthnCredential.owner_type == "INTERNAL_USER",
        QualityAuditWebAuthnCredential.user_id == ctx.user_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Passkey credential not found.")
    row.is_active = False
    row.updated_at = _utcnow()
    db.commit()


@router.post("/audits/{audit_id}/report-revisions/{revision_id}/signature/options")
def report_signature_options(
    audit_id: uuid.UUID,
    revision_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rp_id, _ = _configured_webauthn(request)
    row = _signable_report(db, amo_id=ctx.amo_id, audit_id=audit_id, revision_id=revision_id, signer_user_id=ctx.user_id)
    _require_closing_ack(db, row)
    credentials = db.query(QualityAuditWebAuthnCredential).filter(
        QualityAuditWebAuthnCredential.amo_id == ctx.amo_id,
        QualityAuditWebAuthnCredential.owner_type == "INTERNAL_USER",
        QualityAuditWebAuthnCredential.user_id == ctx.user_id,
        QualityAuditWebAuthnCredential.is_active.is_(True),
    ).all()
    if not credentials:
        raise HTTPException(status_code=409, detail="Register a passkey before signing the approved audit report.")
    existing = _valid_passkey_signature(db, row)
    if existing is not None:
        return {"already_signed": True, "signature": _signature_dict(existing)}
    challenge_bytes = secrets.token_bytes(32)
    options = generate_authentication_options(
        rp_id=rp_id,
        challenge=challenge_bytes,
        allow_credentials=[PublicKeyCredentialDescriptor(id=bytes(item.credential_id)) for item in credentials],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    challenge = QualityAuditWebAuthnChallenge(
        amo_id=ctx.amo_id,
        owner_type="INTERNAL_USER",
        user_id=ctx.user_id,
        audit_id=audit_id,
        report_revision_id=row.id,
        challenge_type="REPORT_SIGNATURE",
        challenge_b64=_b64(challenge_bytes),
        challenge_hash=hashlib.sha256(challenge_bytes).hexdigest(),
        expires_at=_utcnow() + timedelta(seconds=_challenge_ttl()),
    )
    db.add(challenge)
    db.commit()
    return {"already_signed": False, "challenge_id": challenge.id, "report_sha256": row.sha256, "options": _options_payload(options)}


@router.post("/audits/{audit_id}/report-revisions/{revision_id}/signature/verify", status_code=status.HTTP_201_CREATED)
def report_signature_verify(
    audit_id: uuid.UUID,
    revision_id: str,
    payload: WebAuthnReportSignatureVerify,
    request: Request,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rp_id, origin = _configured_webauthn(request)
    row = _signable_report(db, amo_id=ctx.amo_id, audit_id=audit_id, revision_id=revision_id, signer_user_id=ctx.user_id)
    _require_closing_ack(db, row)
    existing = _valid_passkey_signature(db, row)
    if existing is not None:
        return _signature_dict(existing)
    now = _utcnow()
    challenge = db.query(QualityAuditWebAuthnChallenge).filter(
        QualityAuditWebAuthnChallenge.id == payload.challenge_id,
        QualityAuditWebAuthnChallenge.amo_id == ctx.amo_id,
        QualityAuditWebAuthnChallenge.owner_type == "INTERNAL_USER",
        QualityAuditWebAuthnChallenge.user_id == ctx.user_id,
        QualityAuditWebAuthnChallenge.audit_id == audit_id,
        QualityAuditWebAuthnChallenge.report_revision_id == row.id,
        QualityAuditWebAuthnChallenge.challenge_type == "REPORT_SIGNATURE",
        QualityAuditWebAuthnChallenge.consumed_at.is_(None),
        QualityAuditWebAuthnChallenge.expires_at > now,
    ).with_for_update().first()
    if challenge is None:
        raise HTTPException(status_code=400, detail="Passkey signing challenge is expired or invalid.")
    challenge.consumed_at = now
    credential_id = _credential_bytes(payload.credential)
    credential = db.query(QualityAuditWebAuthnCredential).filter(
        QualityAuditWebAuthnCredential.amo_id == ctx.amo_id,
        QualityAuditWebAuthnCredential.owner_type == "INTERNAL_USER",
        QualityAuditWebAuthnCredential.user_id == ctx.user_id,
        QualityAuditWebAuthnCredential.credential_id == credential_id,
        QualityAuditWebAuthnCredential.is_active.is_(True),
    ).first()
    if credential is None:
        db.add(QualityAuditSignatureAttempt(amo_id=ctx.amo_id, audit_id=audit_id, signer_user_id=ctx.user_id, method="WEBAUTHN", succeeded=False, failure_code="CREDENTIAL_NOT_FOUND"))
        db.commit()
        raise HTTPException(status_code=403, detail="Passkey credential is not registered for this user.")
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
        db.add(QualityAuditSignatureAttempt(amo_id=ctx.amo_id, audit_id=audit_id, signer_user_id=ctx.user_id, method="WEBAUTHN", succeeded=False, failure_code="ASSERTION_INVALID"))
        db.commit()
        raise HTTPException(status_code=400, detail="Passkey signing assertion could not be verified.") from exc

    new_count = int(verification.new_sign_count or 0)
    credential.sign_count = new_count
    credential.last_used_at = now
    credential.updated_at = now
    client_data = _client_data(payload.credential)
    credential_hash = hashlib.sha256(bytes(credential.credential_id)).hexdigest()
    ceremony = {
        "version": "QMS_AUDIT_WEBAUTHN_V1",
        "amo_id": ctx.amo_id,
        "audit_id": str(audit_id),
        "report_revision_id": row.id,
        "report_sha256": row.sha256,
        "signer_user_id": ctx.user_id,
        "credential_id_hash": credential_hash,
        "sign_count": new_count,
        "origin": origin,
        "rp_id": rp_id,
        "reason": payload.reason.strip(),
        "signed_at": now.isoformat(),
    }
    ceremony_sha = _canonical_hash(ceremony)
    nonce = secrets.token_urlsafe(32)
    digest_input = f"QMS_AUDIT_WEBAUTHN_SIGNATURE_V1|{ceremony_sha}|{nonce}".encode("utf-8")
    signature_digest = hmac.new(SECRET_KEY.encode("utf-8"), digest_input, hashlib.sha256).hexdigest()
    evidence = QualityAuditSignatureEvidence(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        report_revision_id=row.id,
        signer_user_id=ctx.user_id,
        method="WEBAUTHN",
        purpose="APPROVED_REPORT",
        artifact_sha256=row.sha256,
        reason=payload.reason.strip(),
        signature_digest=signature_digest,
        nonce=nonce,
        credential_id_hash=credential_hash,
        webauthn_sign_count=new_count,
        webauthn_origin=str(client_data.get("origin") or origin),
        webauthn_rp_id=rp_id,
        ceremony_sha256=ceremony_sha,
        signed_at=now,
    )
    db.add(evidence)
    db.add(QualityAuditSignatureAttempt(amo_id=ctx.amo_id, audit_id=audit_id, signer_user_id=ctx.user_id, method="WEBAUTHN", succeeded=True, failure_code=None))
    db.commit()
    db.refresh(evidence)
    return _signature_dict(evidence)


@router.get("/audits/{audit_id}/closing-acknowledgements")
def list_closing_acknowledgements(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    rows = db.query(QualityAuditClosingAcknowledgement).filter(
        QualityAuditClosingAcknowledgement.amo_id == ctx.amo_id,
        QualityAuditClosingAcknowledgement.audit_id == audit_id,
    ).order_by(QualityAuditClosingAcknowledgement.created_at.desc()).limit(100).all()
    return {"items": [_ack_dict(row) for row in rows]}


@router.post("/audits/{audit_id}/report-revisions/{revision_id}/transitions")
def transition_report_revision_guarded(
    audit_id: uuid.UUID,
    revision_id: str,
    payload: dict[str, Any],
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    row = db.query(QualityAuditReportRevision).options(selectinload(QualityAuditReportRevision.events)).filter(
        QualityAuditReportRevision.amo_id == ctx.amo_id,
        QualityAuditReportRevision.audit_id == audit_id,
        QualityAuditReportRevision.id == revision_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Governed audit report revision not found.")
    action = str(payload.get("action") or "").strip().upper()
    reason = str(payload.get("reason") or "").strip()
    if len(reason) < 8 or len(reason) > 4000:
        raise HTTPException(status_code=422, detail="A transition reason of 8 to 4000 characters is required.")
    before = _state_snapshot(row)
    if action == "SUBMIT":
        if row.status != "DRAFT":
            raise HTTPException(status_code=409, detail="Only a DRAFT report revision may enter internal review.")
        _require_closing_ack(db, row)
        row.status = "INTERNAL_REVIEW"
        row.reviewed_by_user_id = None
        row.reviewed_at = None
        event = "SUBMITTED"
    elif action == "RETURN":
        if row.status not in {"INTERNAL_REVIEW", "APPROVED"}:
            raise HTTPException(status_code=409, detail="Only a report under review or approved-but-not-issued may be returned to draft.")
        row.status = "DRAFT"
        row.reviewed_by_user_id = None
        row.reviewed_at = None
        row.approved_by_user_id = None
        row.approved_at = None
        event = "RETURNED"
    elif action == "APPROVE":
        if row.status != "INTERNAL_REVIEW":
            raise HTTPException(status_code=409, detail="Only a report in INTERNAL_REVIEW may be approved.")
        _require_closing_ack(db, row)
        now = _utcnow()
        row.status = "APPROVED"
        row.reviewed_by_user_id = ctx.user_id
        row.reviewed_at = now
        row.approved_by_user_id = ctx.user_id
        row.approved_at = now
        event = "APPROVED"
    elif action == "ISSUE":
        if row.status != "APPROVED":
            raise HTTPException(status_code=409, detail="Only an APPROVED audit report revision may be issued.")
        _require_closing_ack(db, row)
        signature = _valid_passkey_signature(db, row)
        if signature is None:
            raise HTTPException(status_code=409, detail="Complete the passkey signing ceremony against this approved report revision before issue.")
        path = Path(row.file_ref)
        if not path.is_file() or _sha256(path) != row.sha256:
            raise HTTPException(status_code=409, detail="The approved report file no longer matches its governed checksum and cannot be issued.")
        prior = db.query(QualityAuditReportRevision).filter(
            QualityAuditReportRevision.amo_id == ctx.amo_id,
            QualityAuditReportRevision.audit_id == audit_id,
            QualityAuditReportRevision.status == "ISSUED",
            QualityAuditReportRevision.id != row.id,
        ).order_by(QualityAuditReportRevision.revision_no.desc()).with_for_update().first()
        if prior is not None:
            prior_before = _state_snapshot(prior)
            prior.status = "SUPERSEDED"
            _add_event(db, ctx=ctx, row=prior, event_type="SUPERSEDED", reason=f"Superseded by report revision {row.revision_no}: {reason}", before=prior_before)
        row.status = "ISSUED"
        row.issued_by_user_id = ctx.user_id
        row.issued_at = _utcnow()
        audit.report_file_ref = row.file_ref
        event = "ISSUED"
    elif action == "CANCEL":
        if row.status not in {"DRAFT", "INTERNAL_REVIEW", "APPROVED"}:
            raise HTTPException(status_code=409, detail="Issued or superseded audit report revisions cannot be cancelled.")
        row.status = "CANCELLED"
        event = "CANCELLED"
    else:
        raise HTTPException(status_code=422, detail="Unsupported report transition.")
    row.updated_at = _utcnow()
    _add_event(db, ctx=ctx, row=row, event_type=event, reason=reason, before=before)
    db.commit()
    loaded = db.query(QualityAuditReportRevision).options(selectinload(QualityAuditReportRevision.events)).filter(QualityAuditReportRevision.id == row.id).one()
    return _revision_dict(loaded)


@public_router.get("/audit-access/closing")
def public_closing_context(
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session required.")
    grant = _active_grant(db, amo_qms_audit_guest)
    participant = grant.participant
    if participant is None or participant.participant_type != "AUDITEE_GUEST" or "audit:acknowledge" not in set(grant.scope_json or []):
        raise HTTPException(status_code=403, detail="This audit access grant cannot acknowledge the closing meeting.")
    row = db.query(QualityAuditReportRevision).filter(
        QualityAuditReportRevision.amo_id == grant.amo_id,
        QualityAuditReportRevision.audit_id == grant.audit_id,
        QualityAuditReportRevision.status.in_(["DRAFT", "INTERNAL_REVIEW"]),
    ).order_by(QualityAuditReportRevision.revision_no.desc()).first()
    if row is None:
        return {"available": False, "report": None, "acknowledgement": None}
    ack = _latest_ack(db, row)
    return {
        "available": True,
        "report": {
            "id": row.id,
            "revision_no": row.revision_no,
            "status": row.status,
            "filename": row.filename,
            "sha256": row.sha256,
            "report_snapshot": row.report_snapshot or {},
        },
        "acknowledgement": _ack_dict(ack) if ack else None,
    }


@public_router.post("/audit-access/closing/acknowledgements", status_code=status.HTTP_201_CREATED)
def public_closing_acknowledgement(
    payload: ClosingAcknowledgementCreate,
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session required.")
    grant = _active_grant(db, amo_qms_audit_guest)
    participant = grant.participant
    if participant is None or participant.participant_type != "AUDITEE_GUEST" or "audit:acknowledge" not in set(grant.scope_json or []):
        raise HTTPException(status_code=403, detail="This audit access grant cannot acknowledge the closing meeting.")
    row = db.query(QualityAuditReportRevision).filter(
        QualityAuditReportRevision.amo_id == grant.amo_id,
        QualityAuditReportRevision.audit_id == grant.audit_id,
        QualityAuditReportRevision.id == payload.report_revision_id,
        QualityAuditReportRevision.sha256 == payload.report_sha256.lower(),
        QualityAuditReportRevision.status == "DRAFT",
    ).first()
    if row is None:
        raise HTTPException(status_code=409, detail="The closing report changed or is no longer awaiting auditee acknowledgement. Refresh before responding.")
    ack = QualityAuditClosingAcknowledgement(
        amo_id=grant.amo_id,
        audit_id=grant.audit_id,
        participant_id=grant.participant_id,
        grant_id=grant.id,
        report_revision_id=row.id,
        report_sha256=row.sha256,
        acknowledgement_status=payload.acknowledgement_status,
        comments=(payload.comments or "").strip() or None,
    )
    db.add(ack)
    _append_access_event(db, grant, "ACKNOWLEDGED", f"Closing meeting response recorded for report revision {row.revision_no} ({row.sha256}).")
    db.commit()
    db.refresh(ack)
    return _ack_dict(ack)


def _verification_token_signature(segment: str) -> str:
    return _b64(hmac.new(SECRET_KEY.encode("utf-8"), segment.encode("ascii"), hashlib.sha256).digest())


def _make_verification_token(*, amo_id: str, token_id: str, expires_at: datetime) -> str:
    body = {
        "v": 1,
        "t": amo_id,
        "i": token_id,
        "e": int(expires_at.timestamp()),
        "n": secrets.token_urlsafe(32),
    }
    segment = _b64(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return f"{segment}.{_verification_token_signature(segment)}"


def _decode_verification_token(token: str) -> dict[str, Any]:
    clean = str(token or "").strip()
    if not clean or clean.count(".") != 1 or len(clean) > 2048:
        raise HTTPException(status_code=404, detail="Verification record not found.")
    segment, signature = clean.split(".", 1)
    if not hmac.compare_digest(signature, _verification_token_signature(segment)):
        raise HTTPException(status_code=404, detail="Verification record not found.")
    try:
        body = json.loads(_b64decode(segment))
        expiry = int(body.get("e"))
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Verification record not found.") from exc
    if body.get("v") != 1 or not body.get("t") or not body.get("i") or expiry <= int(_utcnow().timestamp()):
        raise HTTPException(status_code=404, detail="Verification record not found.")
    return {"amo_id": str(body["t"]), "token_id": str(body["i"]), "expiry": expiry}


@router.post("/audits/{audit_id}/verification-tokens", status_code=status.HTTP_201_CREATED)
def create_verification_token(
    audit_id: uuid.UUID,
    payload: VerificationTokenCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    report = db.query(QualityAuditReportRevision).filter(
        QualityAuditReportRevision.amo_id == ctx.amo_id,
        QualityAuditReportRevision.audit_id == audit_id,
        QualityAuditReportRevision.status == "ISSUED",
    ).order_by(QualityAuditReportRevision.revision_no.desc()).first()
    if report is None:
        raise HTTPException(status_code=409, detail="An issued governed report is required before creating a public verification record.")
    signature = db.query(QualityAuditSignatureEvidence).filter(
        QualityAuditSignatureEvidence.amo_id == ctx.amo_id,
        QualityAuditSignatureEvidence.audit_id == audit_id,
        QualityAuditSignatureEvidence.report_revision_id == report.id,
        QualityAuditSignatureEvidence.method == "WEBAUTHN",
        QualityAuditSignatureEvidence.artifact_sha256 == report.sha256,
    ).order_by(QualityAuditSignatureEvidence.signed_at.desc()).first()
    if signature is None:
        raise HTTPException(status_code=409, detail="The issued report does not have matching passkey signature evidence.")
    assurance = None
    if payload.assurance_artifact_id:
        assurance = db.query(QualityAuditAssuranceArtifact).filter(
            QualityAuditAssuranceArtifact.amo_id == ctx.amo_id,
            QualityAuditAssuranceArtifact.audit_id == audit_id,
            QualityAuditAssuranceArtifact.id == payload.assurance_artifact_id,
            QualityAuditAssuranceArtifact.source_report_revision_id == report.id,
        ).first()
        if assurance is None:
            raise HTTPException(status_code=404, detail="Assurance artifact not found for this issued report.")
    expires_at = _utcnow() + timedelta(days=payload.expires_in_days)
    token_row = QualityAuditVerificationToken(
        id=generate_user_id(),
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        report_revision_id=report.id,
        signature_evidence_id=signature.id,
        assurance_artifact_id=assurance.id if assurance else None,
        token_hash="pending",
        expires_at=expires_at,
        created_by_user_id=ctx.user_id,
    )
    raw_token = _make_verification_token(amo_id=ctx.amo_id, token_id=token_row.id, expires_at=expires_at)
    token_row.token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    db.add(token_row)
    db.commit()
    return {
        "id": token_row.id,
        "expires_at": expires_at.isoformat(),
        "verification_url": f"/verify/{quote(raw_token, safe='')}",
        "token": raw_token,
    }


@router.post("/audits/{audit_id}/verification-tokens/{token_id}/revoke")
def revoke_verification_token(
    audit_id: uuid.UUID,
    token_id: str,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAuditVerificationToken).filter(
        QualityAuditVerificationToken.id == token_id,
        QualityAuditVerificationToken.amo_id == ctx.amo_id,
        QualityAuditVerificationToken.audit_id == audit_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Verification token not found.")
    if row.revoked_at is None:
        row.revoked_at = _utcnow()
        db.commit()
    return {"id": row.id, "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None}


def _public_verification_record(db: Session, raw_token: str) -> tuple[QualityAuditVerificationToken, models.QMSAudit, QualityAuditReportRevision, QualityAuditSignatureEvidence, QualityAuditAssuranceArtifact | None]:
    envelope = _decode_verification_token(raw_token)
    _set_public_tenant_context(db, amo_id=envelope["amo_id"], grant_id=f"verify:{envelope['token_id']}")
    row = db.query(QualityAuditVerificationToken).filter(
        QualityAuditVerificationToken.id == envelope["token_id"],
        QualityAuditVerificationToken.amo_id == envelope["amo_id"],
        QualityAuditVerificationToken.token_hash == hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        QualityAuditVerificationToken.revoked_at.is_(None),
        QualityAuditVerificationToken.expires_at > _utcnow(),
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Verification record not found.")
    audit = db.query(models.QMSAudit).filter(models.QMSAudit.amo_id == row.amo_id, models.QMSAudit.id == row.audit_id).first()
    report = db.query(QualityAuditReportRevision).filter(QualityAuditReportRevision.amo_id == row.amo_id, QualityAuditReportRevision.id == row.report_revision_id).first()
    signature = db.query(QualityAuditSignatureEvidence).filter(QualityAuditSignatureEvidence.amo_id == row.amo_id, QualityAuditSignatureEvidence.id == row.signature_evidence_id).first()
    assurance = None
    if row.assurance_artifact_id:
        assurance = db.query(QualityAuditAssuranceArtifact).filter(QualityAuditAssuranceArtifact.amo_id == row.amo_id, QualityAuditAssuranceArtifact.id == row.assurance_artifact_id).first()
    if audit is None or report is None or signature is None or report.status != "ISSUED" or report.sha256 != signature.artifact_sha256:
        raise HTTPException(status_code=409, detail="The governed verification chain is incomplete.")
    return row, audit, report, signature, assurance


@public_router.get("/audit-verification/{token}")
def verify_audit_artifact(token: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    row, audit, report, signature, assurance = _public_verification_record(db, token)
    row.last_verified_at = _utcnow()
    db.commit()
    return {
        "valid": True,
        "audit": {"audit_ref": audit.audit_ref, "title": audit.title},
        "report": {
            "revision_no": report.revision_no,
            "status": report.status,
            "filename": report.filename,
            "sha256": report.sha256,
            "issued_at": report.issued_at.isoformat() if report.issued_at else None,
        },
        "signature": {
            "method": signature.method,
            "purpose": signature.purpose,
            "signed_at": signature.signed_at.isoformat() if signature.signed_at else None,
            "credential_id_hash": signature.credential_id_hash,
            "ceremony_sha256": signature.ceremony_sha256,
        },
        "assurance_artifact": ({
            "artifact_type": assurance.artifact_type,
            "filename": assurance.filename,
            "sha256": assurance.sha256,
        } if assurance else None),
        "verification": {"expires_at": row.expires_at.isoformat()},
    }


@public_router.post("/audit-verification/{token}/compare-hash")
def compare_audit_artifact_hash(token: str, payload: HashCompare, db: Session = Depends(get_db)) -> dict[str, Any]:
    _, _, report, _, assurance = _public_verification_record(db, token)
    governed = assurance.sha256 if assurance else report.sha256
    supplied = payload.sha256.lower()
    return {"matches": hmac.compare_digest(governed, supplied), "governed_sha256": governed, "artifact_type": assurance.artifact_type if assurance else "AUDIT_REPORT"}
