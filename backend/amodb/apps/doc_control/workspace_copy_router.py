from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_router import create_copy_event as _create_copy_event
from .workspace_service import active_tenant_users, require_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Controlled Copies"])

_ALLOWED_EVENTS: dict[str, set[str]] = {
    "ISSUED": {"TRANSFER", "LOCATION_CHANGE", "RECALL", "RETURN", "WITHDRAW", "DESTROY"},
    "RECALLED": {"RETURN", "WITHDRAW", "DESTROY"},
    "RETURNED": {"WITHDRAW", "DESTROY"},
    "WITHDRAWN": {"DESTROY"},
    "DESTROYED": set(),
}


def validate_copy_event(row: dm.DocumentControlledCopy, payload: schemas.ControlledCopyEventCreate) -> None:
    event_type = payload.event_type
    allowed = _ALLOWED_EVENTS.get(row.status, set())
    if event_type not in allowed:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONTROLLED_COPY_EVENT_INVALID",
                "message": f"{event_type} is not valid while copy {row.copy_number} is {row.status}.",
                "allowed_events": sorted(allowed),
            },
        )

    reason = str(payload.reason or "").strip()
    evidence = list(payload.evidence or [])
    if event_type in {"WITHDRAW", "DESTROY"} and (not reason or not evidence):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "COPY_DISPOSITION_EVIDENCE_REQUIRED",
                "message": "Withdrawal or destruction requires a reason and retained evidence.",
            },
        )
    if event_type == "RECALL" and not reason:
        raise HTTPException(status_code=409, detail="A controlled-copy recall requires a reason")
    if event_type == "TRANSFER":
        if not payload.to_holder_user_id and not str(payload.to_location or "").strip():
            raise HTTPException(
                status_code=422,
                detail="A transfer requires a new active tenant holder or a new controlled location",
            )
        if (
            payload.to_holder_user_id == row.holder_user_id
            and str(payload.to_location or "").strip() == str(row.location_text or "").strip()
        ):
            raise HTTPException(status_code=409, detail="The transfer does not change holder or location")
    if event_type == "LOCATION_CHANGE":
        new_location = str(payload.to_location or "").strip()
        if not new_location:
            raise HTTPException(status_code=422, detail="A location change requires the new controlled location")
        if new_location == str(row.location_text or "").strip():
            raise HTTPException(status_code=409, detail="The controlled copy is already at that location")


@router.post(
    "/t/{tenant_slug}/controlled-copies/{copy_id}/events",
    include_in_schema=False,
)
def create_guarded_copy_event(
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

    validate_copy_event(row, payload)
    if payload.event_type == "TRANSFER" and payload.to_holder_user_id:
        active_tenant_users(db, tenant, [payload.to_holder_user_id])

    return _create_copy_event(
        tenant_slug=tenant_slug,
        copy_id=copy_id,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )
