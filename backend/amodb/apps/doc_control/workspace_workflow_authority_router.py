from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_service import resolve_tenant
from .workspace_workflow_router import transition_workflow_with_release_guards as _transition


router = APIRouter(prefix="/workspace", tags=["Document Control Workflow Authority"])


def _matching_submission(
    db: Session,
    *,
    tenant_id: str,
    revision_id: str,
    approved: bool,
) -> dm.DocumentAuthoritySubmission | None:
    statuses = ["APPROVED"] if approved else ["SUBMITTED", "IN_REVIEW", "QUERY_RECEIVED", "APPROVED"]
    rows = (
        db.query(dm.DocumentAuthoritySubmission)
        .filter(
            dm.DocumentAuthoritySubmission.tenant_id == tenant_id,
            dm.DocumentAuthoritySubmission.revision_id == revision_id,
            dm.DocumentAuthoritySubmission.status.in_(statuses),
        )
        .order_by(dm.DocumentAuthoritySubmission.updated_at.desc())
        .all()
    )
    for row in rows:
        if not list(row.evidence_json or []):
            continue
        if approved and not str(row.response_summary or "").strip():
            continue
        return row
    return None


@router.post(
    "/t/{tenant_slug}/workflows/{workflow_id}/transition",
    include_in_schema=False,
)
def transition_workflow_with_authority_alignment(
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

    if payload.action == "MARK_AUTHORITY_SUBMITTED":
        if not _matching_submission(
            db,
            tenant_id=tenant.amo_id,
            revision_id=workflow.revision_id,
            approved=False,
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "AUTHORITY_SUBMISSION_RECORD_REQUIRED",
                    "message": "Record an evidence-backed authority submission against this revision first.",
                },
            )

    if payload.action in {"MARK_AUTHORITY_APPROVED", "SCHEDULE_EFFECTIVITY"} and workflow.requires_authority:
        if not _matching_submission(
            db,
            tenant_id=tenant.amo_id,
            revision_id=workflow.revision_id,
            approved=True,
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "AUTHORITY_APPROVAL_RECORD_REQUIRED",
                    "message": "An approved authority submission with retained evidence and response reference is required.",
                },
            )

    return _transition(
        tenant_slug=tenant_slug,
        workflow_id=workflow_id,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )
