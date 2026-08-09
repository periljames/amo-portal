from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_read_db, get_write_db

from . import models
from .audit_checklist_execution_models import QualityAuditChecklistExecutionEvent, QualityAuditChecklistExecutionGovernance
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality audit checklist execution governance"])

CanonicalResponse = Literal["COMPLIANT", "NONCOMPLIANT", "OBSERVATION", "NOT_APPLICABLE", "NOT_VERIFIED"]


class ChecklistExecutionUpdate(BaseModel):
    canonical_response_status: CanonicalResponse
    auditor_notes: str | None = Field(default=None, max_length=12000)
    evidence_references: list[dict[str, Any] | str] = Field(default_factory=list, max_length=200)
    reason: str = Field(min_length=8, max_length=4000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_from_legacy(value: str | None) -> CanonicalResponse:
    normalized = str(value or "PENDING").upper()
    if normalized == "NON_CONFORMING":
        return "NONCOMPLIANT"
    if normalized in {"COMPLIANT", "OBSERVATION", "NOT_APPLICABLE"}:
        return normalized  # type: ignore[return-value]
    return "NOT_VERIFIED"


def _legacy_from_canonical(value: CanonicalResponse) -> str:
    if value == "NONCOMPLIANT":
        return "NON_CONFORMING"
    if value == "NOT_VERIFIED":
        return "PENDING"
    return value


def _item(db: Session, *, amo_id: str, audit_id: uuid.UUID, item_id: uuid.UUID) -> models.QualityAuditChecklistItem:
    row = db.query(models.QualityAuditChecklistItem).filter(
        models.QualityAuditChecklistItem.amo_id == amo_id,
        models.QualityAuditChecklistItem.audit_id == audit_id,
        models.QualityAuditChecklistItem.id == item_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit checklist item not found.")
    return row


def _governance_snapshot(row: QualityAuditChecklistExecutionGovernance) -> dict[str, Any]:
    return {
        "canonical_response_status": row.canonical_response_status,
        "auditor_notes": row.auditor_notes,
        "evidence_references": list(row.evidence_references or []),
        "updated_by_user_id": row.updated_by_user_id,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _event_dict(row: QualityAuditChecklistExecutionEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "event_type": row.event_type,
        "reason": row.reason,
        "before_snapshot": row.before_snapshot,
        "after_snapshot": row.after_snapshot,
        "actor_user_id": row.actor_user_id,
        "created_at": row.created_at,
    }


def _row_dict(item: models.QualityAuditChecklistItem, governance: QualityAuditChecklistExecutionGovernance | None) -> dict[str, Any]:
    canonical = governance.canonical_response_status if governance else _canonical_from_legacy(item.response_status)
    return {
        "checklist_item_id": str(item.id),
        "audit_id": str(item.audit_id),
        "section": item.section,
        "checklist_ref": item.checklist_ref,
        "requirement_ref": item.requirement_ref,
        "prompt": item.prompt,
        "legacy_response_status": item.response_status,
        "canonical_response_status": canonical,
        "objective_evidence": item.objective_evidence,
        "finding_id": str(item.finding_id) if item.finding_id else None,
        "auditor_notes": governance.auditor_notes if governance else None,
        "evidence_references": list(governance.evidence_references or []) if governance else [],
        "governance_id": str(governance.id) if governance else None,
        "updated_by_user_id": governance.updated_by_user_id if governance else item.completed_by_user_id,
        "updated_at": governance.updated_at if governance else item.updated_at,
        "events": [_event_dict(event) for event in list(governance.events or [])] if governance else [],
    }


@router.get("/audits/{audit_id}/checklist-execution-governance")
def list_checklist_execution_governance(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    items = db.query(models.QualityAuditChecklistItem).filter(
        models.QualityAuditChecklistItem.amo_id == ctx.amo_id,
        models.QualityAuditChecklistItem.audit_id == audit_id,
    ).order_by(models.QualityAuditChecklistItem.section.asc(), models.QualityAuditChecklistItem.sort_order.asc()).limit(1000).all()
    governance_rows = db.query(QualityAuditChecklistExecutionGovernance).options(
        selectinload(QualityAuditChecklistExecutionGovernance.events)
    ).filter(
        QualityAuditChecklistExecutionGovernance.amo_id == ctx.amo_id,
        QualityAuditChecklistExecutionGovernance.audit_id == audit_id,
    ).all()
    by_item = {row.checklist_item_id: row for row in governance_rows}
    return {
        "items": [_row_dict(item, by_item.get(item.id)) for item in items],
        "canonical_response_values": ["COMPLIANT", "NONCOMPLIANT", "OBSERVATION", "NOT_APPLICABLE", "NOT_VERIFIED"],
        "legacy_compatibility": {
            "NONCOMPLIANT": "NON_CONFORMING",
            "NOT_VERIFIED": "PENDING",
        },
    }


@router.patch("/audits/{audit_id}/checklist-items/{item_id}/execution-governance")
def update_checklist_execution_governance(
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ChecklistExecutionUpdate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    item = _item(db, amo_id=ctx.amo_id, audit_id=audit_id, item_id=item_id)
    governance = db.query(QualityAuditChecklistExecutionGovernance).options(
        selectinload(QualityAuditChecklistExecutionGovernance.events)
    ).filter(
        QualityAuditChecklistExecutionGovernance.amo_id == ctx.amo_id,
        QualityAuditChecklistExecutionGovernance.audit_id == audit_id,
        QualityAuditChecklistExecutionGovernance.checklist_item_id == item_id,
    ).with_for_update().first()

    event_type = "UPDATED"
    before_snapshot: dict[str, Any] | None
    if governance is None:
        event_type = "CREATED"
        before_snapshot = {
            "canonical_response_status": _canonical_from_legacy(item.response_status),
            "auditor_notes": None,
            "evidence_references": [],
            "legacy_response_status": item.response_status,
        }
        governance = QualityAuditChecklistExecutionGovernance(
            amo_id=ctx.amo_id,
            audit_id=audit_id,
            checklist_item_id=item_id,
            canonical_response_status=payload.canonical_response_status,
            auditor_notes=payload.auditor_notes.strip() if payload.auditor_notes else None,
            evidence_references=list(payload.evidence_references),
            updated_by_user_id=ctx.user_id,
        )
        db.add(governance)
        db.flush()
    else:
        before_snapshot = _governance_snapshot(governance)
        governance.canonical_response_status = payload.canonical_response_status
        governance.auditor_notes = payload.auditor_notes.strip() if payload.auditor_notes else None
        governance.evidence_references = list(payload.evidence_references)
        governance.updated_by_user_id = ctx.user_id
        governance.updated_at = _utcnow()

    legacy_status = _legacy_from_canonical(payload.canonical_response_status)
    item.response_status = legacy_status
    if payload.canonical_response_status == "NOT_VERIFIED":
        item.completed_by_user_id = None
        item.completed_at = None
    else:
        item.completed_by_user_id = ctx.user_id
        item.completed_at = _utcnow()
    item.updated_at = _utcnow()

    after_snapshot = {
        **_governance_snapshot(governance),
        "legacy_response_status": legacy_status,
        "objective_evidence": item.objective_evidence,
        "finding_id": str(item.finding_id) if item.finding_id else None,
    }
    event = QualityAuditChecklistExecutionEvent(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        checklist_item_id=item_id,
        governance_id=governance.id,
        event_type=event_type,
        reason=payload.reason.strip(),
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        actor_user_id=ctx.user_id,
    )
    db.add(event)
    db.commit()

    governance = db.query(QualityAuditChecklistExecutionGovernance).options(
        selectinload(QualityAuditChecklistExecutionGovernance.events)
    ).filter(QualityAuditChecklistExecutionGovernance.id == governance.id).one()
    return _row_dict(item, governance)
