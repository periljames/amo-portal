# backend/amodb/apps/workforce/calculations.py
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import models

UTC = timezone.utc


@dataclass(frozen=True)
class AttendanceTotals:
    presence_minutes: int
    break_minutes: int
    paid_minutes: int
    incomplete: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PatternOccurrence:
    user_id: str
    work_date: date
    cycle_day_index: int
    status: models.PatternDayStatus
    starts_at: Optional[datetime]
    ends_at: Optional[datetime]
    planned_minutes: int
    shift_template_id: Optional[str]
    source_reference_id: str


def ensure_aware(value: datetime, *, default_timezone: str = "UTC") -> datetime:
    if value.tzinfo is not None and value.utcoffset() is not None:
        return value
    return value.replace(tzinfo=get_zone(default_timezone))


def get_zone(timezone_name: Optional[str]) -> ZoneInfo:
    name = (timezone_name or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {name}") from exc


def local_datetime_to_utc(local_date: date, hhmm: str, timezone_name: str) -> datetime:
    try:
        hour, minute = [int(part) for part in hhmm.split(":", 1)]
        local_time = time(hour=hour, minute=minute)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("Time must use HH:MM format") from exc
    local = datetime.combine(local_date, local_time, tzinfo=get_zone(timezone_name))
    return local.astimezone(UTC)


def local_shift_window_to_utc(
    *,
    work_date: date,
    start_time_local: Optional[str],
    end_time_local: Optional[str],
    timezone_name: str,
    spans_next_day: bool,
    fallback_minutes: int = 0,
) -> tuple[Optional[datetime], Optional[datetime], int]:
    if not start_time_local and not end_time_local:
        return None, None, max(int(fallback_minutes or 0), 0)
    if not start_time_local:
        raise ValueError("start_time_local is required when end_time_local is supplied")
    start = local_datetime_to_utc(work_date, start_time_local, timezone_name)
    if end_time_local:
        end_date = work_date + timedelta(days=1 if spans_next_day else 0)
        end = local_datetime_to_utc(end_date, end_time_local, timezone_name)
        if end <= start and not spans_next_day:
            end = local_datetime_to_utc(work_date + timedelta(days=1), end_time_local, timezone_name)
        if end <= start:
            raise ValueError("Work-pattern end time must be after start time")
        return start, end, duration_minutes(start, end)
    minutes = max(int(fallback_minutes or 0), 0)
    return start, start + timedelta(minutes=minutes), minutes


def interval_overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return ensure_aware(a_start) < ensure_aware(b_end) and ensure_aware(b_start) < ensure_aware(a_end)


def duration_minutes(start: datetime, end: datetime) -> int:
    start = ensure_aware(start)
    end = ensure_aware(end)
    if end <= start:
        return 0
    return max(int((end - start).total_seconds() // 60), 0)


def overlap_minutes(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> int:
    start = max(ensure_aware(a_start), ensure_aware(b_start))
    end = min(ensure_aware(a_end), ensure_aware(b_end))
    return duration_minutes(start, end)


def period_bounds_utc(from_date: date, to_date: date, timezone_name: str) -> tuple[datetime, datetime]:
    if to_date < from_date:
        raise ValueError("to date must be on or after from date")
    zone = get_zone(timezone_name)
    start = datetime.combine(from_date, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return start, end


def calculate_attendance_totals(
    events: Sequence[models.AttendanceEvent],
    *,
    window_start: Optional[datetime] = None,
    window_end: Optional[datetime] = None,
) -> AttendanceTotals:
    """Pair clock events deterministically and calculate payable presence.

    Invalid sequences never create negative time.  They are reported as
    warnings and marked incomplete so supervisors can correct the source data.
    MANUAL_ADJUSTMENT events may contain ``metadata_json.minutes`` and are
    applied directly to paid minutes.
    """

    ordered = sorted(events, key=lambda row: (ensure_aware(row.occurred_at), row.id))
    active_start: Optional[datetime] = None
    break_start: Optional[datetime] = None
    presence = 0
    breaks = 0
    manual = 0
    warnings: list[str] = []

    for event in ordered:
        at = ensure_aware(event.occurred_at)
        if window_start and at < ensure_aware(window_start):
            continue
        if window_end and at >= ensure_aware(window_end):
            continue
        event_type = event.event_type
        if event_type == models.AttendanceEventType.CLOCK_IN:
            if active_start is not None:
                warnings.append("Duplicate clock-in ignored")
                continue
            active_start = at
            break_start = None
        elif event_type == models.AttendanceEventType.BREAK_START:
            if active_start is None:
                warnings.append("Break start without clock-in ignored")
            elif break_start is not None:
                warnings.append("Duplicate break start ignored")
            else:
                break_start = at
        elif event_type == models.AttendanceEventType.BREAK_END:
            if active_start is None or break_start is None:
                warnings.append("Break end without active break ignored")
            elif at <= break_start:
                warnings.append("Invalid break interval ignored")
            else:
                breaks += duration_minutes(break_start, at)
                break_start = None
        elif event_type == models.AttendanceEventType.CLOCK_OUT:
            if active_start is None:
                warnings.append("Clock-out without clock-in ignored")
                continue
            if at <= active_start:
                warnings.append("Invalid attendance interval ignored")
                active_start = None
                break_start = None
                continue
            presence += duration_minutes(active_start, at)
            if break_start is not None:
                breaks += duration_minutes(break_start, at)
                warnings.append("Open break closed at clock-out")
            active_start = None
            break_start = None
        elif event_type == models.AttendanceEventType.MANUAL_ADJUSTMENT:
            metadata = event.metadata_json or {}
            try:
                manual += int(metadata.get("minutes", 0))
            except (TypeError, ValueError):
                warnings.append("Manual adjustment without numeric minutes ignored")

    incomplete = active_start is not None
    if active_start is not None:
        warnings.append("Open clock-in requires correction")
    paid = max(presence - breaks + manual, 0)
    return AttendanceTotals(
        presence_minutes=max(presence, 0),
        break_minutes=max(breaks, 0),
        paid_minutes=paid,
        incomplete=incomplete,
        warnings=tuple(warnings),
    )


def resolve_cycle_day(*, work_date: date, cycle_anchor_date: date, cycle_length_days: int) -> int:
    if cycle_length_days <= 0:
        raise ValueError("cycle_length_days must be positive")
    return (work_date - cycle_anchor_date).days % cycle_length_days


def preview_work_pattern(
    *,
    assignment: models.EmployeeWorkPatternAssignment,
    pattern_days: Mapping[int, models.WorkPatternDay],
    from_date: date,
    to_date: date,
    timezone_name: str,
) -> list[PatternOccurrence]:
    if to_date < from_date:
        raise ValueError("Roster period end must not precede its start")
    pattern = assignment.work_pattern
    effective_start = max(from_date, assignment.effective_from)
    effective_end = min(to_date, assignment.effective_to or to_date)
    if effective_end < effective_start:
        return []

    output: list[PatternOccurrence] = []
    current = effective_start
    while current <= effective_end:
        cycle_index = resolve_cycle_day(
            work_date=current,
            cycle_anchor_date=assignment.cycle_anchor_date,
            cycle_length_days=pattern.cycle_length_days,
        )
        day = pattern_days.get(cycle_index)
        if day is not None:
            starts_at, ends_at, minutes = local_shift_window_to_utc(
                work_date=current,
                start_time_local=day.start_time_local,
                end_time_local=day.end_time_local,
                timezone_name=timezone_name or pattern.timezone_name,
                spans_next_day=day.spans_next_day,
                fallback_minutes=day.planned_minutes,
            )
            output.append(
                PatternOccurrence(
                    user_id=assignment.user_id,
                    work_date=current,
                    cycle_day_index=cycle_index,
                    status=day.status,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    planned_minutes=minutes,
                    shift_template_id=day.shift_template_id,
                    source_reference_id=f"{assignment.id}:{current.isoformat()}",
                )
            )
        current += timedelta(days=1)
    return output


def group_minutes_by_local_day(
    intervals: Iterable[tuple[datetime, datetime, int]],
    *,
    timezone_name: str,
) -> dict[date, int]:
    zone = get_zone(timezone_name)
    totals: dict[date, int] = defaultdict(int)
    for start, end, explicit_minutes in intervals:
        start = ensure_aware(start).astimezone(zone)
        end = ensure_aware(end).astimezone(zone)
        minutes = max(int(explicit_minutes), 0)
        if minutes == 0:
            minutes = duration_minutes(start, end)
        if start.date() == end.date() or end <= start:
            totals[start.date()] += minutes
            continue
        total_duration = max((end - start).total_seconds(), 1.0)
        cursor = start
        allocated = 0
        while cursor.date() < end.date():
            boundary = datetime.combine(cursor.date() + timedelta(days=1), time.min, tzinfo=zone)
            share = round(minutes * ((boundary - cursor).total_seconds() / total_duration))
            totals[cursor.date()] += max(share, 0)
            allocated += max(share, 0)
            cursor = boundary
        totals[end.date()] += max(minutes - allocated, 0)
    return dict(sorted(totals.items(), key=lambda item: item[0]))
