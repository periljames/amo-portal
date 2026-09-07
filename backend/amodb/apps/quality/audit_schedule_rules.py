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
