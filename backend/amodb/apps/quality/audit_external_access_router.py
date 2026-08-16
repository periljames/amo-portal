from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_db, get_read_db, get_write_db
from amodb.security import SECRET_KEY

from . import models
from .audit_checklist_execution_models import QualityAuditChecklistExecutionGovernance
from .audit_external_access_models import (
    QualityAuditAccessEvent,
    QualityAuditAccessGrant,
    QualityAuditFindingReleaseEvent,
    QualityAuditParticipant,
    QualityExternalIdentity,
)
from .audit_report_governance_models import QualityAuditReportRevision
from .router import public_router
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(tags=["Quality external audit access"])
_public_extension = APIRouter(prefix="/quality", tags=["Quality / External Audit Access"])
_GUEST_COOKIE = "amo_qms_audit_guest"
_TOKEN_VERSION = 1

AUDITEE_ALLOWED = {
    "audit:read_summary",
    "audit:read_progress",
    "audit:read_released_findings",
    "audit:read_released_evidence",
    "audit:document_submit",
    "audit:acknowledge",
    "car:respond",
}
EXTERNAL_AUDITOR_ALLOWED = {
    "audit:read_assigned",
    "audit:read_summary",
    "audit:read_progress",
    "audit:checklist_execute",
    "audit:evidence_create",
    "audit:finding_draft",
    "audit:report_contribute",
}
DEFAULT_SCOPE = {
    "AUDITEE_GUEST": {"audit:read_summary", "audit:read_released_findings", "audit:document_submit", "audit:acknowledge", "car:respond"},
    "EXTERNAL_AUDITOR": {"audit:read_assigned", "audit:read_summary"},
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value) or "")


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _token_signature(payload_segment: str) -> str:
    digest = hmac.new(SECRET_KEY.encode("utf-8"), payload_segment.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def _make_access_token(*, amo_id: str, grant_id: str, expires_at: datetime) -> str:
    payload = {
        "v": _TOKEN_VERSION,
        "t": str(amo_id),
        "g": str(grant_id),
        "e": int(expires_at.timestamp()),
        "n": secrets.token_urlsafe(32),
    }
    segment = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{segment}.{_token_signature(segment)}"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _decode_access_token(token: str) -> dict[str, Any]:
    clean = str(token or "").strip()
    if not clean or len(clean) > 2048 or clean.count(".") != 1:
        raise HTTPException(status_code=404, detail="Audit access is unavailable.")
    segment, signature = clean.split(".", 1)
    if not hmac.compare_digest(_token_signature(segment), signature):
        raise HTTPException(status_code=404, detail="Audit access is unavailable.")
    try:
        payload = json.loads(_b64decode(segment))
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Audit access is unavailable.") from exc
    if payload.get("v") != _TOKEN_VERSION:
        raise HTTPException(status_code=404, detail="Audit access is unavailable.")
    amo_id = str(payload.get("t") or "")
    grant_id = str(payload.get("g") or "")
    nonce = str(payload.get("n") or "")
    try:
        expires_epoch = int(payload.get("e"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Audit access is unavailable.") from exc
    if not amo_id or not grant_id or len(nonce) < 32 or expires_epoch <= int(time.time()):
        raise HTTPException(status_code=404, detail="Audit access is unavailable.")
    return {"amo_id": amo_id, "grant_id": grant_id, "expires_epoch": expires_epoch}


def _set_public_tenant_context(db: Session, *, amo_id: str, grant_id: str) -> None:
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(text("SELECT set_config('app.tenant_id', :amo_id, true)"), {"amo_id": str(amo_id)})
    db.execute(text("SELECT set_config('app.user_id', :actor, true)"), {"actor": f"external:{grant_id}"[:128]})


def _active_grant(db: Session, token: str) -> QualityAuditAccessGrant:
    envelope = _decode_access_token(token)
    _set_public_tenant_context(db, amo_id=envelope["amo_id"], grant_id=envelope["grant_id"])
    now = _utcnow()
    row = (
        db.query(QualityAuditAccessGrant)
        .filter(
            QualityAuditAccessGrant.id == envelope["grant_id"],
            QualityAuditAccessGrant.amo_id == envelope["amo_id"],
            QualityAuditAccessGrant.token_hash == _hash_token(token),
            QualityAuditAccessGrant.revoked_at.is_(None),
            QualityAuditAccessGrant.expires_at > now,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Audit access is unavailable.")
    participant = row.participant
    if participant is None or participant.status in {"REVOKED", "EXPIRED"} or participant.expires_at <= now:
        raise HTTPException(status_code=404, detail="Audit access is unavailable.")
    identity = participant.external_identity
    if participant.participant_type != "INTERNAL_USER" and (identity is None or identity.identity_status != "ACTIVE"):
        raise HTTPException(status_code=404, detail="Audit access is unavailable.")
    return row


def _append_access_event(db: Session, grant: QualityAuditAccessGrant, event_type: str, reason: str, actor_user_id: str | None = None) -> None:
    db.add(QualityAuditAccessEvent(
        amo_id=grant.amo_id,
        audit_id=grant.audit_id,
        grant_id=grant.id,
        participant_id=grant.participant_id,
        event_type=event_type,
        reason=reason,
        actor_user_id=actor_user_id,
    ))


class ExternalParticipantCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=2, max_length=255)
    organisation: str | None = Field(default=None, max_length=255)
    participant_type: Literal["EXTERNAL_AUDITOR", "AUDITEE_GUEST"]
    role: str = Field(min_length=2, max_length=48)
    permissions: list[str] | None = None
    assurance_level: Literal["EMAIL_LINK", "MFA", "PASSKEY"] = "EMAIL_LINK"
    expires_at: datetime


class FindingReleaseCreate(BaseModel):
    action: Literal["RELEASED", "WITHDRAWN"]
    include_objective_evidence: bool = False
    released_evidence_refs: list[dict[str, Any] | str] = Field(default_factory=list, max_length=100)
    reason: str = Field(min_length=3, max_length=2000)


class AuditAccessExchange(BaseModel):
    token: str = Field(min_length=32, max_length=2048)


def _normalise_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=422, detail="Provide a valid external participant email address.")
    return email


def _scope_for(payload: ExternalParticipantCreate) -> list[str]:
    allowed = AUDITEE_ALLOWED if payload.participant_type == "AUDITEE_GUEST" else EXTERNAL_AUDITOR_ALLOWED
    requested = set(payload.permissions or DEFAULT_SCOPE[payload.participant_type])
    unsupported = sorted(requested - allowed)
    if unsupported:
        raise HTTPException(status_code=422, detail={"message": "Unsupported external audit permission.", "permissions": unsupported})
    return sorted(requested)


def _audit_for_tenant(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> models.QMSAudit:
    row = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit not found.")
    return row


def _participant_payload(row: QualityAuditParticipant, *, include_access_url: str | None = None) -> dict[str, Any]:
    identity = row.external_identity
    active_grant = next((grant for grant in row.grants if grant.revoked_at is None and grant.expires_at > _utcnow()), None)
    return {
        "id": row.id,
        "audit_id": str(row.audit_id),
        "participant_type": row.participant_type,
        "role": row.role,
        "permissions": list(row.permissions_json or []),
        "status": row.status,
        "display_name": identity.display_name if identity else None,
        "email": identity.email if identity else None,
        "organisation": identity.organisation if identity else None,
        "assurance_level": identity.assurance_level if identity else None,
        "expires_at": row.expires_at.isoformat(),
        "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "active_grant": bool(active_grant),
        "access_url": include_access_url,
    }


@router.get("/audits/{audit_id}/external-participants")
def list_external_participants(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit_for_tenant(db, amo_id=ctx.amo_id, audit_id=audit_id)
    rows = db.query(QualityAuditParticipant).filter(
        QualityAuditParticipant.amo_id == ctx.amo_id,
        QualityAuditParticipant.audit_id == audit_id,
        QualityAuditParticipant.participant_type.in_(["EXTERNAL_AUDITOR", "AUDITEE_GUEST"]),
    ).order_by(QualityAuditParticipant.created_at.asc()).all()
    return {"items": [_participant_payload(row) for row in rows]}


@router.post("/audits/{audit_id}/external-participants", status_code=status.HTTP_201_CREATED)
def create_external_participant(
    audit_id: uuid.UUID,
    payload: ExternalParticipantCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit_for_tenant(db, amo_id=ctx.amo_id, audit_id=audit_id)
    now = _utcnow()
    expires_at = payload.expires_at.astimezone(timezone.utc) if payload.expires_at.tzinfo else payload.expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise HTTPException(status_code=422, detail="External participant expiry must be in the future.")

    email = _normalise_email(payload.email)
    identity = db.query(QualityExternalIdentity).filter(
        QualityExternalIdentity.amo_id == ctx.amo_id,
        QualityExternalIdentity.email == email,
    ).first()
    if identity is None:
        identity = QualityExternalIdentity(
            amo_id=ctx.amo_id,
            email=email,
            display_name=payload.display_name.strip(),
            organisation=payload.organisation.strip() if payload.organisation else None,
            identity_status="ACTIVE",
            assurance_level=payload.assurance_level,
            created_by_user_id=ctx.user_id,
        )
        db.add(identity)
        db.flush()
    elif identity.identity_status != "ACTIVE":
        raise HTTPException(status_code=409, detail="This external identity is revoked.")
    else:
        identity.display_name = payload.display_name.strip()
        identity.organisation = payload.organisation.strip() if payload.organisation else identity.organisation
        identity.assurance_level = payload.assurance_level

    existing = db.query(QualityAuditParticipant).filter(
        QualityAuditParticipant.amo_id == ctx.amo_id,
        QualityAuditParticipant.audit_id == audit_id,
        QualityAuditParticipant.external_identity_id == identity.id,
        QualityAuditParticipant.role == payload.role.strip(),
        QualityAuditParticipant.status.in_(["INVITED", "ACTIVE"]),
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="This external participant already has an active audit role.")

    scope = _scope_for(payload)
    participant = QualityAuditParticipant(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        participant_type=payload.participant_type,
        external_identity_id=identity.id,
        role=payload.role.strip(),
        permissions_json=scope,
        status="INVITED",
        invited_at=now,
        expires_at=expires_at,
        created_by_user_id=ctx.user_id,
    )
    db.add(participant)
    db.flush()

    grant = QualityAuditAccessGrant(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        participant_id=participant.id,
        token_hash="pending",
        scope_json=scope,
        expires_at=expires_at,
        created_by_user_id=ctx.user_id,
    )
    db.add(grant)
    db.flush()
    raw_token = _make_access_token(amo_id=ctx.amo_id, grant_id=grant.id, expires_at=expires_at)
    grant.token_hash = _hash_token(raw_token)
    _append_access_event(db, grant, "CREATED", "External audit access grant created.", ctx.user_id)
    db.commit()
    db.refresh(participant)

    access_url = f"/qms/audit-access/{quote(raw_token, safe='')}"
    return _participant_payload(participant, include_access_url=access_url)


@router.post("/audits/{audit_id}/external-participants/{participant_id}/revoke")
def revoke_external_participant(
    audit_id: uuid.UUID,
    participant_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAuditParticipant).filter(
        QualityAuditParticipant.amo_id == ctx.amo_id,
        QualityAuditParticipant.audit_id == audit_id,
        QualityAuditParticipant.id == participant_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit participant not found.")
    now = _utcnow()
    row.status = "REVOKED"
    row.revoked_at = now
    for grant in row.grants:
        if grant.revoked_at is None:
            grant.revoked_at = now
            _append_access_event(db, grant, "REVOKED", "External audit participant access revoked.", ctx.user_id)
    db.commit()
    db.refresh(row)
    return _participant_payload(row)


@router.post("/audits/{audit_id}/findings/{finding_id}/release")
def release_audit_finding(
    audit_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: FindingReleaseCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    finding = db.query(models.QMSAuditFinding).filter(
        models.QMSAuditFinding.amo_id == ctx.amo_id,
        models.QMSAuditFinding.audit_id == audit_id,
        models.QMSAuditFinding.id == finding_id,
    ).first()
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found.")
    event = QualityAuditFindingReleaseEvent(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        finding_id=finding_id,
        action=payload.action,
        include_objective_evidence=payload.include_objective_evidence,
        released_evidence_refs=payload.released_evidence_refs,
        reason=payload.reason.strip(),
        actor_user_id=ctx.user_id,
    )
    db.add(event)
    db.commit()
    return {
        "finding_id": str(finding_id),
        "action": event.action,
        "released_at": event.created_at.isoformat(),
        "include_objective_evidence": event.include_objective_evidence,
        "released_evidence_refs": event.released_evidence_refs,
    }


def _latest_release_events(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> dict[uuid.UUID, QualityAuditFindingReleaseEvent]:
    events = db.query(QualityAuditFindingReleaseEvent).filter(
        QualityAuditFindingReleaseEvent.amo_id == amo_id,
        QualityAuditFindingReleaseEvent.audit_id == audit_id,
    ).order_by(QualityAuditFindingReleaseEvent.created_at.asc()).all()
    latest: dict[uuid.UUID, QualityAuditFindingReleaseEvent] = {}
    for event in events:
        latest[event.finding_id] = event
    return latest


def _public_read_model(db: Session, grant: QualityAuditAccessGrant) -> dict[str, Any]:
    participant = grant.participant
    scope = set(grant.scope_json or [])
    audit = _audit_for_tenant(db, amo_id=grant.amo_id, audit_id=grant.audit_id)
    identity = participant.external_identity

    payload: dict[str, Any] = {
        "participant": {
            "display_name": identity.display_name if identity else None,
            "organisation": identity.organisation if identity else None,
            "participant_type": participant.participant_type,
            "role": participant.role,
            "expires_at": grant.expires_at.isoformat(),
        },
        "permissions": sorted(scope),
        "audit": {},
        "progress": None,
        "released_findings": [],
        "document_requests": [],
        "issued_report_available": False,
    }

    if "audit:read_summary" in scope or "audit:read_assigned" in scope:
        payload["audit"] = {
            "id": str(audit.id),
            "audit_ref": audit.audit_ref,
            "title": audit.title,
            "scope": audit.scope,
            "criteria": audit.criteria,
            "planned_start": audit.planned_start.isoformat() if audit.planned_start else None,
            "planned_end": audit.planned_end.isoformat() if audit.planned_end else None,
            "actual_start": audit.actual_start.isoformat() if audit.actual_start else None,
            "actual_end": audit.actual_end.isoformat() if audit.actual_end else None,
        }

    if "audit:read_progress" in scope:
        rows = db.query(QualityAuditChecklistExecutionGovernance).filter(
            QualityAuditChecklistExecutionGovernance.amo_id == grant.amo_id,
            QualityAuditChecklistExecutionGovernance.audit_id == grant.audit_id,
        ).all()
        total = len(rows)
        pending = sum(1 for row in rows if row.canonical_response_status == "NOT_VERIFIED")
        payload["progress"] = {
            "total": total,
            "completed": total - pending,
            "percent": int(round(((total - pending) / total) * 100)) if total else 0,
        }

    if "audit:read_released_findings" in scope:
        latest = _latest_release_events(db, amo_id=grant.amo_id, audit_id=grant.audit_id)
        released_ids = [finding_id for finding_id, event in latest.items() if event.action == "RELEASED"]
        findings = db.query(models.QMSAuditFinding).filter(
            models.QMSAuditFinding.amo_id == grant.amo_id,
            models.QMSAuditFinding.audit_id == grant.audit_id,
            models.QMSAuditFinding.id.in_(released_ids),
        ).order_by(models.QMSAuditFinding.created_at.asc()).all() if released_ids else []
        for finding in findings:
            release = latest[finding.id]
            payload["released_findings"].append({
                "id": str(finding.id),
                "finding_ref": finding.finding_ref,
                "finding_type": _enum_value(finding.finding_type),
                "severity": _enum_value(finding.severity),
                "level": _enum_value(finding.level),
                "requirement_ref": finding.requirement_ref,
                "description": finding.description,
                "objective_evidence": finding.objective_evidence if release.include_objective_evidence else None,
                "released_evidence_refs": release.released_evidence_refs if "audit:read_released_evidence" in scope else [],
                "acknowledged_at": finding.acknowledged_at.isoformat() if finding.acknowledged_at else None,
            })

    if "audit:document_submit" in scope:
        requests = db.query(models.QualityAuditDocumentRequest).filter(
            models.QualityAuditDocumentRequest.amo_id == grant.amo_id,
            models.QualityAuditDocumentRequest.audit_id == grant.audit_id,
        ).order_by(models.QualityAuditDocumentRequest.created_at.asc()).all()
        payload["document_requests"] = [{
            "id": str(row.id),
            "title": row.title,
            "description": row.description,
            "due_date": row.due_date.isoformat() if row.due_date else None,
            "status": row.status,
            "review_note": row.review_note,
            "submitted": bool(row.uploaded_at),
        } for row in requests]

    issued = db.query(QualityAuditReportRevision.id).filter(
        QualityAuditReportRevision.amo_id == grant.amo_id,
        QualityAuditReportRevision.audit_id == grant.audit_id,
        QualityAuditReportRevision.status == "ISSUED",
    ).first()
    payload["issued_report_available"] = issued is not None
    return payload


@_public_extension.post("/audit-access/exchange")
def exchange_audit_access(
    payload: AuditAccessExchange,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    grant = _active_grant(db, payload.token)
    now = _utcnow()
    grant.last_used_at = now
    participant = grant.participant
    if participant.accepted_at is None:
        participant.accepted_at = now
        participant.status = "ACTIVE"
    _append_access_event(db, grant, "EXCHANGED", "External audit invitation exchanged for an HTTP-only audit session.")
    db.commit()

    max_age = max(1, int((grant.expires_at - now).total_seconds()))
    response.set_cookie(
        key=_GUEST_COOKIE,
        value=payload.token,
        max_age=max_age,
        expires=max_age,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/quality/audit-access",
    )
    return _public_read_model(db, grant)


@_public_extension.get("/audit-access/session")
def get_audit_access_session(
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    grant = _active_grant(db, amo_qms_audit_guest)
    grant.last_used_at = _utcnow()
    _append_access_event(db, grant, "READ", "External audit released-data projection viewed.")
    db.commit()
    return _public_read_model(db, grant)


@_public_extension.post("/audit-access/findings/{finding_id}/acknowledge")
def acknowledge_released_finding(
    finding_id: uuid.UUID,
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    grant = _active_grant(db, amo_qms_audit_guest)
    if "audit:acknowledge" not in set(grant.scope_json or []):
        raise HTTPException(status_code=403, detail="This audit access does not permit acknowledgements.")
    latest = _latest_release_events(db, amo_id=grant.amo_id, audit_id=grant.audit_id).get(finding_id)
    if latest is None or latest.action != "RELEASED":
        raise HTTPException(status_code=404, detail="Released finding not found.")
    finding = db.query(models.QMSAuditFinding).filter(
        models.QMSAuditFinding.amo_id == grant.amo_id,
        models.QMSAuditFinding.audit_id == grant.audit_id,
        models.QMSAuditFinding.id == finding_id,
    ).first()
    if finding is None:
        raise HTTPException(status_code=404, detail="Released finding not found.")
    identity = grant.participant.external_identity
    finding.acknowledged_at = _utcnow()
    finding.acknowledged_by_name = identity.display_name if identity else "External participant"
    finding.acknowledged_by_email = identity.email if identity else None
    finding.acknowledged_by_user_id = None
    _append_access_event(db, grant, "ACKNOWLEDGED", f"Released finding {finding_id} acknowledged.")
    db.commit()
    return {"finding_id": str(finding.id), "acknowledged_at": finding.acknowledged_at.isoformat()}


@_public_extension.delete("/audit-access/session", status_code=204)
def end_audit_access_session(response: Response) -> Response:
    response.delete_cookie(_GUEST_COOKIE, path="/quality/audit-access", httponly=True, samesite="strict")
    return response


# Public CAR invite endpoints already live on public_router. External audit access
# is additive and is registered after the compatibility router is complete.
public_router.routes[0:0] = list(_public_extension.routes)
