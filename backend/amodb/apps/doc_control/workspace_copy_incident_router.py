from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from .workspace_router import _copy_payload
from .workspace_service import audit, require_control_user, resolve_tenant, utcnow


router = APIRouter(prefix="/workspace", tags=["Document Control Controlled Copy Incidents"])


class ControlledCopyIncidentIn(BaseModel):
    incident_type: Literal["DAMAGE", "LOSS"]
    reason: str = Field(min_length=4, max_length=2000)
    evidence: list[dict] = Field(min_length=1, max_length=50)


def _copy(db: Session, tenant_id: str, copy_id: str) -> dm.DocumentControlledCopy:
    row = db.query(dm.DocumentControlledCopy).filter(
        dm.DocumentControlledCopy.id == copy_id,
        dm.DocumentControlledCopy.tenant_id == tenant_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Controlled copy not found")
    return row


@router.get("/t/{tenant_slug}/controlled-copy-custodians")
def list_controlled_copy_custodians(
    tenant_slug: str,
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(account_models.User).filter(
        account_models.User.amo_id == tenant.amo_id,
        account_models.User.is_active.is_(True),
    )
    if q and q.strip():
        needle = f"%{q.strip()}%"
        query = query.filter(or_(
            account_models.User.full_name.ilike(needle),
            account_models.User.email.ilike(needle),
            account_models.User.staff_code.ilike(needle),
        ))
    rows = query.order_by(account_models.User.full_name.asc(), account_models.User.email.asc()).limit(limit).all()
    return [{
        "id": row.id,
        "name": row.full_name or row.email,
        "email": row.email,
        "staff_code": row.staff_code,
        "department_id": row.department_id,
    } for row in rows]


@router.post("/t/{tenant_slug}/controlled-copies/{copy_id}/incidents")
def record_controlled_copy_incident(
    tenant_slug: str,
    copy_id: str,
    payload: ControlledCopyIncidentIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _copy(db, tenant.amo_id, copy_id)
    if row.status == "DESTROYED":
        raise HTTPException(status_code=409, detail="Destroyed controlled copies cannot receive a new incident")

    before = _copy_payload(row)
    event = dm.DocumentControlledCopyEvent(
        tenant_id=tenant.amo_id,
        controlled_copy_id=row.id,
        event_type=payload.incident_type,
        actor_user_id=current_user.id,
        from_holder_user_id=row.holder_user_id,
        to_holder_user_id=None,
        from_location=row.location_text,
        to_location=row.location_text,
        reason=payload.reason.strip(),
        evidence_json=list(payload.evidence),
    )
    db.add(event)
    row.status = "WITHDRAWN"
    row.withdrawn_at = utcnow()
    metadata = dict(row.metadata_json or {})
    metadata["latest_incident"] = {
        "type": payload.incident_type,
        "reason": payload.reason.strip(),
        "recorded_at": utcnow().isoformat(),
        "recorded_by_user_id": str(current_user.id),
    }
    row.metadata_json = metadata
    audit(
        db,
        tenant,
        request,
        f"document.copy.{payload.incident_type.lower()}",
        "document_controlled_copy",
        row.id,
        {"before": before, "after": _copy_payload(row), "evidence": list(payload.evidence)},
    )
    db.commit()
    return _copy_payload(row)
