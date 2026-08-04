from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.database import get_write_db

from .assurance_wiring_router import (
    ApprovalDecision,
    ControlCreate,
    create_control,
    decide_control_approval,
)
from .excellence_models import QualityAssuranceControl
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(prefix="/excellence", tags=["Quality assurance lifecycle"])

_ALLOWED_APPROVAL_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"PENDING_APPROVAL"},
    "REJECTED": {"PENDING_APPROVAL", "RETIRED"},
    "PENDING_APPROVAL": {"APPROVED", "REJECTED"},
    "APPROVED": {"RETIRED"},
    "RETIRED": set(),
}


@router.post("/controls", status_code=status.HTTP_201_CREATED)
def create_draft_control(
    payload: ControlCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.settings.manage")),
    db: Session = Depends(get_write_db),
):
    """Create controls only as drafts.

    Approval and activation are attributable decisions, so API clients may not
    manufacture an approved control by setting lifecycle fields in the initial
    payload. The normal submit and approval endpoints remain the only path to an
    approved active control.
    """

    if payload.status != "DRAFT" or payload.approval_status != "DRAFT":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New assurance controls must start in DRAFT status and DRAFT approval state.",
        )
    return create_control(payload=payload, ctx=ctx, db=db)


@router.post("/controls/{control_id}/approval")
def transition_control_approval(
    control_id: str,
    payload: ApprovalDecision,
    ctx: TenantContext = Depends(require_quality_permission("qms.settings.manage")),
    db: Session = Depends(get_write_db),
):
    """Apply an explicit, attributable control-approval transition."""

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    control = (
        db.query(QualityAssuranceControl)
        .filter(
            QualityAssuranceControl.id == control_id,
            QualityAssuranceControl.amo_id == ctx.amo_id,
        )
        .first()
    )
    if not control:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assurance control not found.")

    current = str(control.approval_status or "DRAFT").upper()
    requested = payload.approval_status
    allowed = _ALLOWED_APPROVAL_TRANSITIONS.get(current, set())
    if requested not in allowed:
        allowed_label = ", ".join(sorted(allowed)) if allowed else "no further transitions"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid control approval transition {current} -> {requested}. Allowed: {allowed_label}.",
        )

    return decide_control_approval(control_id=control_id, payload=payload, ctx=ctx, db=db)
