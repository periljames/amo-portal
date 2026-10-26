"""MOPM 1.6.1 default floors, independent of optional tenant rule sets.

Planned duty cannot use the unscheduled extension allowance. Actual recorded
duty over twelve hours is reported for documented unscheduled review, and
sixteen hours is an absolute maximum. Existing stricter rules also apply.
"""
from collections import defaultdict
from datetime import timedelta

from . import models, validation

PREFIX = "MOPM_DUTY_"


def duty_findings(version, assignments, *, actual_by_assignment=None):
    # Imported here to keep the existing validator installation boundary intact.
    from .compliance_policy import _effective_interval, _merge_intervals

    current = {str(row.id) for row in version.assignments or [] if row.deleted_at is None}
    grouped = defaultdict(list)
    for row in assignments:
        interval = _effective_interval(row, actual_by_assignment=actual_by_assignment)
        if interval:
            grouped[str(row.user_id)].append(interval)
    result = []

    def add(code, user_id, ids, message, details, *, warning=False):
        relevant = current.intersection(ids)
        if not relevant:
            return
        result.append(validation.FindingSpec(
            source=models.RosterValidationSource.RULE,
            severity=models.RosterValidationSeverity.WARNING if warning else models.RosterValidationSeverity.BLOCKER,
            code=PREFIX + code, message=message, user_id=user_id,
            assignment_id=sorted(relevant)[0], overridable=False,
            details={"reference": "MOPM 1.6.1", **details}, sort_order=53,
        ))

    for user_id, raw in grouped.items():
        intervals = _merge_intervals(raw)
        for item in intervals:
            source = "ACTUAL" if all(key in (actual_by_assignment or {}) for key in item.assignment_ids) else "PLANNED"
            minutes = (item.ends_at - item.starts_at).total_seconds() / 60
            if minutes > 960 or (source == "PLANNED" and minutes > 720):
                add("SHIFT_LIMIT", user_id, item.assignment_ids,
                    "MOPM duty limit exceeded: plan no more than 12 hours; unscheduled actual duty must never exceed 16 hours.",
                    {"duty_minutes": minutes, "source": source})
            elif source == "ACTUAL" and minutes > 720:
                add("UNSCHEDULED_REVIEW", user_id, item.assignment_ids,
                    "Actual duty exceeded 12 hours. Record the unscheduled extension and fatigue review; at least 11 hours rest follows shift duty.",
                    {"duty_minutes": minutes}, warning=True)
        for previous, following in zip(intervals, intervals[1:]):
            rest = (following.starts_at - previous.ends_at).total_seconds() / 60
            if rest < 660:
                add("REST_LIMIT", user_id, (*previous.assignment_ids, *following.assignment_ids),
                    "MOPM shift duty requires at least 11 hours between duties.", {"rest_minutes": rest, "minimum_minutes": 660})
        # Any maximum of a rolling sum occurs when a duty endpoint touches a
        # window endpoint. Union intervals prevent overlapping work being counted twice.
        candidates = {item.starts_at for item in intervals} | {item.ends_at - timedelta(days=7) for item in intervals}
        for start in sorted(candidates):
            end = start + timedelta(days=7)
            included = [item for item in intervals if item.starts_at < end and item.ends_at > start]
            minutes = sum((min(item.ends_at, end) - max(item.starts_at, start)).total_seconds() / 60 for item in included)
            if minutes > 4320:
                ids = [key for item in included for key in item.assignment_ids]
                add("WEEK_LIMIT", user_id, ids, "MOPM duty must not exceed 72 hours in any rolling seven days.",
                    {"duty_minutes": minutes, "maximum_minutes": 4320, "window_start": start.isoformat(), "window_end": end.isoformat()})
                if current.intersection(ids):
                    break
    return result
