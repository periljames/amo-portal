from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_integration_router import refresh_integration_link, verify_source_entity
from .workspace_router import (
    create_change_request as _create_change_request,
    update_change_request as _update_change_request,
)
from .workspace_service import is_control_user, require_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Changes"])

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "OPEN": {"ASSESSING", "REJECTED"},
    "ASSESSING": {"ACCEPTED", "REJECTED"},
    "ACCEPTED": {"IMPLEMENTING", "REJECTED"},
    "IMPLEMENTING": {"ASSESSING", "CLOSED"},
    "CLOSED": set(),
    "REJECTED": set(),
}
_RESOLVED_STATUSES = {"CLOSED", "RESOLVED", "READY", "COMPLETED", "WAIVED", "NOT_REQUIRED"}


def _live_change_links(
    db: Session,
    *,
    tenant,
    change_id: str,
) -> list[dm.DocumentIntegrationLink]:
    rows = (
        db.query(dm.DocumentIntegrationLink)
        .filter(
            dm.DocumentIntegrationLink.tenant_id == tenant.amo_id,
            dm.DocumentIntegrationLink.change_request_id == change_id,
        )
        .all()
    )
    for row in rows:
        try:
            refresh_integration_link(db, tenant, row)
        except HTTPException as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CHANGE_LINK_UNVERIFIED",
                    "message": (
                        f"{row.source_module} {row.entity_type} {row.entity_id} "
                        f"cannot be verified: {exc.detail}"
                    ),
                },
            ) from exc
    return rows


def validate_change_update(
    db: Session,
    *,
    tenant,
    row: dm.DocumentChangeRequest,
    payload: schemas.ChangeRequestUpdate,
) -> None:
    update = payload.model_dump(exclude_unset=True)
    next_status = str(update.get("status", row.status))
    if next_status != row.status:
        allowed = _ALLOWED_TRANSITIONS.get(row.status, set())
        if next_status not in allowed:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CHANGE_TRANSITION_INVALID",
                    "message": f"Change request cannot move from {row.status} to {next_status}.",
                    "allowed_statuses": sorted(allowed),
                },
            )

    resolution = str(update.get("resolution", row.resolution) or "").strip()
    if next_status in {"CLOSED", "REJECTED"} and not resolution:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CHANGE_RESOLUTION_REQUIRED",
                "message": f"A controlled resolution is required before the request is {next_status.lower()}.",
            },
        )

    if next_status != "CLOSED":
        return

    training_required = bool(update.get("training_impact_required", row.training_impact_required))
    qms_blocking = bool(update.get("qms_blocking", row.qms_blocking))
    links = _live_change_links(db, tenant=tenant, change_id=row.id)

    def resolved(module_names: set[str]) -> bool:
        return any(
            str(link.source_module or "").upper() in module_names
            and str(link.status_snapshot or "").upper() in _RESOLVED_STATUSES
            for link in links
        )

    if training_required and not resolved({"TRAINING", "TRAINING_AND_COMPETENCE"}):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CHANGE_TRAINING_NOT_RESOLVED",
                "message": "A live resolved Training link is required before this change can close.",
            },
        )
    if qms_blocking and not resolved({"QMS", "QUALITY", "QUALITY_AND_COMPLIANCE"}):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CHANGE_QMS_NOT_RESOLVED",
                "message": "A live resolved QMS link is required before this change can close.",
            },
        )
    unresolved_blocking = [
        link
        for link in links
        if link.blocking and str(link.status_snapshot or "").upper() not in _RESOLVED_STATUSES
    ]
    if unresolved_blocking:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CHANGE_INTEGRATION_BLOCKED",
                "message": "One or more linked module records still block closure.",
                "link_ids": [link.id for link in unresolved_blocking],
            },
        )


def _verify_change_source(db: Session, *, tenant, payload: schemas.ChangeRequestCreate) -> schemas.ChangeRequestCreate:
    source_module = str(payload.source_module or "DOCUMENT_CONTROL").strip().upper()
    entity_type = str(payload.source_entity_type or "").strip()
    entity_id = str(payload.source_entity_id or "").strip()
    if bool(entity_type) != bool(entity_id):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CHANGE_SOURCE_INCOMPLETE",
                "message": "Select a complete governed source record or leave the source record blank.",
            },
        )
    if not entity_type:
        return payload.model_copy(update={"source_module": source_module, "source_entity_type": None, "source_entity_id": None})
    if source_module in {"DOCUMENT_CONTROL", "READER_FEEDBACK"}:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CHANGE_SOURCE_NOT_DISCOVERABLE",
                "message": "Document Control and reader-feedback changes do not accept arbitrary source IDs. Use a governed portal source module or leave the source record blank.",
            },
        )
    verification = verify_source_entity(
        db,
        tenant=tenant,
        source_module=source_module,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata={},
    )
    return payload.model_copy(update={
        "source_module": source_module,
        "source_entity_type": verification["source_table"],
        "source_entity_id": entity_id,
    })


@router.post("/t/{tenant_slug}/change-requests", include_in_schema=False)
def create_role_appropriate_change_request(
    tenant_slug: str,
    payload: schemas.ChangeRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    if not is_control_user(current_user):
        payload = payload.model_copy(
            update={
                "source_module": "READER_FEEDBACK",
                "source_entity_type": None,
                "source_entity_id": None,
                "owner_user_id": None,
                "training_impact_required": False,
                "qms_blocking": False,
            }
        )
    else:
        payload = _verify_change_source(db, tenant=tenant, payload=payload)
    return _create_change_request(
        tenant_slug=tenant_slug,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )


@router.patch("/t/{tenant_slug}/change-requests/{change_id}", include_in_schema=False)
def update_change_request_with_guards(
    tenant_slug: str,
    change_id: str,
    payload: schemas.ChangeRequestUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = (
        db.query(dm.DocumentChangeRequest)
        .filter(
            dm.DocumentChangeRequest.tenant_id == tenant.amo_id,
            dm.DocumentChangeRequest.id == change_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Change request not found")
    validate_change_update(db, tenant=tenant, row=row, payload=payload)
    return _update_change_request(
        tenant_slug=tenant_slug,
        change_id=change_id,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )
