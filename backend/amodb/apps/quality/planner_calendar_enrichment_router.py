from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from amodb.database import get_read_db

from .audit_occurrence_completion_models import QualityAuditMeeting
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


def _coerce_clock(value: Any) -> time | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.timetz().replace(tzinfo=None) if value.tzinfo else value.time()
    if isinstance(value, time):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text = str(value).strip()
    if not text:
        return None
    fragment = text.split("T")[-1].split("+")[0].split("Z")[0].strip()
    parts = fragment.split(":")
    if len(parts) < 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(float(parts[2])) if len(parts) > 2 else 0
    except ValueError:
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59 or second < 0 or second > 59:
        return None
    return time(hour=hour, minute=minute, second=second)


def _event_timestamp(
    event_date: str,
    value,
    *,
    stored_timezone_name: str | None,
    display_timezone,
) -> str | None:
    clock = _coerce_clock(value)
    if not event_date or clock is None:
        return None
    stored_timezone = _timezone_from_name(stored_timezone_name, display_timezone)
    combined = datetime.combine(date.fromisoformat(event_date[:10]), clock, tzinfo=stored_timezone)
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


def _apply_item_times(
    item: dict[str, Any],
    *,
    start_value: Any,
    end_value: Any,
    stored_timezone_name: str | None,
    display_timezone,
) -> None:
    event_date = str(item.get("date") or "")
    starts_at = _event_timestamp(
        event_date,
        start_value,
        stored_timezone_name=stored_timezone_name,
        display_timezone=display_timezone,
    )
    ends_at = _event_timestamp(
        event_date,
        end_value,
        stored_timezone_name=stored_timezone_name,
        display_timezone=display_timezone,
    )
    if not starts_at and not ends_at:
        return
    if starts_at:
        item["starts_at"] = starts_at
        # Keep the source calendar day authoritative; timezone conversion of the
        # wall clock must not slide a daytime audit onto the neighbouring date.
        item["start_time"] = starts_at[11:16]
    if ends_at:
        item["ends_at"] = ends_at
        item["end_time"] = ends_at[11:16]


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _expand_audit_window_with_meetings(
    parent: dict[str, Any],
    meetings: list[QualityAuditMeeting],
    *,
    display_timezone,
) -> None:
    """Fold opening/closing debriefs into the single audit bar (one timed block).

    Planned start/end dates remain the authoritative calendar span. Meetings only
    contribute clock bounds so a same-day audit cannot inflate into a multi-day bar
    when meeting timestamps or stale ends_on disagree with planned_end.
    """
    bounds: list[datetime] = []
    for meeting in meetings:
        if str(meeting.status or "").upper() == "CANCELLED" or meeting.scheduled_start is None:
            continue
        bounds.append(meeting.scheduled_start.astimezone(display_timezone))
        end = meeting.scheduled_end or meeting.scheduled_start
        bounds.append(end.astimezone(display_timezone))
    for key in ("starts_at", "ends_at"):
        parsed = _parse_iso_datetime(parent.get(key))
        if parsed is not None:
            bounds.append(parsed.astimezone(display_timezone) if parsed.tzinfo else parsed.replace(tzinfo=display_timezone))
    if not bounds:
        return
    first = min(bounds)
    last = max(bounds)
    if last < first:
        last = first

    planned_start_text = str(parent.get("planned_start") or parent.get("occurrence_date") or parent.get("date") or "")[:10]
    planned_end_text = str(parent.get("planned_end") or parent.get("ends_on") or "")[:10]
    try:
        planned_start = date.fromisoformat(planned_start_text) if len(planned_start_text) == 10 else None
    except ValueError:
        planned_start = None
    try:
        planned_end = date.fromisoformat(planned_end_text) if len(planned_end_text) == 10 else None
    except ValueError:
        planned_end = None
    if planned_start is None:
        planned_start = first.date()
    if planned_end is None or planned_end < planned_start:
        planned_end = planned_start

    parent["starts_at"] = first.isoformat(timespec="minutes")
    parent["ends_at"] = last.isoformat(timespec="minutes")
    parent["start_time"] = first.strftime("%H:%M")
    parent["end_time"] = last.strftime("%H:%M")
    parent["date"] = planned_start.isoformat()
    parent["meeting_count"] = sum(
        1 for meeting in meetings if str(meeting.status or "").upper() != "CANCELLED" and meeting.scheduled_start
    )
    if planned_end > planned_start:
        parent["ends_on"] = planned_end.isoformat()
        parent["planned_end"] = planned_end.isoformat()
    else:
        parent.pop("ends_on", None)
        parent["planned_end"] = planned_start.isoformat()


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

    if not items:
        return payload

    bind = db.get_bind()
    has_metadata = inspect(bind).has_table("qms_planner_schedule_metadata")
    has_meetings = inspect(bind).has_table("quality_audit_meetings")

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
    audits_by_id = {
        str(item.get("entity_id")): item
        for item in items
        if item.get("entity_type") == "audit" and item.get("entity_id")
    }

    rows: list[QMSPlannerScheduleMetadata] = []
    if has_metadata and (schedule_ids or audit_ids):
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
        if metadata is not None:
            _apply_item_times(
                item,
                start_value=metadata.start_time,
                end_value=metadata.end_time,
                stored_timezone_name=metadata.timezone_name,
                display_timezone=effective_timezone.tzinfo,
            )
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
            continue

        if item.get("entity_type") == "audit" and not item.get("starts_at"):
            _apply_item_times(
                item,
                start_value=item.get("planned_start_time") or item.get("start_time"),
                end_value=item.get("planned_end_time") or item.get("end_time"),
                stored_timezone_name=effective_timezone.name,
                display_timezone=effective_timezone.tzinfo,
            )

    if has_meetings and audit_ids:
        meetings = (
            db.query(QualityAuditMeeting)
            .filter(
                QualityAuditMeeting.amo_id == ctx.amo_id,
                QualityAuditMeeting.audit_id.in_(list(audit_ids)),
                QualityAuditMeeting.status != "CANCELLED",
            )
            .order_by(QualityAuditMeeting.scheduled_start.asc())
            .all()
        )
        meetings_by_audit: dict[str, list[QualityAuditMeeting]] = {}
        for meeting in meetings:
            meetings_by_audit.setdefault(str(meeting.audit_id), []).append(meeting)
        for audit_id, audit_meetings in meetings_by_audit.items():
            parent = audits_by_id.get(audit_id)
            if not parent:
                continue
            # One calendar bar per audit: pre/post debriefs widen the same block.
            _expand_audit_window_with_meetings(
                parent,
                audit_meetings,
                display_timezone=effective_timezone.tzinfo,
            )

    # Keep live-audit day spans authoritative from planned_start/planned_end so
    # stale planner metadata ends_on cannot inflate a one-day audit into two days.
    for item in items:
        if item.get("entity_type") != "audit":
            continue
        start_text = str(item.get("date") or "")[:10]
        if len(start_text) != 10:
            continue
        planned_end_text = str(item.get("planned_end") or "")[:10]
        if planned_end_text and planned_end_text > start_text:
            item["ends_on"] = planned_end_text
        else:
            item.pop("ends_on", None)

    return payload
