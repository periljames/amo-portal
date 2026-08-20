from __future__ import annotations

from datetime import date, timedelta
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.apps.audit import services as audit_services
from amodb.database import get_read_db, get_write_db

from . import models
from .planner_schedule_models import QMSPlannerScheduleMetadata
from .planner_schedule_router import (
    PlannerAuditScheduleResponse,
    _Candidate,
    _assert_version,
    _collect_conflicts,
    _enforce_conflicts,
    _metadata_for_schedule,
    _notify_schedule_change,
    _schedule_response,
    _schedule_user_ids,
)
from .router import _audit_metadata
from .tenant_security import (
    TenantContext,
    assert_quality_permission,
    require_quality_permission,
    set_postgres_tenant_context,
)


router = APIRouter(tags=["Quality authoritative planner schedules"])


class PlannerScheduleDateChange(BaseModel):
    expected_version: int = Field(ge=1)
    new_date: date
    reason: str = Field(min_length=8, max_length=1000)
    allow_conflicts: bool = False
    conflict_override_reason: str | None = Field(default=None, max_length=1000)


def _missing_metadata_error(schedule_ids: list[str]) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "message": "One or more audit schedules have not been reconciled into the authoritative Planner metadata model.",
            "schedule_ids": schedule_ids,
            "required_action": "Apply the planner metadata backfill migration before using the modern Planner.",
        },
    )


@router.get(
    "/integrations/calendar/audit-schedules",
    response_model=list[PlannerAuditScheduleResponse],
)
def list_planner_audit_schedules(
    active: bool | None = Query(default=None),
    limit: int = Query(default=250, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100_000),
    ctx: TenantContext = Depends(require_quality_permission("qms.calendar.view")),
    db: Session = Depends(get_read_db),
) -> list[PlannerAuditScheduleResponse]:
    """Return only schedules backed by the authoritative Planner metadata model."""

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(models.QMSAuditSchedule).filter(
        models.QMSAuditSchedule.amo_id == ctx.amo_id,
        models.QMSAuditSchedule.deleted_at.is_(None),
    )
    if active is not None:
        query = query.filter(models.QMSAuditSchedule.is_active.is_(active))
    schedules = (
        query.order_by(models.QMSAuditSchedule.next_due_date.asc(), models.QMSAuditSchedule.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    if not schedules:
        return []

    schedule_ids = [schedule.id for schedule in schedules]
    metadata_rows = db.query(QMSPlannerScheduleMetadata).filter(
        QMSPlannerScheduleMetadata.amo_id == ctx.amo_id,
        QMSPlannerScheduleMetadata.schedule_id.in_(schedule_ids),
    ).all()
    metadata_by_schedule = {
        str(row.schedule_id): row
        for row in metadata_rows
        if row.schedule_id is not None
    }
    missing = [
        str(schedule.id)
        for schedule in schedules
        if str(schedule.id) not in metadata_by_schedule
    ]
    if missing:
        raise _missing_metadata_error(missing)

    return [
        _schedule_response(schedule, metadata_by_schedule[str(schedule.id)])
        for schedule in schedules
    ]


@router.patch(
    "/integrations/calendar/audit-schedules/{schedule_id}/date",
    response_model=PlannerAuditScheduleResponse,
)
def change_planner_audit_schedule_date(
    schedule_id: uuid.UUID,
    payload: PlannerScheduleDateChange,
    request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.calendar.view")),
    db: Session = Depends(get_write_db),
) -> PlannerAuditScheduleResponse:
    """Move an audit schedule without rewriting unrelated schedule metadata.

    Date-only legacy schedules can therefore be reconciled and moved without
    inventing a start time. Version and conflict checks remain mandatory.
    """

    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    schedule = db.query(models.QMSAuditSchedule).filter(
        models.QMSAuditSchedule.amo_id == ctx.amo_id,
        models.QMSAuditSchedule.id == schedule_id,
        models.QMSAuditSchedule.deleted_at.is_(None),
    ).with_for_update().first()
    metadata = _metadata_for_schedule(
        db,
        amo_id=ctx.amo_id,
        schedule_id=schedule_id,
        lock=True,
    )
    if schedule is None:
        raise HTTPException(status_code=404, detail="Audit schedule not found")
    if metadata is None:
        raise _missing_metadata_error([str(schedule_id)])

    _assert_version(metadata, payload.expected_version)
    if payload.new_date == schedule.next_due_date:
        raise HTTPException(status_code=422, detail="Choose a different schedule date.")
    if payload.allow_conflicts and len((payload.conflict_override_reason or "").strip()) < 8:
        raise HTTPException(
            status_code=422,
            detail="A conflict override reason of at least 8 characters is required.",
        )

    end_date = payload.new_date + timedelta(days=max(int(schedule.duration_days or 1), 1) - 1)
    candidate = _Candidate(
        subject_type="AUDIT_SCHEDULE",
        subject_id=str(schedule.id),
        title=schedule.title,
        start_date=payload.new_date,
        end_date=end_date,
        start_time=metadata.start_time,
        end_time=metadata.end_time,
        location=metadata.location,
        user_ids=_schedule_user_ids(schedule, metadata),
    )
    conflicts = _collect_conflicts(
        db,
        amo_id=ctx.amo_id,
        candidate=candidate,
        exclude_schedule_id=str(schedule.id),
    )
    _enforce_conflicts(conflicts, allow=payload.allow_conflicts)

    old_date = schedule.next_due_date
    before = {
        "next_due_date": old_date.isoformat(),
        "end_date": metadata.end_date.isoformat() if metadata.end_date else None,
        "version": int(metadata.version or 1),
    }
    schedule.next_due_date = payload.new_date
    metadata.occurrence_date = payload.new_date
    metadata.end_date = end_date
    metadata.version = int(metadata.version or 1) + 1
    metadata.updated_by_user_id = ctx.user_id

    audit_services.log_event(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        entity_type="qms_audit_schedule",
        entity_id=str(schedule.id),
        action="planner_date_rescheduled",
        before=before,
        after={
            "next_due_date": payload.new_date.isoformat(),
            "end_date": end_date.isoformat(),
            "version": metadata.version,
            "reason": payload.reason.strip(),
            "conflict_override_reason": payload.conflict_override_reason if conflicts else None,
            "conflicts": [item.model_dump(mode="json") for item in conflicts],
        },
        correlation_id=f"qms-planner-date:{schedule.id}:{metadata.version}",
        metadata=_audit_metadata(request),
        critical=True,
    )
    notifications_queued = _notify_schedule_change(
        db,
        schedule=schedule,
        metadata=metadata,
        state="rescheduled",
        reason=payload.reason.strip(),
    )
    db.commit()
    db.refresh(schedule)
    db.refresh(metadata)
    return _schedule_response(
        schedule,
        metadata,
        notifications_queued=notifications_queued,
        conflicts=conflicts,
    )
