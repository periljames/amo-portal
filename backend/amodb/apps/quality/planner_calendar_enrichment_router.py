from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from amodb.database import get_read_db

from .planner_calendar_router import _qms_planner_calendar
from .planner_schedule_models import QMSPlannerScheduleMetadata
from .tenant_security import TenantContext, require_quality_permission
from .tenant_timezone import TenantTimezone, resolve_tenant_timezone


planner_calendar_enrichment_router = APIRouter()
_CLIENT_TIMEZONE_HEADER = "X-AMO-Client-Timezone"


def _client_timezone_fallback(
    request: Request,
    configured: TenantTimezone,
) -> tuple[TenantTimezone, str]:
    """Use device-local time only when the tenant has no valid configured zone.

    A client timezone is display/runtime context, not tenant configuration. It is
    therefore never persisted here and never replaces an explicit tenant zone.
    """

    if configured.warning is None:
        return configured, "tenant"

    candidate = str(request.headers.get(_CLIENT_TIMEZONE_HEADER) or "").strip()
    if not candidate:
        return configured, "utc_fallback"
    try:
        return TenantTimezone(name=candidate, tzinfo=ZoneInfo(candidate)), "client"
    except ZoneInfoNotFoundError:
        return configured, "utc_fallback"


def _timezone_from_name(value: str | None, fallback) -> Any:
    candidate = str(value or "").strip()
    if not candidate:
        return fallback
    try:
        return ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return fallback


def _event_timestamp(
    event_date: str,
    value,
    *,
    stored_timezone_name: str | None,
    display_timezone,
) -> str | None:
    if not event_date or value is None:
        return None
    stored_timezone = _timezone_from_name(stored_timezone_name, display_timezone)
    combined = datetime.combine(date.fromisoformat(event_date), value, tzinfo=stored_timezone)
    return combined.astimezone(display_timezone).isoformat(timespec="minutes")


def _refresh_due_state(items: list[dict[str, Any]], *, today: date) -> None:
    for item in items:
        raw_date = str(item.get("date") or "")
        try:
            event_date = date.fromisoformat(raw_date[:10])
        except ValueError:
            continue
        actionable = bool(item.get("actionable", True))
        item["due_state"] = (
            "overdue"
            if actionable and event_date < today
            else "today"
            if event_date == today
            else "upcoming"
        )


@planner_calendar_enrichment_router.get("/integrations/calendar")
def qms_planner_calendar_enriched(
    request: Request,
    start: date | None = Query(None),
    end: date | None = Query(None),
    limit: int = Query(120, ge=1, le=500),
    offset: int = Query(0, ge=0, le=100_000),
    view: str | None = Query(None),
    source: str | None = Query(None),
    ctx: TenantContext = Depends(require_quality_permission("qms.calendar.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    payload = _qms_planner_calendar(
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        view=view,
        source=source,
        ctx=ctx,
        db=db,
    )

    configured_timezone = resolve_tenant_timezone(db, amo_id=ctx.amo_id)
    effective_timezone, timezone_source = _client_timezone_fallback(request, configured_timezone)
    source_errors = payload.get("source_errors") or []

    payload["timezone_name"] = effective_timezone.name
    payload["timezone_source"] = timezone_source
    payload["timezone_warning"] = configured_timezone.warning if timezone_source == "utc_fallback" else None
    # timezone_warning has its own field. Keep the generic warning for actual
    # source degradation so the frontend cannot render the same timezone message twice.
    payload["warning"] = "Some calendar sources failed. See source_errors." if source_errors else None

    items = payload.get("items") or []
    if timezone_source == "client":
        _refresh_due_state(items, today=datetime.now(effective_timezone.tzinfo).date())

    if not items or not inspect(db.get_bind()).has_table("qms_planner_schedule_metadata"):
        return payload

    schedule_ids = {
        str(item.get("entity_id"))
        for item in items
        if item.get("entity_type") == "audit_schedule" and item.get("entity_id")
    }
    audit_ids = {
        str(item.get("entity_id"))
        for item in items
        if item.get("entity_type") == "audit" and item.get("entity_id")
    }
    rows = []
    if schedule_ids:
        rows.extend(
            db.query(QMSPlannerScheduleMetadata)
            .filter(
                QMSPlannerScheduleMetadata.amo_id == ctx.amo_id,
                QMSPlannerScheduleMetadata.schedule_id.in_(schedule_ids),
            )
            .all()
        )
    if audit_ids:
        rows.extend(
            db.query(QMSPlannerScheduleMetadata)
            .filter(
                QMSPlannerScheduleMetadata.amo_id == ctx.amo_id,
                QMSPlannerScheduleMetadata.audit_id.in_(audit_ids),
            )
            .all()
        )

    by_schedule = {str(row.schedule_id): row for row in rows if row.schedule_id}
    by_audit = {str(row.audit_id): row for row in rows if row.audit_id}
    for item in items:
        entity_id = str(item.get("entity_id") or "")
        metadata = (
            by_schedule.get(entity_id)
            if item.get("entity_type") == "audit_schedule"
            else by_audit.get(entity_id)
            if item.get("entity_type") == "audit"
            else None
        )
        if metadata is None:
            continue
        event_date = str(item.get("date") or "")
        starts_at = _event_timestamp(
            event_date,
            metadata.start_time,
            stored_timezone_name=metadata.timezone_name,
            display_timezone=effective_timezone.tzinfo,
        )
        ends_at = _event_timestamp(
            event_date,
            metadata.end_time,
            stored_timezone_name=metadata.timezone_name,
            display_timezone=effective_timezone.tzinfo,
        )
        item["starts_at"] = starts_at
        item["ends_at"] = ends_at
        # Timed commitments follow the displayed local date after timezone conversion.
        if starts_at:
            item["date"] = starts_at[:10]
        item["timezone_name"] = effective_timezone.name
        item["timezone_source"] = timezone_source
        item["stored_timezone_name"] = metadata.timezone_name
        item["timezone_reconciled"] = metadata.timezone_name == effective_timezone.name
        item["location"] = metadata.location
        item["planner_notes"] = metadata.notes
        item["attendee_count"] = len(metadata.attendee_user_ids) + len(metadata.external_attendees)
        item["source_schedule_id"] = str(metadata.source_schedule_id) if metadata.source_schedule_id else None
        item["occurrence_date"] = metadata.occurrence_date.isoformat() if metadata.occurrence_date else None
        if metadata.end_date:
            item["ends_on"] = metadata.end_date.isoformat()
        if item.get("entity_type") == "audit_schedule":
            item["schedule_version"] = metadata.version
            item["expected_version"] = metadata.version

    if timezone_source == "client":
        _refresh_due_state(items, today=datetime.now(effective_timezone.tzinfo).date())
    return payload
