from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models


BUSINESS_OPEN = time(9, 0)
BUSINESS_CLOSE = time(17, 0)
DEFAULT_START_TIME = BUSINESS_OPEN
DEFAULT_END_TIME = BUSINESS_CLOSE


def _as_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _from_minutes(value: int) -> time:
    hour, minute = divmod(max(0, value), 60)
    return time(hour=min(hour, 23), minute=min(minute, 59))


def suggest_working_slots(
    *,
    duration_minutes: int,
    busy: list[tuple[time, time]] | None = None,
    open_time: time = BUSINESS_OPEN,
    close_time: time = BUSINESS_CLOSE,
    step_minutes: int = 30,
    limit: int = 6,
) -> list[dict[str, str]]:
    """Return free [start, end) windows inside working hours that fit duration_minutes."""
    if duration_minutes <= 0:
        return []
    open_m = _as_minutes(open_time)
    close_m = _as_minutes(close_time)
    if close_m <= open_m or duration_minutes > (close_m - open_m):
        return []

    blocked: list[tuple[int, int]] = []
    for start, end in busy or []:
        start_m = max(open_m, _as_minutes(start))
        end_m = min(close_m, _as_minutes(end))
        if end_m > start_m:
            blocked.append((start_m, end_m))
    blocked.sort()
    merged: list[tuple[int, int]] = []
    for start_m, end_m in blocked:
        if not merged or start_m > merged[-1][1]:
            merged.append((start_m, end_m))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end_m))

    free: list[tuple[int, int]] = []
    cursor = open_m
    for start_m, end_m in merged:
        if start_m > cursor:
            free.append((cursor, start_m))
        cursor = max(cursor, end_m)
    if cursor < close_m:
        free.append((cursor, close_m))

    suggestions: list[dict[str, str]] = []
    step = max(5, step_minutes)
    for free_start, free_end in free:
        slot_start = free_start
        while slot_start + duration_minutes <= free_end and len(suggestions) < limit:
            slot_end = slot_start + duration_minutes
            start_clock = _from_minutes(slot_start)
            end_clock = _from_minutes(slot_end)
            suggestions.append(
                {
                    "start_time": start_clock.strftime("%H:%M"),
                    "end_time": end_clock.strftime("%H:%M"),
                    "label": f"{start_clock.strftime('%H:%M')} – {end_clock.strftime('%H:%M')}",
                }
            )
            slot_start += step
    return suggestions


def time_text(value: time | None) -> str | None:
    return value.strftime("%H:%M") if value is not None else None


def validate_planned_window(
    *,
    planned_start: date | None,
    planned_end: date | None,
    planned_start_time: time | None,
    planned_end_time: time | None,
    status_code: int = 422,
) -> tuple[time | None, time | None]:
    """Validate the tenant-local audit window and return its effective times."""
    start_time = planned_start_time or (DEFAULT_START_TIME if planned_start else None)
    end_time = planned_end_time or (DEFAULT_END_TIME if planned_end else None)

    if planned_start is None and planned_start_time is not None:
        raise HTTPException(status_code=status_code, detail="Planned start date is required when a start time is set.")
    if planned_end is None and planned_end_time is not None:
        raise HTTPException(status_code=status_code, detail="Planned end date is required when an end time is set.")
    if planned_start and planned_end and planned_end < planned_start:
        raise HTTPException(status_code=status_code, detail="Planned end cannot be before planned start.")

    for label, value in (("start", start_time), ("end", end_time)):
        if value is not None and not (BUSINESS_OPEN <= value <= BUSINESS_CLOSE):
            raise HTTPException(
                status_code=status_code,
                detail=f"Planned audit {label} time must be between 09:00 and 17:00 tenant local time.",
            )
    if planned_start and planned_end and start_time and end_time and end_time <= start_time:
        raise HTTPException(
            status_code=status_code,
            detail="Planned end time must be after planned start time on each audit day; overnight audits are not permitted.",
        )
    return start_time, end_time


def tenant_timezone(db: Session, *, amo_id: str) -> ZoneInfo:
    zone_name = db.query(account_models.AMO.time_zone).filter(account_models.AMO.id == amo_id).scalar() or "UTC"
    try:
        return ZoneInfo(str(zone_name))
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def normalise_tenant_datetime(value: datetime, *, zone: ZoneInfo) -> datetime:
    """Treat offset-free UI values as tenant wall time; persist aware values in UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=zone)
    return value.astimezone(timezone.utc)


def planned_start_at(
    *,
    planned_start: date | None,
    planned_start_time: time | None,
    zone: ZoneInfo,
) -> datetime | None:
    if planned_start is None:
        return None
    return datetime.combine(planned_start, planned_start_time or DEFAULT_START_TIME, tzinfo=zone)


def planned_end_at(
    *,
    planned_end: date | None,
    planned_end_time: time | None,
    zone: ZoneInfo,
) -> datetime | None:
    if planned_end is None:
        return None
    return datetime.combine(planned_end, planned_end_time or DEFAULT_END_TIME, tzinfo=zone)
