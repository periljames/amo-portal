"""Weekend confirmation for Quality audit schedule commits.

When a planned occurrence spans Saturday or Sunday, the API refuses to commit
until the caller explicitly chooses:

- INCLUDE_WEEKEND — activity really runs on the weekend
- SKIP_WEEKEND — keep working days only (Friday then Monday style)
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from fastapi import HTTPException, status


WeekendPolicy = Literal["INCLUDE_WEEKEND", "SKIP_WEEKEND"]
WEEKEND_POLICIES: tuple[str, ...] = ("INCLUDE_WEEKEND", "SKIP_WEEKEND")


def is_weekend(day: date) -> bool:
    return day.weekday() >= 5


def weekend_dates_in_range(start: date, end: date) -> list[date]:
    if end < start:
        start, end = end, start
    hits: list[date] = []
    cursor = start
    while cursor <= end:
        if is_weekend(cursor):
            hits.append(cursor)
        cursor += timedelta(days=1)
    return hits


def next_weekday(day: date) -> date:
    cursor = day
    while is_weekend(cursor):
        cursor += timedelta(days=1)
    return cursor


def add_business_days(start: date, extra_business_days: int) -> date:
    """Advance `extra_business_days` weekdays from start (start counts as day 0)."""
    if extra_business_days < 0:
        raise ValueError("extra_business_days must be >= 0")
    cursor = next_weekday(start)
    remaining = extra_business_days
    while remaining > 0:
        cursor += timedelta(days=1)
        if not is_weekend(cursor):
            remaining -= 1
    return cursor


def calendar_end(start: date, duration_days: int) -> date:
    return start + timedelta(days=max(int(duration_days), 1) - 1)


def weekend_confirmation_detail(
    *,
    start: date,
    duration_days: int,
    title: str | None = None,
) -> dict[str, Any]:
    end = calendar_end(start, duration_days)
    weekends = weekend_dates_in_range(start, end)
    skip_start = next_weekday(start)
    skip_end = add_business_days(skip_start, max(int(duration_days), 1) - 1)
    label = (title or "This activity").strip() or "This activity"
    return {
        "code": "WEEKEND_CONFIRMATION_REQUIRED",
        "message": (
            f"{label} runs into a weekend ({', '.join(d.isoformat() for d in weekends)}). "
            "Confirm whether work happens on the weekend, or keep Friday then Monday (skip Saturday and Sunday)."
        ),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "duration_days": int(duration_days),
        "weekend_dates": [d.isoformat() for d in weekends],
        "options": {
            "INCLUDE_WEEKEND": {
                "label": "Include weekend — activity will run on Saturday/Sunday",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
            "SKIP_WEEKEND": {
                "label": "Skip weekend — keep working days only (Friday then Monday)",
                "start_date": skip_start.isoformat(),
                "end_date": skip_end.isoformat(),
            },
        },
        "allowed_policies": list(WEEKEND_POLICIES),
    }


def schedule_start_in_past_detail(*, start: date, today: date, title: str | None = None) -> dict[str, Any]:
    label = (title or "This activity").strip() or "This activity"
    return {
        "code": "SCHEDULE_START_IN_PAST",
        "message": (
            f"{label} cannot start on {start.isoformat()} because that date is already past "
            f"(today is {today.isoformat()}). Choose today or a future start date."
        ),
        "start_date": start.isoformat(),
        "today": today.isoformat(),
    }


def ensure_schedule_start_not_past(
    *,
    start: date,
    title: str | None = None,
    as_of: date | None = None,
) -> None:
    """Refuse committing a new/rescheduled window that starts before today."""
    today = as_of or date.today()
    if start < today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=schedule_start_in_past_detail(start=start, today=today, title=title),
        )


def resolve_schedule_window(
    *,
    start: date,
    duration_days: int,
    weekend_policy: str | None,
    title: str | None = None,
    require_confirmation: bool = True,
    as_of: date | None = None,
    allow_past_start: bool = False,
) -> tuple[date, date, int]:
    """Return (start, end, calendar_duration_days) after weekend policy application."""
    if not allow_past_start:
        ensure_schedule_start_not_past(start=start, title=title, as_of=as_of)
    duration = max(int(duration_days), 1)
    naive_end = calendar_end(start, duration)
    weekends = weekend_dates_in_range(start, naive_end)
    if not weekends:
        return start, naive_end, duration

    policy = (weekend_policy or "").strip().upper() or None
    if require_confirmation and policy not in WEEKEND_POLICIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=weekend_confirmation_detail(start=start, duration_days=duration, title=title),
        )

    if policy == "INCLUDE_WEEKEND":
        return start, naive_end, duration

    # SKIP_WEEKEND — working-day duration; bump off a weekend start.
    resolved_start = next_weekday(start)
    resolved_end = add_business_days(resolved_start, duration - 1)
    calendar_duration = (resolved_end - resolved_start).days + 1
    return resolved_start, resolved_end, calendar_duration


def annotate_notes_with_weekend_policy(notes: str | None, weekend_policy: str | None) -> str | None:
    policy = (weekend_policy or "").strip().upper() or None
    if policy not in WEEKEND_POLICIES:
        return notes
    marker = f"Weekend policy: {policy}"
    existing = (notes or "").strip()
    if marker in existing:
        return existing or None
    if not existing:
        return marker
    return f"{existing}\n{marker}"
