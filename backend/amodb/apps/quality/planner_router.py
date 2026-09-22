from __future__ import annotations

from datetime import date, datetime, time, timedelta
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_read_db, get_write_db

from . import models
from .audit_occurrence_completion_models import QualityAuditMeeting
from .audit_schedule_rules import (
    BUSINESS_CLOSE,
    BUSINESS_OPEN,
    DEFAULT_END_TIME,
    DEFAULT_START_TIME,
    suggest_working_slots,
)
from .canonical_core_router import _log_qms_activity
from .planner_schedule_router import (
    _Candidate,
    _audit_user_ids,
    _collect_conflicts,
    _metadata_for_audit,
    _metadata_for_schedule,
    _schedule_user_ids,
    _validate_conflict_override,
)
from .schedule_weekend import resolve_schedule_window
from .tenant_security import (
    TenantContext,
    assert_quality_permission,
    has_quality_permission,
    require_quality_permission,
    set_postgres_tenant_context,
)


planner_router = APIRouter()
logger = logging.getLogger("amodb.quality.planner")


class CalendarRescheduleRequest(BaseModel):
    event_id: str = Field(min_length=5, max_length=320)
    new_date: date
    expected_old_date: date | None = None
    reason: str = Field(min_length=8, max_length=1000)
    weekend_policy: str | None = Field(
        default=None,
        description="Required when the moved occurrence spans Saturday/Sunday.",
    )
    start_time: time | None = None
    end_time: time | None = None
    allow_conflicts: bool = False
    conflict_override_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _validate_conflict_override_fields(self) -> "CalendarRescheduleRequest":
        try:
            _validate_conflict_override(self.allow_conflicts, self.conflict_override_reason)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("End time must be later than start time.")
        return self


class CalendarRescheduleResponse(BaseModel):
    event_id: str
    old_date: date
    new_date: date
    end_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    trace_id: str


class PlannerCapabilitiesResponse(BaseModel):
    can_reschedule: bool
    can_create_audit: bool
    can_manage_training: bool
    user_id: str


# Each mutable source carries the same lifecycle predicate used to decide whether
# the record belongs on the operational calendar. The predicate is applied to the
# row lock and to the update so a stale browser tab cannot move a record that was
# closed, cancelled, deactivated, or soft-deleted after the planner loaded.
_MUTABLE_CALENDAR_SOURCES: dict[str, dict[str, Any]] = {
    "audit_schedule": {
        "module": "audits",
        "event_type": "audit_due",
        "table": "qms_audit_schedules",
        "start_column": "next_due_date",
        "end_column": None,
        "permission": "qms.calendar.manage",
        "active_predicate": "is_active IS TRUE AND deleted_at IS NULL",
    },
    "audit": {
        "module": "audits",
        "event_type": "audit_planned",
        "table": "qms_audits",
        "start_column": "planned_start",
        "end_column": "planned_end",
        "permission": "qms.calendar.manage",
        "active_predicate": "deleted_at IS NULL AND UPPER(CAST(status AS TEXT)) NOT IN ('CLOSED', 'CANCELLED')",
    },
    "car": {
        "module": "cars",
        "event_type": "car_due",
        "table": "quality_cars",
        "start_column": "due_date",
        "end_column": None,
        "permission": "qms.calendar.manage",
        "active_predicate": "closed_at IS NULL AND UPPER(CAST(status AS TEXT)) NOT IN ('CLOSED', 'CANCELLED')",
    },
    "training_event": {
        "module": "training-competence",
        "event_type": "training_session",
        "table": "training_events",
        "start_column": "starts_on",
        "end_column": "ends_on",
        "permission": "qms.calendar.manage",
        "active_predicate": "UPPER(CAST(status AS TEXT)) <> 'CANCELLED'",
    },
}


def _parse_calendar_event_id(event_id: str) -> tuple[str, str, str, str]:
    parts = event_id.split(":")
    if len(parts) != 4 or not all(part.strip() for part in parts):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Calendar event identifier is invalid.",
        )
    module, entity_type, entity_id, event_type = (part.strip() for part in parts)
    return module, entity_type, entity_id, event_type


def _is_postgres(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _select_for_update_suffix(db: Session) -> str:
    return " FOR UPDATE" if _is_postgres(db) else ""


def _source_record_exists(db: Session, *, table_name: str, amo_id: str, entity_id: str) -> bool:
    return bool(
        db.execute(
            text(
                f"""
                SELECT 1
                FROM {table_name}
                WHERE amo_id = :amo_id
                  AND CAST(id AS TEXT) = :entity_id
                LIMIT 1
                """
            ),
            {"amo_id": amo_id, "entity_id": entity_id},
        ).first()
    )


def _as_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _duration_minutes(start_value: time, end_value: time) -> int:
    return max(_as_minutes(end_value) - _as_minutes(start_value), 30)


def _shift_audit_meetings(
    db: Session,
    *,
    amo_id: str,
    audit_id: str,
    day_delta: timedelta,
    clock_delta: timedelta | None = None,
) -> int:
    """Keep opening/closing meetings aligned with the audit's planned day and clock."""
    total_delta = day_delta + (clock_delta or timedelta())
    if total_delta == timedelta():
        return 0
    meetings = (
        db.query(QualityAuditMeeting)
        .filter(
            QualityAuditMeeting.amo_id == amo_id,
            QualityAuditMeeting.audit_id == uuid.UUID(str(audit_id)),
            QualityAuditMeeting.status != "CANCELLED",
        )
        .all()
    )
    shifted = 0
    for meeting in meetings:
        if meeting.scheduled_start is None:
            continue
        meeting.scheduled_start = meeting.scheduled_start + total_delta
        if meeting.scheduled_end is not None:
            meeting.scheduled_end = meeting.scheduled_end + total_delta
        shifted += 1
    return shifted


def _raise_personnel_conflicts(
    *,
    conflicts: list[Any],
    start_time: time,
    end_time: time,
    trace_id: str,
    allow: bool,
) -> None:
    personnel = [item for item in conflicts if getattr(item, "conflicting_user_ids", None)]
    if not personnel or allow:
        return
    busy = [
        (item.start_time or BUSINESS_OPEN, item.end_time or BUSINESS_CLOSE)
        for item in personnel
        if item.start_time or item.end_time
    ]
    slots = suggest_working_slots(
        duration_minutes=_duration_minutes(start_time, end_time),
        busy=busy,
    )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "SCHEDULE_CONFLICT",
            "message": (
                "This move overlaps another audit for the same lead, observer, or auditor. "
                "Choose another working-hours slot or confirm an override."
            ),
            "conflicts": [item.model_dump(mode="json") for item in personnel],
            "available_slots": slots,
            "proposed_start_time": start_time.strftime("%H:%M"),
            "proposed_end_time": end_time.strftime("%H:%M"),
            "trace_id": trace_id,
        },
    )


def _enforce_audit_reschedule_conflicts(
    db: Session,
    *,
    amo_id: str,
    entity_id: str,
    start_date: date,
    end_date: date,
    start_time: time,
    end_time: time,
    payload: CalendarRescheduleRequest,
    trace_id: str,
) -> None:
    audit = (
        db.query(models.QMSAudit)
        .filter(models.QMSAudit.amo_id == amo_id, models.QMSAudit.id == uuid.UUID(str(entity_id)))
        .first()
    )
    if not audit:
        return
    metadata = _metadata_for_audit(db, amo_id=amo_id, audit_id=audit.id)
    candidate = _Candidate(
        subject_type="AUDIT",
        subject_id=str(audit.id),
        title=f"{audit.audit_ref} · {audit.title}",
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        end_time=end_time,
        location=(metadata.location if metadata else None) or audit.location,
        user_ids=_audit_user_ids(audit, metadata),
    )
    conflicts = _collect_conflicts(db, amo_id=amo_id, candidate=candidate, exclude_audit_id=str(audit.id))
    _raise_personnel_conflicts(
        conflicts=conflicts,
        start_time=start_time,
        end_time=end_time,
        trace_id=trace_id,
        allow=payload.allow_conflicts,
    )


def _enforce_schedule_reschedule_conflicts(
    db: Session,
    *,
    amo_id: str,
    entity_id: str,
    start_date: date,
    end_date: date,
    start_time: time,
    end_time: time,
    payload: CalendarRescheduleRequest,
    trace_id: str,
) -> None:
    schedule = (
        db.query(models.QMSAuditSchedule)
        .filter(models.QMSAuditSchedule.amo_id == amo_id, models.QMSAuditSchedule.id == uuid.UUID(str(entity_id)))
        .first()
    )
    if not schedule:
        return
    metadata = _metadata_for_schedule(db, amo_id=amo_id, schedule_id=schedule.id)
    candidate = _Candidate(
        subject_type="AUDIT_SCHEDULE",
        subject_id=str(schedule.id),
        title=schedule.title,
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        end_time=end_time,
        location=metadata.location if metadata else None,
        user_ids=_schedule_user_ids(schedule, metadata),
    )
    conflicts = _collect_conflicts(
        db,
        amo_id=amo_id,
        candidate=candidate,
        exclude_schedule_id=str(schedule.id),
    )
    _raise_personnel_conflicts(
        conflicts=conflicts,
        start_time=start_time,
        end_time=end_time,
        trace_id=trace_id,
        allow=payload.allow_conflicts,
    )


@planner_router.get(
    "/integrations/calendar/planner-capabilities",
    response_model=PlannerCapabilitiesResponse,
)
def qms_planner_capabilities(
    ctx: TenantContext = Depends(require_quality_permission("qms.calendar.view")),
    db: Session = Depends(get_read_db),
) -> PlannerCapabilitiesResponse:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    can_manage_calendar = has_quality_permission(db, ctx, "qms.calendar.manage")
    return PlannerCapabilitiesResponse(
        can_reschedule=can_manage_calendar,
        can_create_audit=has_quality_permission(db, ctx, "qms.audit.manage"),
        can_manage_training=has_quality_permission(db, ctx, "qms.training.manage"),
        user_id=ctx.user_id,
    )


@planner_router.patch(
    "/integrations/calendar/reschedule",
    response_model=CalendarRescheduleResponse,
)
def qms_planner_reschedule(
    payload: CalendarRescheduleRequest,
    request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.calendar.view")),
    db: Session = Depends(get_write_db),
) -> CalendarRescheduleResponse:
    trace_id = uuid.uuid4().hex[:12]
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)

    module, entity_type, entity_id, event_type = _parse_calendar_event_id(payload.event_id)
    source = _MUTABLE_CALENDAR_SOURCES.get(entity_type)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This calendar source is read-only and cannot be rescheduled from the planner.",
                "event_id": payload.event_id,
                "trace_id": trace_id,
            },
        )

    if module != source["module"] or event_type != source["event_type"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Calendar event identity does not match its authoritative source type.",
                "event_id": payload.event_id,
                "trace_id": trace_id,
            },
        )

    assert_quality_permission(db, ctx, str(source["permission"]))

    table_name = str(source["table"])
    start_column = str(source["start_column"])
    end_column = source.get("end_column")
    active_predicate = str(source["active_predicate"])
    projected_end = f", {end_column} AS end_date" if end_column else ", NULL AS end_date"
    row = db.execute(
        text(
            f"""
            SELECT {start_column} AS start_date{projected_end}
            FROM {table_name}
            WHERE amo_id = :amo_id
              AND CAST(id AS TEXT) = :entity_id
              AND ({active_predicate})
            LIMIT 1{_select_for_update_suffix(db)}
            """
        ),
        {"amo_id": ctx.amo_id, "entity_id": entity_id},
    ).mappings().first()

    if not row:
        if _source_record_exists(
            db,
            table_name=table_name,
            amo_id=ctx.amo_id,
            entity_id=entity_id,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "This schedule is no longer active and cannot be moved. Refresh the planner.",
                    "event_id": payload.event_id,
                    "trace_id": trace_id,
                },
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Calendar source record was not found.", "trace_id": trace_id},
        )

    if row.get("start_date") is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This active record no longer has a schedulable date. Refresh the planner.",
                "trace_id": trace_id,
            },
        )

    old_date = row["start_date"]
    old_end = row.get("end_date")
    if payload.expected_old_date and old_date != payload.expected_old_date:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SCHEDULE_STALE",
                "message": "The schedule changed after the planner loaded. Refresh before moving it again.",
                "expected_old_date": payload.expected_old_date.isoformat(),
                "current_date": old_date.isoformat(),
                "trace_id": trace_id,
            },
        )

    if payload.new_date == old_date and payload.start_time is None and payload.end_time is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Choose a different date.", "trace_id": trace_id},
        )

    if old_end is not None:
        duration_days = max((old_end - old_date).days + 1, 1)
    elif entity_type == "audit_schedule":
        duration_row = db.execute(
            text(
                """
                SELECT GREATEST(COALESCE(duration_days, 1), 1) AS duration_days
                FROM qms_audit_schedules
                WHERE amo_id = :amo_id AND CAST(id AS TEXT) = :entity_id
                LIMIT 1
                """
            ),
            {"amo_id": ctx.amo_id, "entity_id": entity_id},
        ).mappings().first()
        duration_days = int((duration_row or {}).get("duration_days") or 1)
    else:
        duration_days = 1

    start_date, new_end, resolved_duration = resolve_schedule_window(
        start=payload.new_date,
        duration_days=duration_days,
        weekend_policy=payload.weekend_policy,
        title=None,
    )

    resolved_start_time: time | None = None
    resolved_end_time: time | None = None
    previous_start_time: time | None = None
    if entity_type == "audit":
        audit = (
            db.query(models.QMSAudit)
            .filter(models.QMSAudit.amo_id == ctx.amo_id, models.QMSAudit.id == uuid.UUID(entity_id))
            .first()
        )
        metadata = _metadata_for_audit(db, amo_id=ctx.amo_id, audit_id=uuid.UUID(entity_id)) if audit else None
        previous_start_time = (
            (audit.planned_start_time if audit else None)
            or (metadata.start_time if metadata else None)
            or DEFAULT_START_TIME
        )
        previous_end_time = (
            (audit.planned_end_time if audit else None)
            or (metadata.end_time if metadata else None)
            or DEFAULT_END_TIME
        )
        resolved_start_time = payload.start_time or previous_start_time
        resolved_end_time = payload.end_time or previous_end_time
        _enforce_audit_reschedule_conflicts(
            db,
            amo_id=ctx.amo_id,
            entity_id=entity_id,
            start_date=start_date,
            end_date=new_end,
            start_time=resolved_start_time,
            end_time=resolved_end_time,
            payload=payload,
            trace_id=trace_id,
        )
    elif entity_type == "audit_schedule":
        metadata = _metadata_for_schedule(db, amo_id=ctx.amo_id, schedule_id=uuid.UUID(entity_id))
        previous_start_time = (metadata.start_time if metadata else None) or DEFAULT_START_TIME
        previous_end_time = (metadata.end_time if metadata else None) or DEFAULT_END_TIME
        resolved_start_time = payload.start_time or previous_start_time
        resolved_end_time = payload.end_time or previous_end_time
        _enforce_schedule_reschedule_conflicts(
            db,
            amo_id=ctx.amo_id,
            entity_id=entity_id,
            start_date=start_date,
            end_date=new_end,
            start_time=resolved_start_time,
            end_time=resolved_end_time,
            payload=payload,
            trace_id=trace_id,
        )

    update_params: dict[str, Any] = {
        "new_date": start_date,
        "amo_id": ctx.amo_id,
        "entity_id": entity_id,
    }
    if end_column:
        update_params["new_end"] = new_end
        result = db.execute(
            text(
                f"""
                UPDATE {table_name}
                SET {start_column} = :new_date,
                    {end_column} = :new_end
                WHERE amo_id = :amo_id
                  AND CAST(id AS TEXT) = :entity_id
                  AND ({active_predicate})
                """
            ),
            update_params,
        )
    elif entity_type == "audit_schedule":
        update_params["duration_days"] = resolved_duration
        result = db.execute(
            text(
                """
                UPDATE qms_audit_schedules
                SET next_due_date = :new_date,
                    duration_days = :duration_days
                WHERE amo_id = :amo_id
                  AND CAST(id AS TEXT) = :entity_id
                  AND (is_active IS TRUE AND deleted_at IS NULL)
                """
            ),
            update_params,
        )
        if result.rowcount == 1:
            db.execute(
                text(
                    """
                    UPDATE qms_planner_schedule_metadata
                    SET occurrence_date = :new_date,
                        end_date = :new_end,
                        start_time = COALESCE(:start_time, start_time),
                        end_time = COALESCE(:end_time, end_time),
                        version = COALESCE(version, 1) + 1
                    WHERE amo_id = :amo_id
                      AND CAST(schedule_id AS TEXT) = :entity_id
                    """
                ),
                {
                    "new_date": start_date,
                    "new_end": new_end,
                    "start_time": resolved_start_time,
                    "end_time": resolved_end_time,
                    "amo_id": ctx.amo_id,
                    "entity_id": entity_id,
                },
            )
    else:
        result = db.execute(
            text(
                f"""
                UPDATE {table_name}
                SET {start_column} = :new_date
                WHERE amo_id = :amo_id
                  AND CAST(id AS TEXT) = :entity_id
                  AND ({active_predicate})
                """
            ),
            update_params,
        )

    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "The source record left the active calendar before the move could be committed. Refresh the planner.",
                "event_id": payload.event_id,
                "trace_id": trace_id,
            },
        )

    if entity_type == "audit":
        clock_delta: timedelta | None = None
        if previous_start_time and resolved_start_time and previous_start_time != resolved_start_time:
            clock_delta = datetime.combine(date.min, resolved_start_time) - datetime.combine(
                date.min, previous_start_time
            )
        _shift_audit_meetings(
            db,
            amo_id=ctx.amo_id,
            audit_id=entity_id,
            day_delta=timedelta(days=(start_date - old_date).days),
            clock_delta=clock_delta,
        )
        if resolved_start_time is not None or resolved_end_time is not None:
            db.execute(
                text(
                    """
                    UPDATE qms_audits
                    SET planned_start_time = COALESCE(:start_time, planned_start_time),
                        planned_end_time = COALESCE(:end_time, planned_end_time)
                    WHERE amo_id = :amo_id
                      AND CAST(id AS TEXT) = :entity_id
                    """
                ),
                {
                    "start_time": resolved_start_time,
                    "end_time": resolved_end_time,
                    "amo_id": ctx.amo_id,
                    "entity_id": entity_id,
                },
            )
        db.execute(
            text(
                """
                UPDATE qms_planner_schedule_metadata
                SET occurrence_date = :new_date,
                    end_date = :new_end,
                    start_time = COALESCE(:start_time, start_time),
                    end_time = COALESCE(:end_time, end_time),
                    version = COALESCE(version, 1) + 1
                WHERE amo_id = :amo_id
                  AND CAST(audit_id AS TEXT) = :entity_id
                """
            ),
            {
                "new_date": start_date,
                "new_end": new_end,
                "start_time": resolved_start_time,
                "end_time": resolved_end_time,
                "amo_id": ctx.amo_id,
                "entity_id": entity_id,
            },
        )

    # Append the schedule mutation to the tenant-scoped QMS activity ledger before
    # committing. The source update and immutable audit record therefore succeed
    # or roll back together.
    _log_qms_activity(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        action="calendar_schedule_rescheduled",
        module=module,
        entity_type=entity_type,
        entity_id=entity_id,
        previous_value={
            "event_id": payload.event_id,
            "event_type": event_type,
            "start_date": old_date.isoformat(),
            "end_date": old_end.isoformat() if old_end else None,
        },
        new_value={
            "event_id": payload.event_id,
            "event_type": event_type,
            "start_date": start_date.isoformat(),
            "end_date": new_end.isoformat() if new_end else None,
            "duration_days": resolved_duration,
            "weekend_policy": payload.weekend_policy,
            "start_time": resolved_start_time.strftime("%H:%M") if resolved_start_time else None,
            "end_time": resolved_end_time.strftime("%H:%M") if resolved_end_time else None,
            "allow_conflicts": payload.allow_conflicts,
            "reason": payload.reason.strip(),
            "trace_id": trace_id,
        },
        request=request,
    )
    db.commit()
    logger.info(
        "QMS planner schedule changed trace_id=%s amo_id=%s actor_user_id=%s module=%s entity_type=%s entity_id=%s event_type=%s old_date=%s new_date=%s reason=%s",
        trace_id,
        ctx.amo_id,
        ctx.user_id,
        module,
        entity_type,
        entity_id,
        event_type,
        old_date.isoformat(),
        start_date.isoformat(),
        payload.reason.strip(),
    )

    return CalendarRescheduleResponse(
        event_id=payload.event_id,
        old_date=old_date,
        new_date=start_date,
        end_date=new_end,
        start_time=resolved_start_time,
        end_time=resolved_end_time,
        trace_id=trace_id,
    )
