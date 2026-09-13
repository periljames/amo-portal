from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from amodb.database import get_read_db, get_write_db

from .excellence_models import QualityAssuranceControl
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(prefix="/excellence", tags=["Quality regulatory traceability"])

ApplicabilityStatus = Literal["APPLICABLE", "NOT_APPLICABLE", "PENDING_REVIEW"]
MappingStatus = Literal["MAPPED", "EXCEPTION", "NOT_ASSESSED", "PENDING"]


class ControlTraceabilityPatch(BaseModel):
    framework_version: str | None = Field(default=None, max_length=80)
    requirement_title: str | None = Field(default=None, max_length=255)
    requirement_source_reference: str | None = Field(default=None, max_length=500)
    requirement_effective_from: date | None = None
    requirement_effective_to: date | None = None
    applicability_status: ApplicabilityStatus | None = None
    applicability_rationale: str | None = Field(default=None, max_length=12000)
    mapping_status: MappingStatus | None = None

    @model_validator(mode="after")
    def validate_effective_window(self):
        if self.requirement_effective_from and self.requirement_effective_to:
            if self.requirement_effective_to < self.requirement_effective_from:
                raise ValueError("Requirement effective-to date cannot precede effective-from date.")
        if self.applicability_status == "NOT_APPLICABLE" and not (self.applicability_rationale or "").strip():
            raise ValueError("A not-applicable determination requires a rationale.")
        return self


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row(db: Session, *, ctx: TenantContext, control_id: str) -> QualityAssuranceControl:
    row = db.query(QualityAssuranceControl).filter(
        QualityAssuranceControl.id == control_id,
        QualityAssuranceControl.amo_id == ctx.amo_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Assurance control not found.")
    return row


def _serialize(row: QualityAssuranceControl) -> dict[str, object | None]:
    return {
        "control_id": row.id,
        "control_code": row.control_code,
        "framework": row.framework,
        "framework_version": row.framework_version,
        "clause_reference": row.clause_reference,
        "requirement_title": row.requirement_title,
        "requirement_source_reference": row.requirement_source_reference,
        "requirement_effective_from": row.requirement_effective_from.isoformat() if row.requirement_effective_from else None,
        "requirement_effective_to": row.requirement_effective_to.isoformat() if row.requirement_effective_to else None,
        "applicability_status": row.applicability_status,
        "applicability_rationale": row.applicability_rationale,
        "mapping_status": row.mapping_status,
        "control_version": row.version_no,
        "control_approval_status": row.approval_status,
        "updated_by_user_id": row.updated_by_user_id,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/controls/{control_id}/traceability")
def get_control_traceability(
    control_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.dashboard.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, object | None]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _serialize(_row(db, ctx=ctx, control_id=control_id))


@router.patch("/controls/{control_id}/traceability")
def update_control_traceability(
    control_id: str,
    payload: ControlTraceabilityPatch,
    ctx: TenantContext = Depends(require_quality_permission("qms.settings.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, object | None]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _row(db, ctx=ctx, control_id=control_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return _serialize(row)

    # Validate the resulting effective-date window, not only dates supplied in
    # the current patch.
    effective_from = changes.get("requirement_effective_from", row.requirement_effective_from)
    effective_to = changes.get("requirement_effective_to", row.requirement_effective_to)
    if effective_from and effective_to and effective_to < effective_from:
        raise HTTPException(status_code=422, detail="Requirement effective-to date cannot precede effective-from date.")
    applicability = changes.get("applicability_status", row.applicability_status)
    rationale = changes.get("applicability_rationale", row.applicability_rationale)
    if applicability == "NOT_APPLICABLE" and not str(rationale or "").strip():
        raise HTTPException(status_code=422, detail="A not-applicable determination requires a rationale.")

    if row.approval_status == "APPROVED":
        row.version_no = int(row.version_no or 1) + 1
        row.approval_status = "DRAFT"
        row.approved_by_user_id = None
        row.approved_at = None

    for field, value in changes.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(row, field, value)
    row.updated_by_user_id = ctx.user_id
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return _serialize(row)
