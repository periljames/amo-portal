from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_router import (
    complete_review as _complete_review,
    create_review as _create_review,
)
from .workspace_service import (
    audit,
    get_manual,
    get_revision,
    require_control_user,
    resolve_tenant,
    utcnow,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Reviews"])
_OPEN_REVIEW_STATUSES = {"SCHEDULED", "IN_PROGRESS"}


def _effective_review_payload(
    db: Session,
    *,
    tenant,
    payload: schemas.ReviewPlanCreate,
) -> schemas.ReviewPlanCreate:
    manual = get_manual(db, tenant, payload.manual_id)
    effective_revision_id = manual.current_published_rev_id
    if not effective_revision_id:
        raise HTTPException(
            status_code=409,
            detail="A periodic review must be scheduled against the current published revision",
        )
    if payload.revision_id and payload.revision_id != effective_revision_id:
        raise HTTPException(
            status_code=409,
            detail="Periodic review must reference the current published revision",
        )
    get_revision(db, manual, effective_revision_id)
    if payload.due_at <= utcnow():
        raise HTTPException(
            status_code=422,
            detail="The next periodic review due date must be in the future",
        )
    existing = (
        db.query(dm.DocumentReviewPlan)
        .filter(
            dm.DocumentReviewPlan.tenant_id == tenant.amo_id,
            dm.DocumentReviewPlan.manual_id == manual.id,
            dm.DocumentReviewPlan.revision_id == effective_revision_id,
            dm.DocumentReviewPlan.status.in_(_OPEN_REVIEW_STATUSES),
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "OPEN_REVIEW_ALREADY_EXISTS",
                "message": "An open periodic review already exists for the effective revision.",
                "review_id": existing.id,
            },
        )
    return payload.model_copy(update={"revision_id": effective_revision_id})


def validate_review_completion(
    row: dm.DocumentReviewPlan,
    payload: schemas.ReviewCompleteRequest,
) -> None:
    if row.status not in _OPEN_REVIEW_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVIEW_ALREADY_CLOSED",
                "message": f"A review in {row.status} state cannot be completed again.",
            },
        )
    if payload.outcome != "CONTINUE" and not payload.findings:
        raise HTTPException(
            status_code=422,
            detail="A non-continuation review outcome requires at least one finding",
        )
    if payload.outcome != "CONTINUE" and not payload.actions:
        raise HTTPException(
            status_code=422,
            detail="A non-continuation review outcome requires at least one resulting action",
        )


def _create_review_follow_up(
    db: Session,
    *,
    tenant,
    row: dm.DocumentReviewPlan,
    payload: schemas.ReviewCompleteRequest,
    current_user: account_models.User,
    request: Request,
) -> dm.DocumentChangeRequest | None:
    if payload.outcome == "CONTINUE":
        return None
    existing = (
        db.query(dm.DocumentChangeRequest)
        .filter(
            dm.DocumentChangeRequest.tenant_id == tenant.amo_id,
            dm.DocumentChangeRequest.source_module == "DOCUMENT_CONTROL",
            dm.DocumentChangeRequest.source_entity_type == "PERIODIC_REVIEW",
            dm.DocumentChangeRequest.source_entity_id == row.id,
        )
        .first()
    )
    if existing:
        return existing

    finding_text = "; ".join(
        str(item.get("finding") or item.get("description") or item)
        for item in payload.findings
    )
    action_text = "; ".join(
        str(item.get("action") or item.get("description") or item)
        for item in payload.actions
    )
    change = dm.DocumentChangeRequest(
        tenant_id=tenant.amo_id,
        manual_id=row.manual_id,
        revision_id=row.revision_id,
        source_module="DOCUMENT_CONTROL",
        source_entity_type="PERIODIC_REVIEW",
        source_entity_id=row.id,
        title=f"Periodic review outcome: {payload.outcome.replace('_', ' ').title()}",
        description=(
            f"Findings: {finding_text}\nRequired actions: {action_text}"
        ),
        priority="HIGH" if payload.outcome in {"WITHDRAW", "SUPERSEDE"} else "NORMAL",
        status="OPEN",
        proposer_user_id=current_user.id,
        impact_json={"review_outcome": payload.outcome},
    )
    db.add(change)
    db.flush()
    audit(
        db,
        tenant,
        request,
        "document.change.created_from_review",
        "document_change_request",
        change.id,
        {"review_id": row.id, "outcome": payload.outcome},
    )
    return change


@router.post("/t/{tenant_slug}/reviews", include_in_schema=False)
def create_effective_revision_review(
    tenant_slug: str,
    payload: schemas.ReviewPlanCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    guarded = _effective_review_payload(db, tenant=tenant, payload=payload)
    return _create_review(
        tenant_slug=tenant_slug,
        payload=guarded,
        request=request,
        db=db,
        current_user=current_user,
    )


@router.post("/t/{tenant_slug}/reviews/{review_id}/complete", include_in_schema=False)
def complete_review_with_follow_up(
    tenant_slug: str,
    review_id: str,
    payload: schemas.ReviewCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = (
        db.query(dm.DocumentReviewPlan)
        .filter(
            dm.DocumentReviewPlan.tenant_id == tenant.amo_id,
            dm.DocumentReviewPlan.id == review_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Review plan not found")
    validate_review_completion(row, payload)

    result = _complete_review(
        tenant_slug=tenant_slug,
        review_id=review_id,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )
    follow_up = _create_review_follow_up(
        db,
        tenant=tenant,
        row=row,
        payload=payload,
        current_user=current_user,
        request=request,
    )
    if follow_up:
        db.commit()
        result["follow_up_change_request_id"] = follow_up.id
    return result
