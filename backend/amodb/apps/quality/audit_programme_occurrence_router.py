from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.database import get_read_db, get_write_db

from .audit_programme_models import QualityAuditProgramme, QualityAuditProgrammeEvent, QualityAuditProgrammeItem
from .audit_programme_occurrence_models import QualityAuditProgrammeOccurrenceLink
from .audit_source_link_models import QualityAuditSourceLink
from .enums import QMSAuditScheduleFrequency
from .intelligence_models import QualitySignalObservation, QualitySignalRule
from .planner_assignment_guard_router import create_guarded_planner_audit_schedule
from .planner_schedule_models import QMSPlannerScheduleMetadata
from .planner_schedule_router import PlannerAuditScheduleCreate, PlannerAuditScheduleResponse
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context

router = APIRouter(tags=["Quality audit programme custom occurrences"])
OccurrenceType = Literal["CUSTOM", "RISK_TRIGGERED"]


class ProgrammeOccurrenceCreate(BaseModel):
    occurrence_key: str = Field(min_length=3, max_length=160)
    rationale: str = Field(min_length=8, max_length=4000)
    signal_id: str | None = Field(default=None, max_length=36)
    schedule: PlannerAuditScheduleCreate


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _link_dict(row: QualityAuditProgrammeOccurrenceLink) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "programme_id": row.programme_id,
        "programme_item_id": row.programme_item_id,
        "schedule_id": str(row.schedule_id),
        "occurrence_type": row.occurrence_type,
        "occurrence_key": row.occurrence_key,
        "source_signal_id": row.source_signal_id,
        "rationale": row.rationale,
        "source_snapshot": row.source_snapshot or {},
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
    }


def _programme_item(db: Session, *, amo_id: str, programme_id: str, item_id: str) -> tuple[QualityAuditProgramme, QualityAuditProgrammeItem]:
    programme = db.query(QualityAuditProgramme).filter(
        QualityAuditProgramme.amo_id == amo_id,
        QualityAuditProgramme.id == programme_id,
    ).first()
    item = db.query(QualityAuditProgrammeItem).filter(
        QualityAuditProgrammeItem.amo_id == amo_id,
        QualityAuditProgrammeItem.programme_id == programme_id,
        QualityAuditProgrammeItem.id == item_id,
    ).first()
    if programme is None or item is None:
        raise HTTPException(status_code=404, detail="Audit programme requirement not found.")
    return programme, item


def _validate_window(programme: QualityAuditProgramme, item: QualityAuditProgrammeItem, payload: PlannerAuditScheduleCreate) -> None:
    if programme.status not in {"APPROVED", "ACTIVE"}:
        raise HTTPException(status_code=409, detail="Only APPROVED or ACTIVE programme revisions may create occurrences.")
    if item.state not in {"PLANNED", "SCHEDULED"}:
        raise HTTPException(status_code=409, detail=f"Programme requirement in state {item.state} cannot create another occurrence.")
    if payload.frequency != QMSAuditScheduleFrequency.ONE_TIME:
        raise HTTPException(status_code=422, detail="Custom and risk-triggered programme occurrences must be authoritative ONE_TIME Planner schedules.")
    end_date = payload.next_due_date + timedelta(days=payload.duration_days - 1)
    if payload.next_due_date < programme.period_start or end_date > programme.period_end:
        raise HTTPException(status_code=422, detail="Occurrence falls outside the approved programme period.")
    if item.target_start and payload.next_due_date < item.target_start:
        raise HTTPException(status_code=422, detail="Occurrence begins before the governed programme-item target window.")
    if item.target_end and end_date > item.target_end:
        raise HTTPException(status_code=422, detail="Occurrence ends after the governed programme-item target window.")


def _signal(db: Session, *, amo_id: str, signal_id: str) -> tuple[QualitySignalObservation, QualitySignalRule | None]:
    row = db.query(QualitySignalObservation).filter(
        QualitySignalObservation.amo_id == amo_id,
        QualitySignalObservation.id == signal_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Quality intelligence signal not found.")
    if not row.triggered or row.state == "CLOSED":
        raise HTTPException(status_code=409, detail="Risk-triggered programme occurrence requires an open triggered signal.")
    rule = db.query(QualitySignalRule).filter(
        QualitySignalRule.amo_id == amo_id,
        QualitySignalRule.id == row.rule_id,
    ).first()
    return row, rule


def _signal_snapshot(signal: QualitySignalObservation, rule: QualitySignalRule | None) -> dict[str, Any]:
    return {
        "signal_id": str(signal.id),
        "rule_code": rule.rule_code if rule else None,
        "metric": signal.metric,
        "observed_value": str(signal.observed_value),
        "threshold": str(signal.threshold),
        "operator": signal.operator,
        "severity": signal.severity,
        "explanation": signal.explanation,
        "source_snapshot": signal.source_snapshot or {},
        "source_references": signal.source_references or [],
        "state": signal.state,
    }


@router.get("/audit-programmes/{programme_id}/occurrence-links")
def list_programme_occurrence_links(
    programme_id: str,
    programme_item_id: str | None = Query(default=None),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    programme = db.query(QualityAuditProgramme.id).filter(
        QualityAuditProgramme.amo_id == ctx.amo_id,
        QualityAuditProgramme.id == programme_id,
    ).first()
    if programme is None:
        raise HTTPException(status_code=404, detail="Audit programme not found.")
    query = db.query(QualityAuditProgrammeOccurrenceLink).filter(
        QualityAuditProgrammeOccurrenceLink.amo_id == ctx.amo_id,
        QualityAuditProgrammeOccurrenceLink.programme_id == programme_id,
    )
    if programme_item_id:
        query = query.filter(QualityAuditProgrammeOccurrenceLink.programme_item_id == programme_item_id)
    rows = query.order_by(QualityAuditProgrammeOccurrenceLink.created_at.asc()).limit(500).all()
    schedule_ids = [row.schedule_id for row in rows]
    metadata = {
        str(row.schedule_id): row
        for row in db.query(QMSPlannerScheduleMetadata).filter(
            QMSPlannerScheduleMetadata.amo_id == ctx.amo_id,
            QMSPlannerScheduleMetadata.schedule_id.in_(schedule_ids),
        ).all()
    } if schedule_ids else {}
    return {
        "items": [
            {**_link_dict(row), "lifecycle_status": metadata.get(str(row.schedule_id)).lifecycle_status if str(row.schedule_id) in metadata else None}
            for row in rows
        ]
    }


@router.post(
    "/audit-programmes/{programme_id}/items/{item_id}/occurrences/{occurrence_type}",
    response_model=PlannerAuditScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_programme_occurrence(
    programme_id: str,
    item_id: str,
    occurrence_type: OccurrenceType,
    payload: ProgrammeOccurrenceCreate,
    request: Request,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerAuditScheduleResponse:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    programme, item = _programme_item(db, amo_id=ctx.amo_id, programme_id=programme_id, item_id=item_id)
    recurrence = str(item.recurrence or "").upper()
    if recurrence != occurrence_type:
        raise HTTPException(
            status_code=409,
            detail={"message": "Occurrence type must match the governed programme recurrence.", "programme_recurrence": recurrence, "requested_occurrence_type": occurrence_type},
        )
    _validate_window(programme, item, payload.schedule)
    key = payload.occurrence_key.strip()
    existing = db.query(QualityAuditProgrammeOccurrenceLink.id).filter(
        QualityAuditProgrammeOccurrenceLink.amo_id == ctx.amo_id,
        QualityAuditProgrammeOccurrenceLink.programme_item_id == item.id,
        QualityAuditProgrammeOccurrenceLink.occurrence_key == key,
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="This governed occurrence key is already linked to a Planner schedule.")

    signal: QualitySignalObservation | None = None
    rule: QualitySignalRule | None = None
    source_snapshot: dict[str, Any] = {
        "programme_id": str(programme.id),
        "programme_item_id": str(item.id),
        "recurrence": recurrence,
        "target_start": item.target_start.isoformat() if item.target_start else None,
        "target_end": item.target_end.isoformat() if item.target_end else None,
    }
    if occurrence_type == "RISK_TRIGGERED":
        if not payload.signal_id:
            raise HTTPException(status_code=422, detail="RISK_TRIGGERED occurrence requires signal_id.")
        signal, rule = _signal(db, amo_id=ctx.amo_id, signal_id=payload.signal_id)
        signal_duplicate = db.query(QualityAuditProgrammeOccurrenceLink.id).filter(
            QualityAuditProgrammeOccurrenceLink.amo_id == ctx.amo_id,
            QualityAuditProgrammeOccurrenceLink.programme_item_id == item.id,
            QualityAuditProgrammeOccurrenceLink.source_signal_id == str(signal.id),
        ).first()
        if signal_duplicate is not None:
            raise HTTPException(status_code=409, detail="This signal already generated an occurrence for the programme requirement.")
        source_snapshot["signal"] = _signal_snapshot(signal, rule)
    elif payload.signal_id:
        raise HTTPException(status_code=422, detail="CUSTOM occurrence must not supply signal_id.")

    schedule = create_guarded_planner_audit_schedule(payload=payload.schedule, request=request, ctx=ctx, db=db)
    now = _utcnow()
    link = QualityAuditProgrammeOccurrenceLink(
        amo_id=ctx.amo_id,
        programme_id=programme.id,
        programme_item_id=item.id,
        schedule_id=schedule.id,
        occurrence_type=occurrence_type,
        occurrence_key=key,
        source_signal_id=str(signal.id) if signal else None,
        rationale=payload.rationale.strip(),
        source_snapshot=source_snapshot,
        created_by_user_id=ctx.user_id,
        created_at=now,
    )
    db.add(link)
    if signal is not None:
        db.add(QualityAuditSourceLink(
            amo_id=ctx.amo_id,
            schedule_id=schedule.id,
            source_type="SIGNAL",
            source_id=str(signal.id),
            source_route=f"/maintenance/{ctx.amo_code}/quality?workspace=intelligence&signal={signal.id}",
            rationale=payload.rationale.strip(),
            source_snapshot=_signal_snapshot(signal, rule),
            created_by_user_id=ctx.user_id,
            created_at=now,
        ))
    if item.state == "PLANNED":
        item.state = "SCHEDULED"
        item.scheduled_by_user_id = ctx.user_id
        item.scheduled_at = now
        item.updated_by_user_id = ctx.user_id
        item.updated_at = now
    db.add(QualityAuditProgrammeEvent(
        amo_id=ctx.amo_id,
        programme_id=programme.id,
        event_type="ITEM_SCHEDULED",
        reason=f"{occurrence_type} programme occurrence {key} linked to an authoritative ONE_TIME Planner schedule.",
        before_snapshot={"programme_item_id": str(item.id), "recurrence": recurrence},
        after_snapshot={"schedule_id": str(schedule.id), "occurrence_type": occurrence_type, "occurrence_key": key, "source_signal_id": str(signal.id) if signal else None},
        actor_user_id=ctx.user_id,
        created_at=now,
    ))
    db.commit()
    return schedule
