from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_router import update_authority_submission as _update_authority_submission
from .workspace_service import require_approver, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Authority"])

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"SUBMITTED", "WITHDRAWN"},
    "SUBMITTED": {"IN_REVIEW", "QUERY_RECEIVED", "APPROVED", "REJECTED", "WITHDRAWN"},
    "IN_REVIEW": {"QUERY_RECEIVED", "APPROVED", "REJECTED", "WITHDRAWN"},
    "QUERY_RECEIVED": {"SUBMITTED", "IN_REVIEW", "APPROVED", "REJECTED", "WITHDRAWN"},
    "APPROVED": set(),
    "REJECTED": set(),
    "WITHDRAWN": set(),
}


def validate_authority_update(
    row: dm.DocumentAuthoritySubmission,
    payload: schemas.AuthoritySubmissionUpdate,
) -> None:
    if payload.status != row.status:
        allowed = _ALLOWED_TRANSITIONS.get(row.status, set())
        if payload.status not in allowed:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "AUTHORITY_TRANSITION_INVALID",
                    "message": f"Authority submission cannot move from {row.status} to {payload.status}.",
                    "allowed_statuses": sorted(allowed),
                },
            )

    resulting_evidence = (
        list(payload.evidence)
        if payload.evidence is not None
        else list(row.evidence_json or [])
    )
    response_summary = str(payload.response_summary or row.response_summary or "").strip()

    if payload.status == "SUBMITTED" and not resulting_evidence:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "AUTHORITY_SUBMISSION_EVIDENCE_REQUIRED",
                "message": "Submission evidence is required before authority status can be marked submitted.",
            },
        )
    if payload.status == "QUERY_RECEIVED" and not response_summary:
        raise HTTPException(
            status_code=409,
            detail="The authority query or response summary must be recorded",
        )
    if payload.status == "APPROVED":
        if not resulting_evidence:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "AUTHORITY_APPROVAL_EVIDENCE_REQUIRED",
                    "message": "Authority approval evidence is required before approval can be recorded.",
                },
            )
        if not response_summary:
            raise HTTPException(
                status_code=409,
                detail="The authority approval reference or response summary must be recorded",
            )
    if payload.status in {"REJECTED", "WITHDRAWN"} and not response_summary:
        raise HTTPException(
            status_code=409,
            detail=f"A reason is required when an authority submission is {payload.status.lower()}",
        )


@router.patch(
    "/t/{tenant_slug}/authority-submissions/{submission_id}",
    include_in_schema=False,
)
def update_authority_submission_with_guards(
    tenant_slug: str,
    submission_id: str,
    payload: schemas.AuthoritySubmissionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_approver(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = (
        db.query(dm.DocumentAuthoritySubmission)
        .filter(
            dm.DocumentAuthoritySubmission.tenant_id == tenant.amo_id,
            dm.DocumentAuthoritySubmission.id == submission_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Authority submission not found")

    validate_authority_update(row, payload)
    return _update_authority_submission(
        tenant_slug=tenant_slug,
        submission_id=submission_id,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )
