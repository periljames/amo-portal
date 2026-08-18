from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from . import compliance_policy

_INSTALLED = False
_EPSILON = timedelta(microseconds=1)


def _clip(value: datetime, minimum: datetime, maximum: datetime) -> datetime:
    return max(minimum, min(value, maximum))


def _merge_ranges(ranges: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    ordered = sorted((start, end) for start, end in ranges if end >= start)
    merged: list[tuple[datetime, datetime]] = []
    for start, end in ordered:
        if not merged or start > merged[-1][1] + _EPSILON:
            merged.append((start, end))
            continue
        merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _free_ranges(
    intervals: Sequence[compliance_policy.DutyInterval],
    *,
    horizon_start: datetime,
    horizon_end: datetime,
) -> list[tuple[datetime, datetime]]:
    cursor = horizon_start
    free: list[tuple[datetime, datetime]] = []
    for item in intervals:
        if item.ends_at <= horizon_start:
            continue
        if item.starts_at >= horizon_end:
            break
        start = max(item.starts_at, horizon_start)
        end = min(item.ends_at, horizon_end)
        if start > cursor:
            free.append((cursor, start))
        if end > cursor:
            cursor = end
    if cursor < horizon_end:
        free.append((cursor, horizon_end))
    return free


def _relevant_window_ranges(
    intervals: Sequence[compliance_policy.DutyInterval],
    *,
    current_assignment_ids: set[str],
    evaluation_start: datetime,
    evaluation_end: datetime,
    window: timedelta,
) -> list[tuple[datetime, datetime]]:
    if not current_assignment_ids:
        return [(evaluation_start, evaluation_end)]
    ranges: list[tuple[datetime, datetime]] = []
    for item in intervals:
        if not current_assignment_ids.intersection(item.assignment_ids):
            continue
        # A duty interval overlaps [t, t+window] only where
        # item.starts_at < t+window and item.ends_at > t. Use one microsecond
        # inside the strict boundaries so a duty ending exactly at a window
        # start (or starting exactly at its end) is not treated as overlap.
        start = max(evaluation_start, item.starts_at - window + _EPSILON)
        end = min(evaluation_end, item.ends_at - _EPSILON)
        if start <= end:
            ranges.append((start, end))
    return _merge_ranges(ranges)


def _first_uncovered(
    coverage: Sequence[tuple[datetime, datetime]],
    *,
    start: datetime,
    end: datetime,
) -> datetime | None:
    candidate = start
    for covered_start, covered_end in coverage:
        if covered_end < candidate:
            continue
        if covered_start > end:
            break
        if covered_start > candidate:
            return candidate
        candidate = max(candidate, covered_end + _EPSILON)
        if candidate > end:
            return None
    return candidate if candidate <= end else None


def protected_rest_violation(
    intervals: Sequence[compliance_policy.DutyInterval],
    *,
    evaluation_start: datetime,
    evaluation_end: datetime,
    current_assignment_ids: set[str] | None = None,
    window: timedelta = timedelta(days=7),
    required_rest: timedelta = timedelta(hours=24),
) -> dict | None:
    """Evaluate every rolling window exactly using interval coverage.

    Let L = window - required_rest. A qualifying free gap [g0, g1] permits a
    protected-rest period to start anywhere in [g0, g1-required_rest]. Such a
    rest period can satisfy every rolling-window start t in
    [rest_start-L, rest_start]. Unioning these satisfaction ranges gives the
    complete continuous set of compliant window starts; any uncovered relevant
    start is a hard violation. This avoids minute/day sampling entirely.
    """

    merged = compliance_policy._merge_intervals(intervals)
    if not merged:
        return None
    start = compliance_policy._aware_utc(evaluation_start)
    end = compliance_policy._aware_utc(evaluation_end)
    if end < start:
        return None
    if required_rest <= timedelta(0) or required_rest > window:
        raise ValueError("required_rest must be positive and no longer than the rolling window")

    latest_window_end = end + window
    free = _free_ranges(
        merged,
        horizon_start=start,
        horizon_end=latest_window_end,
    )
    lead = window - required_rest
    satisfaction_ranges: list[tuple[datetime, datetime]] = []
    for free_start, free_end in free:
        if free_end - free_start < required_rest:
            continue
        latest_rest_start = free_end - required_rest
        satisfaction_ranges.append((free_start - lead, latest_rest_start))
    coverage = _merge_ranges([
        (max(start, covered_start), min(end, covered_end))
        for covered_start, covered_end in satisfaction_ranges
        if covered_end >= start and covered_start <= end
    ])

    relevant = _relevant_window_ranges(
        merged,
        current_assignment_ids=current_assignment_ids or set(),
        evaluation_start=start,
        evaluation_end=end,
        window=window,
    )
    violation_start: datetime | None = None
    for relevant_start, relevant_end in relevant:
        violation_start = _first_uncovered(
            coverage,
            start=relevant_start,
            end=relevant_end,
        )
        if violation_start is not None:
            break
    if violation_start is None:
        return None

    violation_end = violation_start + window
    longest, rest_start, rest_end = compliance_policy._longest_free_period(
        merged,
        window_start=violation_start,
        window_end=violation_end,
    )
    overlapping = [
        item
        for item in merged
        if item.starts_at < violation_end and item.ends_at > violation_start
    ]
    return {
        "window_start": violation_start.isoformat(),
        "window_end": violation_end.isoformat(),
        "window_minutes": int(window.total_seconds() // 60),
        "longest_rest_minutes": longest,
        "longest_rest_start": rest_start.isoformat(),
        "longest_rest_end": rest_end.isoformat(),
        "required_rest_minutes": int(required_rest.total_seconds() // 60),
        "duty_intervals": [
            {
                "starts_at": item.starts_at.isoformat(),
                "ends_at": item.ends_at.isoformat(),
                "assignment_ids": list(item.assignment_ids),
                "source": item.source,
            }
            for item in overlapping
        ],
    }


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    compliance_policy.protected_rest_violation = protected_rest_violation
    _INSTALLED = True


__all__ = ["install", "protected_rest_violation"]
