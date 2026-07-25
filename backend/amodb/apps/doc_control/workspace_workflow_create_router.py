from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_router import create_workflow as _create_workflow
from .workspace_service import (
    get_manual,
    get_profile,
    get_revision,
    get_workflow,
    is_approver,
    require_control_user,
    resolve_tenant,
    serialize_workflow,
    status_value,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Workflow Creation"])
_OPEN_CHANGE_STATUSES = {"OPEN", "ASSESSING", "ACCEPTED", "IMPLEMENTING"}


def derive_initial_workflow_payload(
    db: Session,
    *,
    tenant,
    manual: manual_models.Manual,
    revision: manual_models.ManualRevision,
    payload: schemas.WorkflowCreate,
    current_user: account_models.User,
) -> schemas.WorkflowCreate:
    """Build the initial workflow state from controlled records, not form claims.

    A controller may declare an additional Training impact or authority requirement,
    but cannot clear a requirement already established by the document profile,
    open change requests, or linked module records. READY and WAIVED states are
    intentionally impossible at creation; they require later evidence-backed
    transition actions. Distribution readiness is owned by campaign issuance.
    """
    profile = get_profile(db, tenant, manual.id)
    changes = (
        db.query(dm.DocumentChangeRequest)
        .filter(
            dm.DocumentChangeRequest.tenant_id == tenant.amo_id,
            dm.DocumentChangeRequest.manual_id == manual.id,
            dm.DocumentChangeRequest.status.in_(_OPEN_CHANGE_STATUSES),
            or_(
                dm.DocumentChangeRequest.revision_id.is_(None),
                dm.DocumentChangeRequest.revision_id == revision.id,
            ),
        )
        .all()
    )
    links = (
        db.query(dm.DocumentIntegrationLink)
        .filter(
            dm.DocumentIntegrationLink.tenant_id == tenant.amo_id,
            dm.DocumentIntegrationLink.manual_id == manual.id,
            or_(
                dm.DocumentIntegrationLink.revision_id.is_(None),
                dm.DocumentIntegrationLink.revision_id == revision.id,
            ),
        )
        .all()
    )

    linked_modules = {str(link.source_module or "").upper() for link in links}
    training_required = bool(
        payload.training_impact_required
        or any(change.training_impact_required for change in changes)
        or linked_modules.intersection({"TRAINING", "TRAINING_AND_COMPETENCE"})
    )
    qms_required = bool(
        any(change.qms_blocking for change in changes)
        or linked_modules.intersection({"QMS", "QUALITY", "QUALITY_AND_COMPLIANCE"})
    )
    authority_required = bool(
        payload.requires_authority
        or (profile and profile.requires_authority_approval)
        or (profile and profile.regulated_flag)
    )
    acknowledgement_required = bool(profile and profile.acknowledgement_required)

    if payload.effective_at is not None and not is_approver(current_user):
        raise HTTPException(
            status_code=403,
            detail="Document approval privileges are required to schedule effectivity",
        )

    return payload.model_copy(
        update={
            "requires_authority": authority_required,
            "training_impact_required": training_required,
            "training_readiness_status": "PENDING" if training_required else "NOT_REQUIRED",
            "qms_readiness_status": "PENDING" if qms_required else "NOT_REQUIRED",
            "distribution_readiness_status": "PENDING" if acknowledgement_required else "NOT_REQUIRED",
        }
    )


@router.post("/t/{tenant_slug}/workflows", include_in_schema=False)
def create_derived_workflow(
    tenant_slug: str,
    payload: schemas.WorkflowCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    revision = get_revision(db, manual, payload.revision_id)
    if revision.immutable_locked or status_value(revision) in {
        "PUBLISHED",
        "SUPERSEDED",
        "ARCHIVED",
    }:
        raise HTTPException(
            status_code=409,
            detail="Published, superseded, or archived revisions cannot enter a new editable workflow",
        )

    existing = get_workflow(db, tenant, revision.id)
    if existing:
        return serialize_workflow(existing)

    derived = derive_initial_workflow_payload(
        db,
        tenant=tenant,
        manual=manual,
        revision=revision,
        payload=payload,
        current_user=current_user,
    )
    return _create_workflow(
        tenant_slug=tenant_slug,
        payload=derived,
        request=request,
        db=db,
        current_user=current_user,
    )
