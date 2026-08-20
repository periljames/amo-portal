from __future__ import annotations

from datetime import date, timedelta
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_read_db, get_write_db

from .canonical_router_legacy import _log_qms_activity
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


class CalendarRescheduleResponse(BaseModel):
    event_id: str
    old_date: date
    new_date: date
    end_date: date | None = None
    trace_id: str


class PlannerCapabilitiesResponse(BaseModel):
    can_reschedule: bool
    can_create_audit: bool
    can_manage_training: bool
    user_id: str


# Audit schedule templates deliberately do not appear here. They are governed by
# /integrations/calendar/audit-schedules/*, which carries metadata versioning,
# conflict checks and schedule-specific audit evidence. This generic adapter is
# only for authoritative non-template source records already owned elsewhere.
_MUTABLE_CALENDAR_SOURCES: dict[str, dict[str, Any]] = {
    "audit": {
        "table": "qms_audits",
        "start_column": "planned_start",
        "end_column": "planned_end",
        "permission": "qms.calendar.manage",
        "active_predicate": "deleted_at IS NULL AND UPPER(CAST(status AS TEXT)) NOT IN ('CLOSED', 'CANCELLED')",
    },
    "car": {
        "table": "quality_cars",
        "start_column": "due_date",
        "end_column": None,
        "permission": "qms.calendar.manage",
        "active_predicate": "closed_at IS NULL AND UPPER(CAST(status AS TEXT)) NOT IN ('CLOSED', 'CANCELLED')",
    },
    "training_event": {
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
                "message": "This calendar source is read-only here. Audit schedules must be changed through the authoritative schedule API.",
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
                "message": "The schedule changed after the planner loaded. Refresh before moving it again.",
                "expected_old_date": payload.expected_old_date.isoformat(),
                "current_date": old_date.isoformat(),
                "trace_id": trace_id,
            },
        )

    if payload.new_date == old_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Choose a different date.", "trace_id": trace_id},
        )

    duration = (old_end - old_date) if old_end else None
    new_end = payload.new_date + duration if isinstance(duration, timedelta) else None

    update_params: dict[str, Any] = {
        "new_date": payload.new_date,
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
            "start_date": payload.new_date.isoformat(),
            "end_date": new_end.isoformat() if new_end else None,
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
        payload.new_date.isoformat(),
        payload.reason.strip(),
    )

    return CalendarRescheduleResponse(
        event_id=payload.event_id,
        old_date=old_date,
        new_date=payload.new_date,
        end_date=new_end,
        trace_id=trace_id,
    )
