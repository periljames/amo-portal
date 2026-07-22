from __future__ import annotations

import re
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException

_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def validate_clock(value: str | None, *, field_name: str) -> str | None:
    normalized = str(value or "").strip() or None
    if normalized and not _TIME_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=422, detail=f"{field_name} must use a valid 24-hour HH:MM value")
    return normalized


def validate_timezone(value: str | None) -> str:
    normalized = str(value or "UTC").strip() or "UTC"
    try:
        ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="timezone_name must be a valid IANA timezone") from exc
    return normalized


def _clock(value: str) -> time:
    hours, minutes = value.split(":", 1)
    return time(hour=int(hours), minute=int(minutes))


def is_quiet_now(
    *,
    start: str | None,
    end: str | None,
    timezone_name: str | None,
    now: datetime | None = None,
) -> bool:
    if not start or not end or start == end:
        return False
    validated_start = validate_clock(start, field_name="quiet_hours_start")
    validated_end = validate_clock(end, field_name="quiet_hours_end")
    zone_name = validate_timezone(timezone_name)
    if not validated_start or not validated_end:
        return False
    current = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(zone_name)).time().replace(tzinfo=None)
    start_clock = _clock(validated_start)
    end_clock = _clock(validated_end)
    if start_clock < end_clock:
        return start_clock <= current < end_clock
    return current >= start_clock or current < end_clock
