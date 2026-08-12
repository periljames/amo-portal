from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_copy_router import create_guarded_copy_event as _create_event
from .workspace_evidence_router import validate_evidence_references
from .workspace_service import require_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Controlled Copy Evidence"])


@router.post(
    "/t/{tenant_slug}/controlled-copies/{copy_id}/events",
    include_in_schema=False,
)
def create_copy_event_with_governed_evidence(
    tenant_slug: str,
    copy_id: str,
    payload: schemas.ControlledCopyEventCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = (
        db.query(dm.DocumentControlledCopy)
        .filter(
            dm.DocumentControlledCopy.tenant_id == tenant.amo_id,
            dm.DocumentControlledCopy.id == copy_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Controlled copy not found")
    normalized = validate_evidence_references(
        db,
        tenant_id=tenant.amo_id,
        manual_id=row.manual_id,
        evidence=list(payload.evidence or []),
    )
    payload = payload.model_copy(update={"evidence": normalized})
    return _create_event(
        tenant_slug=tenant_slug,
        copy_id=copy_id,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )
