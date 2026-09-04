from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db, get_read_db, get_write_db

from . import models
from .audit_external_access_router import _GUEST_COOKIE, _active_grant, _utcnow
from .audit_presence_models import QualityAuditPresence
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(tags=["Quality audit collaboration presence"])
public_router = APIRouter(prefix="/quality/audit-access", tags=["Quality / Audit Collaboration Presence"])
PRESENCE_TTL_SECONDS = 60


class PresenceHeartbeat(BaseModel):
    route: str | None = Field(default=None, max_length=128)


def _value(value: object | None) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value) or "") or None


def _require_internal_presence_access(db: Session, *, ctx: TenantContext, audit_id: uuid.UUID):
    from . import router as quality_router

    audit = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == ctx.amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit occurrence not found.")
    user = db.query(account_models.User).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.id == ctx.user_id,
        account_models.User.is_active.is_(True),
    ).first()
    if user is None:
        raise HTTPException(status_code=403, detail="Active internal Quality identity is required.")
    if not quality_router._is_quality_admin(user) and not quality_router._audit_allows_user_by_audit(audit, user.id):
        raise HTTPException(status_code=403, detail="Audit presence is limited to the assigned audit team and Quality management.")
    return user


def _row_dict(row: QualityAuditPresence) -> dict[str, Any]:
    return {
        "id": row.id,
        "actor_type": row.actor_type,
        "display_name": row.display_name,
        "role": row.role,
        "route": row.route,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
    }


def _upsert(
    db: Session,
    *,
    amo_id: str,
    audit_id: uuid.UUID,
    actor_type: str,
    actor_key: str,
    display_name: str,
    role: str | None,
    route: str | None,
    user_id: str | None = None,
    participant_id: str | None = None,
) -> QualityAuditPresence:
    row = db.query(QualityAuditPresence).filter(
        QualityAuditPresence.amo_id == amo_id,
        QualityAuditPresence.audit_id == audit_id,
        QualityAuditPresence.actor_key == actor_key,
    ).with_for_update().first()
    now = _utcnow()
    if row is None:
        row = QualityAuditPresence(
            amo_id=amo_id,
            audit_id=audit_id,
            actor_type=actor_type,
            actor_key=actor_key,
            user_id=user_id,
            participant_id=participant_id,
            display_name=display_name,
            role=role,
            route=route,
            last_seen_at=now,
        )
        db.add(row)
    else:
        row.display_name = display_name
        row.role = role
        row.route = route
        row.last_seen_at = now
    return row


@router.post("/audits/{audit_id}/presence/heartbeat")
def heartbeat_internal_audit_presence(
    audit_id: uuid.UUID,
    payload: PresenceHeartbeat,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    user = _require_internal_presence_access(db, ctx=ctx, audit_id=audit_id)
    display_name = str(getattr(user, "full_name", None) or getattr(user, "email", None) or ctx.user_id)
    role = _value(getattr(user, "role", None)) or str(getattr(user, "position_title", None) or "Audit team")
    row = _upsert(
        db,
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        actor_type="INTERNAL_USER",
        actor_key=f"user:{ctx.user_id}",
        user_id=ctx.user_id,
        display_name=display_name,
        role=role,
        route=(payload.route or "").strip() or None,
    )
    db.commit()
    return _row_dict(row)


@router.get("/audits/{audit_id}/presence")
def list_internal_audit_presence(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _require_internal_presence_access(db, ctx=ctx, audit_id=audit_id)
    cutoff = _utcnow() - timedelta(seconds=PRESENCE_TTL_SECONDS)
    rows = db.query(QualityAuditPresence).filter(
        QualityAuditPresence.amo_id == ctx.amo_id,
        QualityAuditPresence.audit_id == audit_id,
        QualityAuditPresence.last_seen_at >= cutoff,
    ).order_by(QualityAuditPresence.actor_type.asc(), QualityAuditPresence.display_name.asc()).all()
    return {"ttl_seconds": PRESENCE_TTL_SECONDS, "items": [_row_dict(row) for row in rows]}


@public_router.post("/presence/heartbeat")
def heartbeat_guest_audit_presence(
    payload: PresenceHeartbeat,
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    grant = _active_grant(db, amo_qms_audit_guest)
    participant = grant.participant
    if participant is None:
        raise HTTPException(status_code=404, detail="Audit participant not found.")
    # Guest presence is opt-in through the existing purpose-bound progress scope.
    # This lets an audit manager omit the scope when viewing presence is not an
    # appropriate expectation for the auditee or external participant.
    if "audit:read_progress" not in set(grant.scope_json or []):
        return {"recorded": False, "reason": "presence_not_permitted_by_grant"}
    identity = participant.external_identity
    display_name = str(identity.display_name if identity else participant.role or "Audit participant")
    row = _upsert(
        db,
        amo_id=grant.amo_id,
        audit_id=grant.audit_id,
        actor_type=participant.participant_type,
        actor_key=f"participant:{participant.id}",
        participant_id=participant.id,
        display_name=display_name,
        role=participant.role,
        route=(payload.route or "").strip() or None,
    )
    db.commit()
    return {"recorded": True, "presence": _row_dict(row)}
