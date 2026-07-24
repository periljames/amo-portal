from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_router import transition_workflow as _transition_workflow
from .workspace_service import (
    get_profile,
    is_approver,
    require_approver,
    resolve_tenant,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Workflow"])
_OPEN_CHANGE_STATUSES = {"OPEN", "ASSESSING", "ACCEPTED", "IMPLEMENTING"}
_RESOLVED_LINK_STATUSES = {"CLOSED", "RESOLVED", "READY", "COMPLETED", "WAIVED", "NOT_REQUIRED"}


def _resolved_integration_exists(
    db: Session,
    *,
    tenant_id: str,
    workflow_id: str,
    modules: set[str],
) -> bool:
    normalized_modules = {value.upper() for value in modules}
    rows = (
        db.query(dm.DocumentIntegrationLink)
        .filter(
            dm.DocumentIntegrationLink.tenant_id == tenant_id,
            dm.DocumentIntegrationLink.workflow_id == workflow_id,
        )
        .all()
    )
    return any(
        str(row.source_module or "").upper() in normalized_modules
        and str(row.status_snapshot or "").upper() in _RESOLVED_LINK_STATUSES
        for row in rows
    )


def _validate_readiness_change(
    db: Session,
    *,
    workflow: dm.DocumentWorkflowInstance,
    payload: schemas.WorkflowTransitionRequest,
    current_user: account_models.User,
) -> None:
    proposed = {
        "training": payload.training_readiness_status,
        "qms": payload.qms_readiness_status,
        "distribution": payload.distribution_readiness_status,
    }
    if not any(value is not None for value in proposed.values()):
        return

    require_approver(current_user)
    comments = str(payload.comments or "").strip()
    evidence = list(payload.evidence or [])

    if proposed["distribution"] == "READY":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DISTRIBUTION_READY_IS_SYSTEM_MANAGED",
                "message": "Issue a real distribution campaign; readiness cannot be marked ready manually.",
            },
        )

    if proposed["training"] == "READY" and not _resolved_integration_exists(
        db,
        tenant_id=workflow.tenant_id,
        workflow_id=workflow.id,
        modules={"TRAINING", "TRAINING_AND_COMPETENCE"},
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TRAINING_LINK_NOT_READY",
                "message": "A resolved Training integration link is required before training readiness can be marked ready.",
            },
        )

    if proposed["qms"] == "READY" and not _resolved_integration_exists(
        db,
        tenant_id=workflow.tenant_id,
        workflow_id=workflow.id,
        modules={"QMS", "QUALITY", "QUALITY_AND_COMPLIANCE"},
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "QMS_LINK_NOT_READY",
                "message": "A resolved QMS integration link is required before QMS readiness can be marked ready.",
            },
        )

    if any(value == "WAIVED" for value in proposed.values() if value is not None):
        if not comments or not evidence:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "WAIVER_EVIDENCE_REQUIRED",
                    "message": "A waiver requires a reason and supporting evidence.",
                },
            )


def _publication_blockers(
    db: Session,
    *,
    workflow: dm.DocumentWorkflowInstance,
) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []

    open_changes = (
        db.query(func.count(dm.DocumentChangeRequest.id))
        .filter(
            dm.DocumentChangeRequest.tenant_id == workflow.tenant_id,
            dm.DocumentChangeRequest.manual_id == workflow.manual_id,
            dm.DocumentChangeRequest.status.in_(_OPEN_CHANGE_STATUSES),
        )
        .scalar()
        or 0
    )
    if open_changes:
        blockers.append(
            {
                "code": "OPEN_CHANGE_REQUESTS",
                "message": f"{int(open_changes)} unresolved change request(s) remain open.",
            }
        )

    if workflow.requires_authority:
        approved_authority = (
            db.query(dm.DocumentAuthoritySubmission)
            .filter(
                dm.DocumentAuthoritySubmission.tenant_id == workflow.tenant_id,
                dm.DocumentAuthoritySubmission.revision_id == workflow.revision_id,
                dm.DocumentAuthoritySubmission.status == "APPROVED",
            )
            .order_by(dm.DocumentAuthoritySubmission.approved_at.desc())
            .first()
        )
        if not approved_authority:
            blockers.append(
                {
                    "code": "AUTHORITY_NOT_APPROVED",
                    "message": "Authority approval is required before publication.",
                }
            )
        elif not list(approved_authority.evidence_json or []):
            blockers.append(
                {
                    "code": "AUTHORITY_EVIDENCE_MISSING",
                    "message": "The approved authority submission has no retained evidence.",
                }
            )

    profile = get_profile_by_workflow(db, workflow)
    if profile and profile.acknowledgement_required:
        campaign = (
            db.query(dm.DocumentDistributionCampaign)
            .filter(
                dm.DocumentDistributionCampaign.tenant_id == workflow.tenant_id,
                dm.DocumentDistributionCampaign.revision_id == workflow.revision_id,
                dm.DocumentDistributionCampaign.status.in_(["ISSUED", "COMPLETED"]),
            )
            .order_by(dm.DocumentDistributionCampaign.issued_at.desc())
            .first()
        )
        if not campaign:
            blockers.append(
                {
                    "code": "DISTRIBUTION_NOT_ISSUED",
                    "message": "An issued distribution campaign is required for this revision.",
                }
            )
        else:
            recipients = (
                db.query(func.count(dm.DocumentDistributionRecipient.id))
                .filter(dm.DocumentDistributionRecipient.campaign_id == campaign.id)
                .scalar()
                or 0
            )
            if recipients == 0:
                blockers.append(
                    {
                        "code": "DISTRIBUTION_HAS_NO_RECIPIENTS",
                        "message": "The issued distribution campaign has no active tenant recipients.",
                    }
                )

    return blockers


def get_profile_by_workflow(
    db: Session,
    workflow: dm.DocumentWorkflowInstance,
) -> dm.DocumentControlProfile | None:
    return (
        db.query(dm.DocumentControlProfile)
        .filter(
            dm.DocumentControlProfile.tenant_id == workflow.tenant_id,
            dm.DocumentControlProfile.manual_id == workflow.manual_id,
        )
        .first()
    )


@router.post(
    "/t/{tenant_slug}/workflows/{workflow_id}/transition",
    include_in_schema=False,
)
def transition_workflow_with_release_guards(
    tenant_slug: str,
    workflow_id: str,
    payload: schemas.WorkflowTransitionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    workflow = (
        db.query(dm.DocumentWorkflowInstance)
        .filter(
            dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id,
            dm.DocumentWorkflowInstance.id == workflow_id,
        )
        .first()
    )
    if not workflow:
        raise HTTPException(status_code=404, detail="Document workflow not found")

    _validate_readiness_change(
        db,
        workflow=workflow,
        payload=payload,
        current_user=current_user,
    )

    if payload.effective_at is not None and not is_approver(current_user):
        raise HTTPException(
            status_code=403,
            detail="Document approval privileges are required to schedule effectivity",
        )

    if payload.action == "PUBLISH":
        require_approver(current_user)
        blockers = _publication_blockers(db, workflow=workflow)
        if blockers:
            raise HTTPException(
                status_code=409,
                detail={"message": "Publication is blocked", "blockers": blockers},
            )

    return _transition_workflow(
        tenant_slug=tenant_slug,
        workflow_id=workflow_id,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )
