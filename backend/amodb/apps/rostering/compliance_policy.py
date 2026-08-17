from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from . import models, validation


STATUTORY_TOTAL_HOURS_RULE = "MAX_DUTY_14D_116H"
NORMAL_HOURS_CLASSIFICATION_RULE = "MAX_NORMAL_DUTY_7D_52H"
PROTECTED_REST_RULE = "REST_DAY_24H_IN_7D"
PROTECTED_REST_FINDING = "PROTECTED_REST_NOT_ASSIGNED"

_STATUTORY_TOTAL_MINUTES = 116 * 60
_NORMAL_WEEK_MINUTES = 52 * 60
_PROTECTED_REST_MINUTES = 24 * 60
_INSTALLED = False


def assignment_counts_as_duty(row: Any) -> bool:
    """Use the configured shift template, never the display code, as duty truth."""

    template = getattr(row, "shift_template", None)
    if template is not None:
        return bool(getattr(template, "counts_as_duty", False))
    return getattr(row, "status", None) in {
        models.RosterAssignmentStatus.DUTY,
        models.RosterAssignmentStatus.STANDBY,
        models.RosterAssignmentStatus.TRAINING,
    }


def assignment_is_protected_rest(row: Any) -> bool:
    """A protected rest assignment is an explicit non-duty OFF template."""

    template = getattr(row, "shift_template", None)
    if template is None or bool(getattr(template, "counts_as_duty", False)):
        return False
    return getattr(template, "kind", None) == models.ShiftTemplateKind.OFF


def statutory_rule_is_non_overridable(code: str) -> bool:
    return str(code or "").upper() in {STATUTORY_TOTAL_HOURS_RULE, PROTECTED_REST_RULE}


def _govern_rule(row: models.RosterRule) -> None:
    parameters = dict(row.parameters_json or {})
    if row.code == STATUTORY_TOTAL_HOURS_RULE:
        parameters["window_days"] = 14
        configured = int(parameters.get("maximum_minutes") or _STATUTORY_TOTAL_MINUTES)
        parameters["maximum_minutes"] = min(configured, _STATUTORY_TOTAL_MINUTES)
        row.parameters_json = parameters
        row.severity = models.RosterValidationSeverity.BLOCKER
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
        row.parameters_json = parameters
        # This threshold classifies excess time as overtime; it is not the statutory total-hours ceiling.
        row.severity = models.RosterValidationSeverity.WARNING


def _local_date(row: Any, timezone_name: str) -> date:
    try:
        zone = ZoneInfo(timezone_name or "UTC")
    except Exception:
        zone = ZoneInfo("UTC")
    return row.starts_at.astimezone(zone).date()


def _protected_rest_specs(
    version: models.RosterVersion,
    assignments: Sequence[models.RosterAssignment],
    rules: Sequence[models.RosterRule],
) -> list[validation.FindingSpec]:
    """Require an explicit protected rest assignment in every duty-bearing seven-day window.

    Empty calendar space is not treated as protected rest. If an OFF assignment is worked,
    that date is consumed and another explicit protected rest date must exist in the window.
    """

    timezone_name = version.period.timezone_name or "UTC"
    duty_by_user: dict[str, list[models.RosterAssignment]] = defaultdict(list)
    rest_by_user: dict[str, list[models.RosterAssignment]] = defaultdict(list)
    for row in assignments:
        if assignment_counts_as_duty(row):
            duty_by_user[row.user_id].append(row)
        elif assignment_is_protected_rest(row):
            rest_by_user[row.user_id].append(row)

    findings: list[validation.FindingSpec] = []
    period_start = version.period.starts_on
    period_end = version.period.ends_on

    for user_id, duty_rows in duty_by_user.items():
        duty_dates = {_local_date(row, timezone_name) for row in duty_rows}
        candidate_rest_dates = {_local_date(row, timezone_name) for row in rest_by_user.get(user_id, [])}
        valid_rest_dates = candidate_rest_dates - duty_dates
        first_assignment = min(duty_rows, key=lambda row: row.starts_at)
        rest_rule = validation.find_rule(rules, models.RosterRuleType.REQUIRED_DAYS_OFF, first_assignment)

        cursor = period_start
        while cursor <= period_end:
            window_end = min(cursor + timedelta(days=6), period_end)
            window_dates = {cursor + timedelta(days=offset) for offset in range((window_end - cursor).days + 1)}
            if len(window_dates) < 7:
                break
            if duty_dates & window_dates and not (valid_rest_dates & window_dates):
                findings.append(
                    validation.FindingSpec(
                        source=models.RosterValidationSource.RULE,
                        severity=models.RosterValidationSeverity.BLOCKER,
                        code=PROTECTED_REST_FINDING,
                        message=(
                            "A duty-bearing seven-day window has no explicit protected rest day. "
                            "Assign a valid replacement rest day before publication."
                        ),
                        user_id=user_id,
                        rule_id=getattr(rest_rule, "id", None),
                        details={
                            "window_start": cursor.isoformat(),
                            "window_end": window_end.isoformat(),
                            "duty_dates": sorted(item.isoformat() for item in duty_dates & window_dates),
                            "worked_rest_dates": sorted(item.isoformat() for item in candidate_rest_dates & duty_dates & window_dates),
                            "required_replacement_rest": True,
                        },
                        overridable=False,
                        sort_order=54,
                    )
                )
                break
            cursor += timedelta(days=1)
    return findings


def install_validation_policy() -> None:
    """Install the stronger policy at the existing validator compatibility boundary."""

    global _INSTALLED
    if _INSTALLED:
        return

    original_active_rules = validation.active_rules
    original_build_findings = validation.build_findings

    def governed_active_rules(db, *, amo_id: str, on_date: date):
        rows = original_active_rules(db, amo_id=amo_id, on_date=on_date)
        for row in rows:
            _govern_rule(row)
        return rows

    def governed_build_findings(db, *, version, rules):
        specs = original_build_findings(db, version=version, rules=rules)
        assignments = [row for row in version.assignments or [] if row.deleted_at is None]
        specs.extend(_protected_rest_specs(version, assignments, rules))
        return specs

    validation._is_productive = assignment_counts_as_duty
    validation.active_rules = governed_active_rules
    validation.build_findings = governed_build_findings
    _INSTALLED = True


__all__ = [
    "NORMAL_HOURS_CLASSIFICATION_RULE",
    "PROTECTED_REST_FINDING",
    "PROTECTED_REST_RULE",
    "STATUTORY_TOTAL_HOURS_RULE",
    "assignment_counts_as_duty",
    "assignment_is_protected_rest",
    "install_validation_policy",
    "statutory_rule_is_non_overridable",
]
