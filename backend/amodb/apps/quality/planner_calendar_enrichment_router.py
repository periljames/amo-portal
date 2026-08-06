from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from amodb.database import get_read_db

from .planner_calendar_router import qms_planner_calendar
from .planner_schedule_models import QMSPlannerScheduleMetadata
from .tenant_security import TenantContext, require_quality_permission


planner_calendar_enrichment_router = APIRouter()
_TIMEZONE = ZoneInfo("Africa/Nairobi")


def _event_timestamp(event_date: str, value) -> str | None:
    if not event_date or value is None:
        return None
    combined = datetime.combine(date.fromisoformat(event_date), value, tzinfo=_TIMEZONE)
    return combined.isoformat(timespec="minutes")


@planner_calendar_enrichment_router.get("/integrations/calendar")
def qms_planner_calendar_enriched(
    start: date | None = Query(None),
    end: date | None = Query(None),
    limit: int = Query(120, ge=1, le=500),
    offset: int = Query(0, ge=0, le=100_000),
    view: str | None = Query(None),
    source: str | None = Query(None),
    ctx: TenantContext = Depends(require_quality_permission("qms.calendar.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    payload = qms_planner_calendar(
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        view=view,
        source=source,
        ctx=ctx,
        db=db,
    )
    items = payload.get("items") or []
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
        item["starts_at"] = _event_timestamp(event_date, metadata.start_time)
        item["ends_at"] = _event_timestamp(event_date, metadata.end_time)
        item["timezone_name"] = metadata.timezone_name
        item["location"] = metadata.location
        item["planner_notes"] = metadata.notes
        item["attendee_count"] = len(metadata.attendee_user_ids) + len(metadata.external_attendees)
        item["source_schedule_id"] = str(metadata.source_schedule_id) if metadata.source_schedule_id else None
        item["occurrence_date"] = metadata.occurrence_date.isoformat() if metadata.occurrence_date else None
    return payload
