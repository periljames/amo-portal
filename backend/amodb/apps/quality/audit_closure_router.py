from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_read_db, get_write_db

from . import models
from .assurance_case_models import QualityAssuranceCase, QualityEffectivenessPlan
from .audit_closure_models import QualityAuditClosureEvent, QualityAuditClosureState
from .audit_report_governance_models import QualityAuditReportRevision
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality audit closure governance"])


class ClosureDecision(BaseModel):
    reason: str = Field(min_length=8, max_length=4000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _audit(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> models.QMSAudit:
    row = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit not found.")
    return row


def _contains_reference(value: Any, candidate_ids: set[str]) -> bool:
    if value is None:
        return False
    if isinstance(value, dict):
        return any(_contains_reference(item, candidate_ids) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_reference(item, candidate_ids) for item in value)
    text = str(value)
    return text in candidate_ids or any(candidate in text for candidate in candidate_ids if len(candidate) >= 8)


def _linked_records(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> dict[str, Any]:
    findings = db.query(models.QMSAuditFinding).filter(
        models.QMSAuditFinding.amo_id == amo_id,
        models.QMSAuditFinding.audit_id == audit_id,
    ).all()
    finding_ids = {str(item.id) for item in findings}
    cars = []
    if finding_ids:
        cars = db.query(models.CorrectiveActionRequest).filter(
            models.CorrectiveActionRequest.finding_id.in_(list(finding_ids))
        ).all()
    car_ids = {str(item.id) for item in cars}
    reference_ids = {str(audit_id), *finding_ids, *car_ids}

    plans = db.query(QualityEffectivenessPlan).filter(QualityEffectivenessPlan.amo_id == amo_id).limit(1000).all()
    relevant_plans = [
        item for item in plans
        if (item.source_id and str(item.source_id) in reference_ids)
        or (item.source_route and _contains_reference(item.source_route, reference_ids))
    ]

    cases = db.query(QualityAssuranceCase).filter(QualityAssuranceCase.amo_id == amo_id).limit(1000).all()
    relevant_cases = [item for item in cases if _contains_reference(item.source_references, reference_ids)]
    return {
        "findings": findings,
        "cars": cars,
        "plans": relevant_plans,
        "cases": relevant_cases,
        "reference_ids": sorted(reference_ids),
    }


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").upper()


def _follow_up_readiness(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> dict[str, Any]:
    linked = _linked_records(db, amo_id=amo_id, audit_id=audit_id)
    open_findings = [item for item in linked["findings"] if item.closed_at is None]
    open_cars = [item for item in linked["cars"] if _status_value(item.status) not in {"CLOSED", "CANCELLED"}]
    pending_effectiveness = [
        item for item in linked["plans"]
        if item.status != "CONCLUDED" or item.conclusion != "EFFECTIVE"
    ]
    open_cases = [item for item in linked["cases"] if item.status not in {"CLOSED", "CANCELLED"}]

    blockers: list[dict[str, Any]] = []
    blockers.extend({"type": "FINDING", "id": str(item.id), "ref": item.finding_ref, "reason": "Finding remains open."} for item in open_findings)
    blockers.extend({"type": "CAR", "id": str(item.id), "ref": item.car_number, "reason": f"CAR status is {_status_value(item.status)}."} for item in open_cars)
    blockers.extend({
        "type": "EFFECTIVENESS",
        "id": str(item.id),
        "ref": item.source_id,
        "reason": f"Effectiveness is {item.status} / {item.conclusion or 'NOT_CONCLUDED'}.",
    } for item in pending_effectiveness)
    blockers.extend({"type": "ASSURANCE_CASE", "id": str(item.id), "ref": item.case_ref, "reason": f"Assurance case status is {item.status}."} for item in open_cases)

    return {
        "ready": len(blockers) == 0,
        "blockers": blockers,
        "counts": {
            "findings_total": len(linked["findings"]),
            "findings_open": len(open_findings),
            "cars_total": len(linked["cars"]),
            "cars_open": len(open_cars),
            "effectiveness_total": len(linked["plans"]),
            "effectiveness_blocking": len(pending_effectiveness),
            "assurance_cases_total": len(linked["cases"]),
            "assurance_cases_open": len(open_cases),
        },
        "reference_ids": linked["reference_ids"],
        "captured_at": _utcnow().isoformat(),
    }


def _execution_readiness(db: Session, *, amo_id: str, audit: models.QMSAudit) -> dict[str, Any]:
    report_rows = db.query(QualityAuditReportRevision).filter(
        QualityAuditReportRevision.amo_id == amo_id,
        QualityAuditReportRevision.audit_id == audit.id,
    ).order_by(QualityAuditReportRevision.revision_no.desc()).all()
    issued = next((row for row in report_rows if row.status == "ISSUED"), None)
    governed_report_required = bool(report_rows)
    blockers: list[dict[str, Any]] = []
    if audit.actual_end is None:
        blockers.append({"type": "FIELDWORK", "reason": "Fieldwork has not been formally completed."})
    if governed_report_required and issued is None:
        blockers.append({"type": "REPORT", "reason": "Governed report revisions exist but none is ISSUED."})
    return {
        "ready": len(blockers) == 0,
        "blockers": blockers,
        "legacy_report_compatibility": not governed_report_required,
        "issued_report": {
            "id": str(issued.id),
            "revision_no": issued.revision_no,
            "sha256": issued.sha256,
            "issued_at": issued.issued_at.isoformat() if issued and issued.issued_at else None,
        } if issued else None,
        "authoritative_audit_status": _status_value(audit.status),
        "captured_at": _utcnow().isoformat(),
    }


def _state_dict(row: QualityAuditClosureState, *, execution_readiness: dict[str, Any], follow_up_readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "audit_id": str(row.audit_id),
        "execution_status": row.execution_status,
        "execution_closed_by_user_id": row.execution_closed_by_user_id,
        "execution_closed_at": row.execution_closed_at,
        "execution_close_reason": row.execution_close_reason,
        "execution_evidence_snapshot": row.execution_evidence_snapshot or {},
        "follow_up_status": row.follow_up_status,
        "follow_up_completed_by_user_id": row.follow_up_completed_by_user_id,
        "follow_up_completed_at": row.follow_up_completed_at,
        "follow_up_completion_reason": row.follow_up_completion_reason,
        "follow_up_evidence_snapshot": row.follow_up_evidence_snapshot or {},
        "execution_readiness": execution_readiness,
        "follow_up_readiness": follow_up_readiness,
        "events": [
            {
                "id": str(item.id),
                "event_type": item.event_type,
                "reason": item.reason,
                "evidence_snapshot": item.evidence_snapshot or {},
                "actor_user_id": item.actor_user_id,
                "created_at": item.created_at,
            }
            for item in list(row.events or [])
        ],
    }


def _ensure_state(db: Session, *, ctx: TenantContext, audit_id: uuid.UUID) -> QualityAuditClosureState:
    row = db.query(QualityAuditClosureState).filter(
        QualityAuditClosureState.amo_id == ctx.amo_id,
        QualityAuditClosureState.audit_id == audit_id,
    ).first()
    if row is None:
        row = QualityAuditClosureState(
            amo_id=ctx.amo_id,
            audit_id=audit_id,
            execution_status="OPEN",
            follow_up_status="OPEN",
            execution_evidence_snapshot={},
            follow_up_evidence_snapshot={},
            created_by_user_id=ctx.user_id,
        )
        db.add(row)
        db.flush()
    return row


def _add_event(db: Session, *, ctx: TenantContext, row: QualityAuditClosureState, event_type: str, reason: str, evidence: dict[str, Any]) -> None:
    db.add(QualityAuditClosureEvent(
        amo_id=ctx.amo_id,
        audit_id=row.audit_id,
        closure_state_id=row.id,
        event_type=event_type,
        reason=reason.strip(),
        evidence_snapshot=evidence,
        actor_user_id=ctx.user_id,
    ))


@router.get("/audits/{audit_id}/closure-state")
def get_audit_closure_state(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    row = db.query(QualityAuditClosureState).options(selectinload(QualityAuditClosureState.events)).filter(
        QualityAuditClosureState.amo_id == ctx.amo_id,
        QualityAuditClosureState.audit_id == audit_id,
    ).first()
    execution = _execution_readiness(db, amo_id=ctx.amo_id, audit=audit)
    follow_up = _follow_up_readiness(db, amo_id=ctx.amo_id, audit_id=audit_id)
    if row is None:
        return {
            "audit_id": str(audit_id),
            "execution_status": "OPEN",
            "follow_up_status": "OPEN",
            "execution_readiness": execution,
            "follow_up_readiness": follow_up,
            "events": [],
        }
    return _state_dict(row, execution_readiness=execution, follow_up_readiness=follow_up)


@router.post("/audits/{audit_id}/closure-state/execution-close")
def record_execution_closed(
    audit_id: uuid.UUID,
    payload: ClosureDecision,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    readiness = _execution_readiness(db, amo_id=ctx.amo_id, audit=audit)
    if not readiness["ready"]:
        raise HTTPException(status_code=409, detail={"message": "Audit execution closure is not ready.", **readiness})
    row = _ensure_state(db, ctx=ctx, audit_id=audit_id)
    if row.execution_status == "CLOSED":
        raise HTTPException(status_code=409, detail="Audit execution closure has already been recorded.")
    row.execution_status = "CLOSED"
    row.execution_closed_by_user_id = ctx.user_id
    row.execution_closed_at = _utcnow()
    row.execution_close_reason = payload.reason.strip()
    row.execution_evidence_snapshot = readiness
    row.updated_at = _utcnow()
    _add_event(db, ctx=ctx, row=row, event_type="EXECUTION_CLOSED", reason=payload.reason, evidence=readiness)
    db.commit()
    loaded = db.query(QualityAuditClosureState).options(selectinload(QualityAuditClosureState.events)).filter(QualityAuditClosureState.id == row.id).one()
    return _state_dict(loaded, execution_readiness=readiness, follow_up_readiness=_follow_up_readiness(db, amo_id=ctx.amo_id, audit_id=audit_id))


@router.post("/audits/{audit_id}/closure-state/follow-up-complete")
def record_follow_up_complete(
    audit_id: uuid.UUID,
    payload: ClosureDecision,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    row = _ensure_state(db, ctx=ctx, audit_id=audit_id)
    if row.execution_status != "CLOSED":
        raise HTTPException(status_code=409, detail="Audit execution must be formally closed before assurance follow-up can be completed.")
    readiness = _follow_up_readiness(db, amo_id=ctx.amo_id, audit_id=audit_id)
    if not readiness["ready"]:
        raise HTTPException(status_code=409, detail={"message": "Assurance follow-up remains open.", **readiness})
    if row.follow_up_status == "COMPLETE":
        raise HTTPException(status_code=409, detail="Assurance follow-up is already complete.")
    row.follow_up_status = "COMPLETE"
    row.follow_up_completed_by_user_id = ctx.user_id
    row.follow_up_completed_at = _utcnow()
    row.follow_up_completion_reason = payload.reason.strip()
    row.follow_up_evidence_snapshot = readiness
    row.updated_at = _utcnow()
    audit.status = models.QMSAuditStatus.CLOSED
    _add_event(db, ctx=ctx, row=row, event_type="FOLLOW_UP_COMPLETED", reason=payload.reason, evidence=readiness)
    db.commit()
    loaded = db.query(QualityAuditClosureState).options(selectinload(QualityAuditClosureState.events)).filter(QualityAuditClosureState.id == row.id).one()
    return _state_dict(loaded, execution_readiness=_execution_readiness(db, amo_id=ctx.amo_id, audit=audit), follow_up_readiness=readiness)


@router.post("/audits/{audit_id}/closure-state/reopen-follow-up")
def reopen_follow_up(
    audit_id: uuid.UUID,
    payload: ClosureDecision,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    row = db.query(QualityAuditClosureState).filter(
        QualityAuditClosureState.amo_id == ctx.amo_id,
        QualityAuditClosureState.audit_id == audit_id,
    ).with_for_update().first()
    if row is None or row.follow_up_status != "COMPLETE":
        raise HTTPException(status_code=409, detail="Only completed assurance follow-up may be reopened.")
    evidence = _follow_up_readiness(db, amo_id=ctx.amo_id, audit_id=audit_id)
    row.follow_up_status = "OPEN"
    row.follow_up_completed_by_user_id = None
    row.follow_up_completed_at = None
    row.follow_up_completion_reason = None
    row.follow_up_evidence_snapshot = evidence
    row.updated_at = _utcnow()
    audit.status = models.QMSAuditStatus.CAP_OPEN if evidence["counts"]["findings_total"] else models.QMSAuditStatus.IN_PROGRESS
    _add_event(db, ctx=ctx, row=row, event_type="FOLLOW_UP_REOPENED", reason=payload.reason, evidence=evidence)
    db.commit()
    loaded = db.query(QualityAuditClosureState).options(selectinload(QualityAuditClosureState.events)).filter(QualityAuditClosureState.id == row.id).one()
    return _state_dict(loaded, execution_readiness=_execution_readiness(db, amo_id=ctx.amo_id, audit=audit), follow_up_readiness=evidence)
