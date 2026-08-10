from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_publication_distribution import ensure_automatic_publication_distribution
from .workspace_service import get_manual, get_revision, resolve_tenant
from .workspace_workflow_authority_router import (
    transition_workflow_with_authority_alignment as _transition,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Workflow Review Guards"])

_DECISION_EVIDENCE_ACTIONS = {
    "APPROVE_TECHNICAL",
    "APPROVE_QUALITY",
    "APPROVE_ACCOUNTABLE_MANAGER",
    "MARK_AUTHORITY_SUBMITTED",
    "MARK_AUTHORITY_APPROVED",
    "SCHEDULE_EFFECTIVITY",
    "PUBLISH",
    "ARCHIVE",
}
_EVIDENCE_REFERENCE_KEYS = {
    "asset_id",
    "attachment_id",
    "document_id",
    "evidence_id",
    "file_id",
    "reference",
    "reference_id",
    "submission_reference",
    "url",
    "checksum",
    "checksum_sha256",
}


def _has_retained_reference(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    for key in _EVIDENCE_REFERENCE_KEYS:
        value = item.get(key)
        if value is None or isinstance(value, bool):
            continue
        if str(value).strip():
            return True
    return False


def validate_decision_evidence(payload: schemas.WorkflowTransitionRequest) -> None:
    if payload.action not in _DECISION_EVIDENCE_ACTIONS:
        return
    comments = str(payload.comments or "").strip()
    evidence = list(payload.evidence or [])
    invalid_indexes = [
        index
        for index, item in enumerate(evidence)
        if not _has_retained_reference(item)
    ]
    if not comments or not evidence or invalid_indexes:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DECISION_EVIDENCE_REQUIRED",
                "message": (
                    "Approval, authority, publication, and archive decisions require "
                    "a recorded reason and retained evidence with an identifiable reference."
                ),
                "invalid_evidence_indexes": invalid_indexes,
            },
        )


def validate_publication_recipient_counts(
    *,
    total_recipients: int,
    active_recipients: int,
) -> None:
    if total_recipients <= 0:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Publication is blocked",
                "blockers": [
                    {
                        "code": "DISTRIBUTION_HAS_NO_ACTIVE_RECIPIENTS",
                        "message": (
                            "The issued campaign has no active, non-system tenant recipients. "
                            "Reissue distribution before publication."
                        ),
                    }
                ],
            },
        )
    if active_recipients != total_recipients:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Publication is blocked",
                "blockers": [
                    {
                        "code": "DISTRIBUTION_HAS_INVALID_RECIPIENTS",
                        "message": (
                            "Every issued campaign recipient must remain an active, non-system "
                            "user in the same tenant. Reissue distribution before publication."
                        ),
                        "total_recipients": total_recipients,
                        "active_recipients": active_recipients,
                    }
                ],
            },
        )


def validate_active_publication_recipients(
    db: Session,
    *,
    tenant_id: str,
    workflow: dm.DocumentWorkflowInstance,
) -> None:
    profile = (
        db.query(dm.DocumentControlProfile)
        .filter(
            dm.DocumentControlProfile.tenant_id == tenant_id,
            dm.DocumentControlProfile.manual_id == workflow.manual_id,
        )
        .first()
    )
    if not profile or not profile.acknowledgement_required:
        return

    campaign = (
        db.query(dm.DocumentDistributionCampaign)
        .filter(
            dm.DocumentDistributionCampaign.tenant_id == tenant_id,
            dm.DocumentDistributionCampaign.revision_id == workflow.revision_id,
            dm.DocumentDistributionCampaign.status.in_(["ISSUED", "COMPLETED"]),
        )
        .order_by(dm.DocumentDistributionCampaign.issued_at.desc())
        .first()
    )
    if not campaign:
        return

    total_recipients = (
        db.query(func.count(dm.DocumentDistributionRecipient.id))
        .filter(
            dm.DocumentDistributionRecipient.tenant_id == tenant_id,
            dm.DocumentDistributionRecipient.campaign_id == campaign.id,
        )
        .scalar()
        or 0
    )
    active_recipients = (
        db.query(func.count(dm.DocumentDistributionRecipient.id))
        .join(
            account_models.User,
            account_models.User.id == dm.DocumentDistributionRecipient.recipient_user_id,
        )
        .filter(
            dm.DocumentDistributionRecipient.tenant_id == tenant_id,
            dm.DocumentDistributionRecipient.campaign_id == campaign.id,
            account_models.User.amo_id == tenant_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .scalar()
        or 0
    )
    validate_publication_recipient_counts(
        total_recipients=int(total_recipients),
        active_recipients=int(active_recipients),
    )


@router.post(
    "/t/{tenant_slug}/workflows/{workflow_id}/transition",
    include_in_schema=False,
)
def transition_workflow_with_codex_review_guards(
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

    # This layer validates retained decision evidence only. Authorization is
    # deliberately enforced by ``require_workflow_action`` in the downstream
    # workflow router, where confirmed reviewer/approver responsibilities are
    # evaluated per action. Requiring the generic accountable-role policy here
    # would incorrectly block assigned technical and Quality reviewers.
    if payload.action in _DECISION_EVIDENCE_ACTIONS:
        validate_decision_evidence(payload)
    if payload.action == "PUBLISH":
        manual = get_manual(db, tenant, workflow.manual_id)
        revision = get_revision(db, manual, workflow.revision_id)
        ensure_automatic_publication_distribution(
            db,
            tenant_slug=tenant_slug,
            tenant=tenant,
            workflow=workflow,
            manual=manual,
            revision=revision,
            current_user=current_user,
            request=request,
        )
        validate_active_publication_recipients(
            db,
            tenant_id=tenant.amo_id,
            workflow=workflow,
        )

    return _transition(
        tenant_slug=tenant_slug,
        workflow_id=workflow_id,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )
