from __future__ import annotations

from datetime import date, datetime, timedelta
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from amodb.database import get_read_db

from .canonical_router_legacy import (
    _append_calendar_rows,
    _as_date,
    _calendar_event_row,
    _pg_set_read_timeout,
    _soft_delete_filter,
    _table_columns,
    _training_calendar_available,
)
from .tenant_security import (
    TenantContext,
    require_quality_permission,
    set_postgres_tenant_context,
)
from .tenant_timezone import resolve_tenant_timezone


planner_calendar_router = APIRouter()
_VALID_SOURCES = {"all", "audits", "cars", "training", "month", "week", "list", "agenda", "year"}


def _active_training_lifecycle_sql(db: Session) -> str:
    columns = _table_columns(db, "training_records")
    filters: list[str] = []
    if "record_status" in columns:
        filters.append("COALESCE(UPPER(NULLIF(r.record_status, '')), 'ACTIVE') NOT IN ('RENEWED', 'SUPERSEDED')")
    if "source_status" in columns:
        filters.append("COALESCE(UPPER(NULLIF(r.source_status, '')), 'ACTIVE') NOT IN ('RENEWED', 'SUPERSEDED')")
    return "" if not filters else " AND " + " AND ".join(filters)


def _calendar_page(
    *,
    events: list[dict[str, Any]],
    offset: int,
    limit: int,
) -> tuple[list[dict[str, Any]], bool, int | None]:
    events.sort(key=lambda item: (item.get("date") or "", item.get("title") or "", item.get("id") or ""))
    end_index = offset + limit
    has_more = len(events) > end_index
    return events[offset:end_index], has_more, end_index if has_more else None


@planner_calendar_router.get("/integrations/calendar")
def qms_planner_calendar(
    start: date | None = Query(None),
    end: date | None = Query(None),
    limit: int = Query(120, ge=1, le=500),
    offset: int = Query(0, ge=0, le=100_000),
    view: str | None = Query(None),
    source: str | None = Query(None),
    ctx: TenantContext = Depends(require_quality_permission("qms.calendar.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    trace_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()

    # Reject a fully specified invalid range before touching tenant/database
    # state. Apart from preserving the public validation contract, this avoids
    # a needless timezone query for a request that cannot be executed.
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Calendar start date cannot be after the end date.",
        )

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _pg_set_read_timeout(db, 1800)

    tenant_timezone = resolve_tenant_timezone(db, amo_id=ctx.amo_id)
    today = datetime.now(tenant_timezone.tzinfo).date()
    start_date = start or today - timedelta(days=30)
    end_date = end or today + timedelta(days=180)
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Calendar start date cannot be after the end date.",
        )

    bounded_limit = max(1, min(limit, 500))
    bounded_offset = max(0, offset)
    source_limit = min(max(bounded_limit + bounded_offset + 20, 120), 700)
    requested_source = (source or "all").strip().lower()
    if requested_source not in _VALID_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported calendar source '{requested_source}'.",
        )

    source_errors: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    params = {
        "amo_id": ctx.amo_id,
        "start_date": start_date,
        "end_date": end_date,
        "limit": source_limit,
    }
    schedule_deleted = _soft_delete_filter(db, "qms_audit_schedules")
    audit_deleted = _soft_delete_filter(db, "qms_audits")
    car_deleted = _soft_delete_filter(db, "quality_cars")

    if requested_source in {"all", "audits", "month", "week", "list", "agenda", "year"}:
        schedule_rows = _append_calendar_rows(
            db,
            ctx=ctx,
            label="audit_schedules",
            params=params,
            source_errors=source_errors,
            sql=f"""
                SELECT id, title, kind, frequency, auditee, lead_auditor_user_id,
                       next_due_date AS event_date
                FROM qms_audit_schedules
                WHERE amo_id = :amo_id
                  AND is_active IS TRUE
                  AND next_due_date IS NOT NULL
                  AND next_due_date >= :start_date
                  AND next_due_date <= :end_date
                  {schedule_deleted}
                ORDER BY next_due_date ASC, id ASC
                LIMIT :limit
            """,
        )
        for row in schedule_rows:
            kind = str(row.get("kind") or "audit").replace("_", " ").title()
            title = f"{kind}: {row.get('title') or 'Scheduled audit'}"
            events.append(
                _calendar_event_row(
                    module="audits",
                    entity_type="audit_schedule",
                    entity_id=row.get("id"),
                    title=title,
                    event_date=row.get("event_date"),
                    event_type="audit_due",
                    link=f"/maintenance/{ctx.amo_code}/quality/audits/plan?view=list&schedule_id={row.get('id')}",
                    today=today,
                    extra={
                        "audit_source": "schedule_template",
                        "calendar_group": "audit",
                        "kind": row.get("kind"),
                        "frequency": row.get("frequency"),
                        "auditee": row.get("auditee"),
                        "lead_auditor_user_id": row.get("lead_auditor_user_id"),
                    },
                )
            )

        audit_rows = _append_calendar_rows(
            db,
            ctx=ctx,
            label="live_audits",
            params=params,
            source_errors=source_errors,
            sql=f"""
                SELECT id, audit_ref, title, kind, status, auditee,
                       lead_auditor_user_id, planned_start AS event_date, planned_end
                FROM qms_audits
                WHERE amo_id = :amo_id
                  AND planned_start IS NOT NULL
                  AND planned_start >= :start_date
                  AND planned_start <= :end_date
                  AND COALESCE(status, 'PLANNED') NOT IN ('CLOSED', 'CANCELLED')
                  {audit_deleted}
                ORDER BY planned_start ASC, id ASC
                LIMIT :limit
            """,
        )
        for row in audit_rows:
            title = f"{row.get('audit_ref') or 'Audit'} · {row.get('title') or 'Planned audit'}"
            events.append(
                _calendar_event_row(
                    module="audits",
                    entity_type="audit",
                    entity_id=row.get("id"),
                    title=title,
                    event_date=row.get("event_date"),
                    event_type="audit_planned",
                    link=f"/maintenance/{ctx.amo_code}/quality/audits/{row.get('id')}/overview",
                    today=today,
                    extra={
                        "audit_source": "live_audit",
                        "calendar_group": "audit",
                        "audit_ref": row.get("audit_ref"),
                        "status": row.get("status"),
                        "kind": row.get("kind"),
                        "auditee": row.get("auditee"),
                        "lead_auditor_user_id": row.get("lead_auditor_user_id"),
                        "planned_end": _as_date(row.get("planned_end")),
                    },
                )
            )

    if requested_source in {"all", "cars", "month", "week", "list", "agenda", "year"}:
        car_rows = _append_calendar_rows(
            db,
            ctx=ctx,
            label="cars",
            params=params,
            source_errors=source_errors,
            sql=f"""
                SELECT id, car_number, title, priority, status, due_date AS event_date
                FROM quality_cars
                WHERE amo_id = :amo_id
                  AND due_date IS NOT NULL
                  AND due_date >= :start_date
                  AND due_date <= :end_date
                  AND COALESCE(status, 'DRAFT') NOT IN ('CLOSED', 'CANCELLED')
                  {car_deleted}
                ORDER BY due_date ASC, id ASC
                LIMIT :limit
            """,
        )
        for row in car_rows:
            title = f"{row.get('car_number') or 'CAR'} · {row.get('title') or 'Corrective action due'}"
            events.append(
                _calendar_event_row(
                    module="cars",
                    entity_type="car",
                    entity_id=row.get("id"),
                    title=title,
                    event_date=row.get("event_date"),
                    event_type="car_due",
                    link=f"/maintenance/{ctx.amo_code}/quality/cars/{row.get('id')}/overview",
                    today=today,
                    extra={
                        "calendar_group": "car",
                        "status": row.get("status"),
                        "priority": row.get("priority"),
                        "car_number": row.get("car_number"),
                    },
                )
            )

    training_available = _training_calendar_available(db, amo_id=ctx.amo_id)
    include_training = requested_source in {"all", "training", "month", "week", "list", "agenda", "year"}
    if include_training and training_available:
        lifecycle_sql = _active_training_lifecycle_sql(db)
        training_rows = _append_calendar_rows(
            db,
            ctx=ctx,
            label="training_expiries",
            params=params,
            source_errors=source_errors,
            timeout_ms=1400,
            sql=f"""
                WITH ranked AS (
                    SELECT
                        r.id,
                        r.user_id,
                        r.course_id,
                        r.valid_until AS event_date,
                        r.completion_date,
                        r.created_at,
                        c.course_id AS course_code,
                        c.course_name,
                        COALESCE(
                            NULLIF(u.full_name, ''),
                            NULLIF(CONCAT_WS(' ', u.first_name, u.last_name), ''),
                            u.email,
                            r.user_id
                        ) AS user_name,
                        ROW_NUMBER() OVER (
                            PARTITION BY r.user_id, r.course_id
                            ORDER BY r.completion_date DESC NULLS LAST,
                                     r.created_at DESC NULLS LAST,
                                     r.id DESC
                        ) AS record_rank
                    FROM training_records r
                    LEFT JOIN training_courses c
                      ON c.id = r.course_id AND c.amo_id = r.amo_id
                    LEFT JOIN users u
                      ON u.id = r.user_id AND u.amo_id = r.amo_id
                    WHERE r.amo_id = :amo_id
                      AND r.valid_until IS NOT NULL
                      AND UPPER(CAST(r.verification_status AS TEXT)) = 'VERIFIED'
                      {lifecycle_sql}
                )
                SELECT id, user_id, course_id, event_date, course_code, course_name, user_name
                FROM ranked
                WHERE record_rank = 1
                  AND event_date >= :start_date
                  AND event_date <= :end_date
                ORDER BY event_date ASC, user_name ASC, id ASC
                LIMIT :limit
            """,
        )
        for row in training_rows:
            course = row.get("course_code") or row.get("course_name") or row.get("course_id") or "Training"
            title = f"{row.get('user_name') or 'Personnel'} · {course} expires"
            events.append(
                _calendar_event_row(
                    module="training-competence",
                    entity_type="training_record",
                    entity_id=row.get("id"),
                    title=title,
                    event_date=row.get("event_date"),
                    event_type="training_expiry",
                    link=f"/maintenance/{ctx.amo_code}/training/competence/people/{row.get('user_id')}/course-history",
                    today=today,
                    extra={
                        "calendar_group": "training",
                        "course_code": course,
                        "course_id": row.get("course_id"),
                        "user_id": row.get("user_id"),
                        "user_name": row.get("user_name"),
                    },
                )
            )

        session_rows = _append_calendar_rows(
            db,
            ctx=ctx,
            label="training_sessions",
            params=params,
            source_errors=source_errors,
            timeout_ms=1400,
            sql="""
                SELECT e.id, e.title, e.starts_on AS event_date, e.ends_on, e.status,
                       c.course_id AS course_code, c.course_name
                FROM training_events e
                LEFT JOIN training_courses c
                  ON c.id = e.course_id AND c.amo_id = e.amo_id
                WHERE e.amo_id = :amo_id
                  AND e.starts_on IS NOT NULL
                  AND e.starts_on >= :start_date
                  AND e.starts_on <= :end_date
                  AND COALESCE(e.status, 'PLANNED') <> 'CANCELLED'
                ORDER BY e.starts_on ASC, e.id ASC
                LIMIT :limit
            """,
        )
        for row in session_rows:
            course = row.get("course_code") or row.get("course_name") or row.get("title") or "Training session"
            events.append(
                _calendar_event_row(
                    module="training-competence",
                    entity_type="training_event",
                    entity_id=row.get("id"),
                    title=course,
                    event_date=row.get("event_date"),
                    event_type="training_session",
                    link=f"/maintenance/{ctx.amo_code}/training/competence/schedule?event_id={row.get('id')}",
                    today=today,
                    extra={
                        "calendar_group": "training",
                        "course_code": course,
                        "status": row.get("status"),
                        "ends_on": _as_date(row.get("ends_on")),
                    },
                )
            )
    elif requested_source == "training" and not training_available:
        source_errors.append(
            {
                "label": "training",
                "message": "Training module is not enabled for this tenant.",
                "type": "ModuleNotEnabled",
            }
        )

    visible, has_more, next_offset = _calendar_page(
        events=events,
        offset=bounded_offset,
        limit=bounded_limit,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    warning_messages = [item for item in [tenant_timezone.warning] if item]
    if source_errors:
        warning_messages.append("Some calendar sources failed. See source_errors.")
    return {
        "module": "calendar",
        "view": view or requested_source,
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "timezone_name": tenant_timezone.name,
        "timezone_warning": tenant_timezone.warning,
        "items": visible,
        "limit": bounded_limit,
        "offset": bounded_offset,
        "next_offset": next_offset,
        "has_more": has_more,
        "source_errors": source_errors,
        "warning": " ".join(warning_messages) if warning_messages else None,
        "trace_id": trace_id,
        "elapsed_ms": elapsed_ms,
    }
