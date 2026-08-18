from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from ..workforce import models as workforce_models
from . import models, validation
from .code_registry_models import RosterDutySemantic, RosterShiftTemplatePolicy


STATUTORY_TOTAL_HOURS_RULE = "MAX_DUTY_14D_116H"
NORMAL_HOURS_CLASSIFICATION_RULE = "MAX_NORMAL_DUTY_7D_52H"
CONSECUTIVE_DUTY_RULE = "MAX_CONSECUTIVE_DUTY_DAYS_6"
PROTECTED_REST_RULE = "REST_DAY_24H_IN_7D"
PROTECTED_REST_FINDING = "ROSTER_PROTECTED_REST_VIOLATION"

_STATUTORY_TOTAL_MINUTES = 116 * 60
_NORMAL_WEEK_MINUTES = 52 * 60
_PROTECTED_REST_MINUTES = 24 * 60
_PROTECTED_REST_WINDOW = timedelta(days=7)
_INSTALLED = False
UTC = timezone.utc


@dataclass(frozen=True)
class DutyInterval:
    """One effective period during which the employee is not relieved from duty."""

    starts_at: datetime
    ends_at: datetime
    assignment_ids: tuple[str, ...] = ()
    source: str = "PLANNED"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def assignment_counts_as_duty(row: Any) -> bool:
    """Use configured shift semantics, never a display code, as duty truth."""

    template = getattr(row, "shift_template", None)
    if template is not None:
        return bool(getattr(template, "counts_as_duty", False))
    return getattr(row, "status", None) in {
        models.RosterAssignmentStatus.DUTY,
        models.RosterAssignmentStatus.STANDBY,
        models.RosterAssignmentStatus.TRAINING,
    }


def assignment_is_protected_rest(
    row: Any,
    *,
    policies: dict[str, RosterShiftTemplatePolicy] | None = None,
) -> bool:
    """Resolve a configured OFF/REST label for UI and planning purposes only.

    A nominal OFF/REST assignment is evidence that rest was planned. It is not
    used to prove the statutory protected-rest result; that result is derived
    exclusively from the employee's effective duty intervals.
    """

    template = getattr(row, "shift_template", None)
    if template is None:
        return getattr(row, "status", None) == models.RosterAssignmentStatus.OFF
    if bool(getattr(template, "counts_as_duty", False)):
        return False
    if policies is not None:
        policy = policies.get(str(getattr(template, "id", "")))
        if policy is not None:
            return policy.duty_semantic in {
                RosterDutySemantic.REST,
                RosterDutySemantic.OFF,
            }
    return getattr(template, "kind", None) == models.ShiftTemplateKind.OFF


def statutory_rule_is_non_overridable(code: str) -> bool:
    """Return True only for rules governed here as non-waivable hard limits."""

    return str(code or "").upper() in {
        STATUTORY_TOTAL_HOURS_RULE,
        PROTECTED_REST_RULE,
        PROTECTED_REST_FINDING,
    }


def _govern_rule(row: models.RosterRule) -> None:
    parameters = dict(row.parameters_json or {})
    if row.code == STATUTORY_TOTAL_HOURS_RULE:
        parameters["window_days"] = 14
        configured = int(parameters.get("maximum_minutes") or _STATUTORY_TOTAL_MINUTES)
        parameters["maximum_minutes"] = min(configured, _STATUTORY_TOTAL_MINUTES)
        row.parameters_json = parameters
        row.severity = models.RosterValidationSeverity.BLOCKER
        row.allow_override = False
    elif row.code == CONSECUTIVE_DUTY_RULE:
        # Consecutive calendar duty days are a useful fatigue/planning signal,
        # but they are not the authoritative 24h-in-7 protected-rest test.
        parameters.setdefault("maximum_days", 6)
        row.parameters_json = parameters
        row.severity = models.RosterValidationSeverity.WARNING
        row.allow_override = False
    elif row.code == PROTECTED_REST_RULE:
        parameters["window_days"] = 7
        configured = int(parameters.get("minimum_continuous_minutes") or 0)
        parameters["minimum_continuous_minutes"] = max(configured, _PROTECTED_REST_MINUTES)
        row.parameters_json = parameters
        row.severity = models.RosterValidationSeverity.BLOCKER
        row.allow_override = False
    elif row.code == NORMAL_HOURS_CLASSIFICATION_RULE:
        parameters["window_days"] = 7
        configured = int(parameters.get("maximum_minutes") or _NORMAL_WEEK_MINUTES)
        parameters["maximum_minutes"] = min(configured, _NORMAL_WEEK_MINUTES)
        parameters.setdefault("classification", "ORDINARY_OT")
        parameters.setdefault("minimum_multiplier", 1.5)
        row.parameters_json = parameters
        # Crossing normal hours classifies excess time as overtime. It is not
        # the separate rolling total-hours illegality threshold.
        row.severity = models.RosterValidationSeverity.WARNING
        row.allow_override = False


def _finding(
    *,
    user_id: str,
    rule_id: str | None,
    assignment_id: str | None,
    message: str,
    details: dict[str, Any],
) -> validation.FindingSpec:
    return validation.FindingSpec(
        source=models.RosterValidationSource.RULE,
        severity=models.RosterValidationSeverity.BLOCKER,
        code=PROTECTED_REST_FINDING,
        message=message,
        assignment_id=assignment_id,
        user_id=user_id,
        rule_id=rule_id,
        details=details,
        overridable=False,
        sort_order=54,
    )


def _merge_intervals(intervals: Iterable[DutyInterval]) -> list[DutyInterval]:
    ordered = sorted(
        (
            DutyInterval(
                starts_at=_aware_utc(item.starts_at),
                ends_at=_aware_utc(item.ends_at),
                assignment_ids=tuple(item.assignment_ids),
                source=item.source,
            )
            for item in intervals
            if _aware_utc(item.ends_at) > _aware_utc(item.starts_at)
        ),
        key=lambda item: (item.starts_at, item.ends_at, item.assignment_ids),
    )
    merged: list[DutyInterval] = []
    for item in ordered:
        if not merged or item.starts_at > merged[-1].ends_at:
            merged.append(item)
            continue
        previous = merged[-1]
        merged[-1] = DutyInterval(
            starts_at=previous.starts_at,
            ends_at=max(previous.ends_at, item.ends_at),
            assignment_ids=tuple(sorted(set(previous.assignment_ids + item.assignment_ids))),
            source="ACTUAL" if "ACTUAL" in {previous.source, item.source} else previous.source,
        )
    return merged


def _effective_interval(
    row: Any,
    *,
    actual_by_assignment: Mapping[str, tuple[datetime, datetime]] | None = None,
) -> DutyInterval | None:
    if not assignment_counts_as_duty(row):
        return None
    assignment_id = str(getattr(row, "id", ""))
    actual = (actual_by_assignment or {}).get(assignment_id)
    if actual is not None:
        actual_start, actual_end = actual
        if _aware_utc(actual_end) > _aware_utc(actual_start):
            return DutyInterval(
                starts_at=_aware_utc(actual_start),
                ends_at=_aware_utc(actual_end),
                assignment_ids=(assignment_id,) if assignment_id else (),
                source="ACTUAL",
            )
    starts_at = getattr(row, "starts_at", None)
    ends_at = getattr(row, "ends_at", None)
    if starts_at is None or ends_at is None:
        return None
    return DutyInterval(
        starts_at=_aware_utc(starts_at),
        ends_at=_aware_utc(ends_at),
        assignment_ids=(assignment_id,) if assignment_id else (),
        source="PLANNED",
    )


def _longest_free_period(
    intervals: Sequence[DutyInterval],
    *,
    window_start: datetime,
    window_end: datetime,
) -> tuple[int, datetime, datetime]:
    cursor = window_start
    best_start = window_start
    best_end = window_start
    for item in intervals:
        if item.ends_at <= window_start:
            continue
        if item.starts_at >= window_end:
            break
        starts_at = max(item.starts_at, window_start)
        ends_at = min(item.ends_at, window_end)
        if starts_at > cursor and starts_at - cursor > best_end - best_start:
            best_start, best_end = cursor, starts_at
        if ends_at > cursor:
            cursor = ends_at
    if cursor < window_end and window_end - cursor > best_end - best_start:
        best_start, best_end = cursor, window_end
    return int((best_end - best_start).total_seconds() // 60), best_start, best_end


def _candidate_window_starts(
    intervals: Sequence[DutyInterval],
    *,
    start_min: datetime,
    start_max: datetime,
    window: timedelta,
    required_rest: timedelta,
) -> list[datetime]:
    """Return exact event-boundary candidates for a continuous rolling test.

    The maximum free gap in a fixed-size sliding window can only change slope
    when a window/rest boundary crosses a duty boundary. Evaluating those
    breakpoints avoids minute-by-minute scans while preserving timestamp-level
    behaviour for large monthly rosters.
    """

    candidates = {start_min, start_max}
    offsets = (
        timedelta(0),
        window,
        required_rest,
        window - required_rest,
    )
    for item in intervals:
        for boundary in (item.starts_at, item.ends_at):
            for offset in offsets:
                candidate = boundary - offset
                if start_min <= candidate <= start_max:
                    candidates.add(candidate)
    return sorted(candidates)


def protected_rest_violation(
    intervals: Sequence[DutyInterval],
    *,
    evaluation_start: datetime,
    evaluation_end: datetime,
    current_assignment_ids: set[str] | None = None,
    window: timedelta = _PROTECTED_REST_WINDOW,
    required_rest: timedelta = timedelta(minutes=_PROTECTED_REST_MINUTES),
) -> dict[str, Any] | None:
    """Find the first rolling seven-day window lacking 24h continuous release.

    OFF/RD/RR codes are intentionally absent from this calculation. A person is
    at rest only where the merged effective-duty timeline contains no duty.
    """

    merged = _merge_intervals(intervals)
    if not merged:
        return None
    start_min = _aware_utc(evaluation_start)
    start_max = _aware_utc(evaluation_end)
    if start_max < start_min:
        return None
    current_ids = current_assignment_ids or set()
    for window_start in _candidate_window_starts(
        merged,
        start_min=start_min,
        start_max=start_max,
        window=window,
        required_rest=required_rest,
    ):
        window_end = window_start + window
        overlapping = [
            item for item in merged
            if item.starts_at < window_end and item.ends_at > window_start
        ]
        if not overlapping:
            continue
        if current_ids and not any(
            current_ids.intersection(item.assignment_ids) for item in overlapping
        ):
            continue
        longest, rest_start, rest_end = _longest_free_period(
            merged,
            window_start=window_start,
            window_end=window_end,
        )
        required_minutes = int(required_rest.total_seconds() // 60)
        if longest >= required_minutes:
            continue
        return {
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "window_minutes": int(window.total_seconds() // 60),
            "longest_rest_minutes": longest,
            "longest_rest_start": rest_start.isoformat(),
            "longest_rest_end": rest_end.isoformat(),
            "required_rest_minutes": required_minutes,
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
    return None


def _period_bounds(version: models.RosterVersion) -> tuple[datetime, datetime]:
    try:
        zone = ZoneInfo(version.period.timezone_name or "UTC")
    except Exception:
        zone = ZoneInfo("UTC")
    start = datetime.combine(version.period.starts_on, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(version.period.ends_on + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return start, end


def _actual_intervals(
    db,
    *,
    amo_id: str,
    assignment_ids: Sequence[str],
) -> dict[str, tuple[datetime, datetime]]:
    if not assignment_ids:
        return {}
    rows = db.query(workforce_models.AttendanceEvent).filter(
        workforce_models.AttendanceEvent.amo_id == amo_id,
        workforce_models.AttendanceEvent.roster_assignment_id.in_(assignment_ids),
        workforce_models.AttendanceEvent.event_type.in_([
            workforce_models.AttendanceEventType.CLOCK_IN,
            workforce_models.AttendanceEventType.CLOCK_OUT,
        ]),
    ).order_by(
        workforce_models.AttendanceEvent.roster_assignment_id.asc(),
        workforce_models.AttendanceEvent.occurred_at.asc(),
        workforce_models.AttendanceEvent.id.asc(),
    ).all()
    by_assignment: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        if row.roster_assignment_id:
            by_assignment[str(row.roster_assignment_id)].append(row)
    result: dict[str, tuple[datetime, datetime]] = {}
    for assignment_id, events in by_assignment.items():
        clock_ins = [row.occurred_at for row in events if row.event_type == workforce_models.AttendanceEventType.CLOCK_IN]
        clock_outs = [row.occurred_at for row in events if row.event_type == workforce_models.AttendanceEventType.CLOCK_OUT]
        if not clock_ins or not clock_outs:
            continue
        starts_at = min(clock_ins)
        valid_outs = [value for value in clock_outs if _aware_utc(value) > _aware_utc(starts_at)]
        if valid_outs:
            result[assignment_id] = (starts_at, max(valid_outs))
    return result


def _duty_context(db, *, version: models.RosterVersion) -> list[models.RosterAssignment]:
    """Load current version plus bounded adjacent published duty once per run."""

    period_start, period_end = _period_bounds(version)
    context_start = period_start - _PROTECTED_REST_WINDOW
    context_end = period_end + _PROTECTED_REST_WINDOW
    current_rows = [row for row in version.assignments or [] if row.deleted_at is None]
    user_ids = sorted({row.user_id for row in current_rows if assignment_counts_as_duty(row)})
    if not user_ids:
        return current_rows
    rows = db.query(models.RosterAssignment).options(
        selectinload(models.RosterAssignment.shift_template),
    ).join(
        models.RosterVersion,
        models.RosterVersion.id == models.RosterAssignment.version_id,
    ).filter(
        models.RosterAssignment.amo_id == version.amo_id,
        models.RosterAssignment.user_id.in_(user_ids),
        models.RosterAssignment.deleted_at.is_(None),
        models.RosterAssignment.starts_at < context_end,
        models.RosterAssignment.ends_at > context_start,
        or_(
            models.RosterAssignment.version_id == version.id,
            models.RosterVersion.status == models.RosterVersionStatus.PUBLISHED,
        ),
    ).all()
    return rows


def _protected_rest_specs(
    version: models.RosterVersion,
    assignments: Sequence[models.RosterAssignment],
    rules: Sequence[models.RosterRule],
    *,
    actual_by_assignment: Mapping[str, tuple[datetime, datetime]] | None = None,
) -> list[validation.FindingSpec]:
    """Evaluate protected rest from effective timestamps, never rest-code names."""

    current_rows = [row for row in version.assignments or [] if row.deleted_at is None]
    current_by_user: dict[str, set[str]] = defaultdict(set)
    for row in current_rows:
        if assignment_counts_as_duty(row):
            current_by_user[str(row.user_id)].add(str(row.id))

    duty_by_user: dict[str, list[DutyInterval]] = defaultdict(list)
    first_assignment_by_user: dict[str, Any] = {}
    for row in assignments:
        interval = _effective_interval(row, actual_by_assignment=actual_by_assignment)
        if interval is None:
            continue
        user_id = str(row.user_id)
        duty_by_user[user_id].append(interval)
        first_assignment_by_user.setdefault(user_id, row)

    period_start, period_end = _period_bounds(version)
    findings: list[validation.FindingSpec] = []
    for user_id, current_ids in current_by_user.items():
        first_assignment = first_assignment_by_user.get(user_id)
        rest_rule = validation.find_rule(
            rules,
            models.RosterRuleType.REQUIRED_DAYS_OFF,
            first_assignment,
        )
        parameters = dict(getattr(rest_rule, "parameters_json", None) or {})
        window_days = max(int(parameters.get("window_days", 7)), 7)
        required_minutes = max(
            int(parameters.get("minimum_continuous_minutes", _PROTECTED_REST_MINUTES)),
            _PROTECTED_REST_MINUTES,
        )
        window = timedelta(days=window_days)
        required_rest = timedelta(minutes=required_minutes)
        # Include starts up to one full rolling window before the roster period
        # so a boundary-spanning failure cannot disappear at month rollover.
        violation = protected_rest_violation(
            duty_by_user.get(user_id, []),
            evaluation_start=period_start - window,
            evaluation_end=period_end,
            current_assignment_ids=current_ids,
            window=window,
            required_rest=required_rest,
        )
        if violation is None:
            continue
        assignment_id = next(iter(sorted(current_ids)), None)
        violation.update({
            "rule_code": PROTECTED_REST_RULE,
            "remediation_actions": [
                "ASSIGN_PROTECTED_REST",
                "REASSIGN_DUTY",
                "CHANGE_SHIFT",
                "VIEW_7_DAY_TIMELINE",
            ],
            "managerial_override_allowed": False,
            "personnel_acknowledgement_can_cure": False,
        })
        findings.append(
            _finding(
                user_id=user_id,
                rule_id=getattr(rest_rule, "id", None),
                assignment_id=assignment_id,
                message=(
                    "Protected Rest Required — Publication Blocked. No uninterrupted "
                    f"{required_minutes / 60:g}-hour period relieved from all duties exists "
                    f"within the applicable rolling {window_days}-day period. Personnel "
                    "acknowledgement or managerial approval cannot satisfy this requirement."
                ),
                details=violation,
            )
        )
    return findings


def install_validation_policy() -> None:
    """Install aviation policy at the existing validator compatibility boundary."""

    global _INSTALLED
    if _INSTALLED:
        return

    original_active_rules = validation.active_rules
    original_build_findings = validation.build_findings
    original_override_finding = validation.override_finding

    def governed_active_rules(db, *, amo_id: str, on_date: date):
        rows = original_active_rules(db, amo_id=amo_id, on_date=on_date)
        for row in rows:
            _govern_rule(row)
        return rows

    def governed_build_findings(db, *, version, rules):
        # The legacy REQUIRED_DAYS_OFF implementation is local-midnight anchored.
        # Remove that duplicate and replace it with the continuous timestamp rule.
        specs = [
            spec
            for spec in original_build_findings(db, version=version, rules=rules)
            if spec.code not in {PROTECTED_REST_RULE, PROTECTED_REST_FINDING}
        ]
        assignments = _duty_context(db, version=version)
        actuals = _actual_intervals(
            db,
            amo_id=version.amo_id,
            assignment_ids=[str(row.id) for row in assignments],
        )
        specs.extend(
            _protected_rest_specs(
                version,
                assignments,
                rules,
                actual_by_assignment=actuals,
            )
        )
        return specs

    def governed_override_finding(db, *, finding, actor_user_id: str, payload):
        rule_code = getattr(getattr(finding, "rule", None), "code", None) or finding.code
        if statutory_rule_is_non_overridable(rule_code) or finding.code == PROTECTED_REST_FINDING:
            raise ValueError(
                "This statutory roster finding cannot be overridden by personnel consent, "
                "managerial approval or administrator action. Resolve the roster or attach "
                "a separately governed regulatory exemption where supported."
            )
        return original_override_finding(
            db,
            finding=finding,
            actor_user_id=actor_user_id,
            payload=payload,
        )

    validation._is_productive = assignment_counts_as_duty
    validation.active_rules = governed_active_rules
    validation.build_findings = governed_build_findings
    validation.override_finding = governed_override_finding
    _INSTALLED = True


__all__ = [
    "CONSECUTIVE_DUTY_RULE",
    "DutyInterval",
    "NORMAL_HOURS_CLASSIFICATION_RULE",
    "PROTECTED_REST_FINDING",
    "PROTECTED_REST_RULE",
    "STATUTORY_TOTAL_HOURS_RULE",
    "assignment_counts_as_duty",
    "assignment_is_protected_rest",
    "install_validation_policy",
    "protected_rest_violation",
    "statutory_rule_is_non_overridable",
]
