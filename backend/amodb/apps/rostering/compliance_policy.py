from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from . import models, validation
from .code_registry_models import RosterDutySemantic, RosterShiftTemplatePolicy


STATUTORY_TOTAL_HOURS_RULE = "MAX_DUTY_14D_116H"
NORMAL_HOURS_CLASSIFICATION_RULE = "MAX_NORMAL_DUTY_7D_52H"
CONSECUTIVE_DUTY_RULE = "MAX_CONSECUTIVE_DUTY_DAYS_6"
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


def assignment_is_protected_rest(
    row: Any,
    *,
    policies: dict[str, RosterShiftTemplatePolicy] | None = None,
) -> bool:
    """Resolve protected rest from configured semantics rather than code text.

    OFF and REST are equivalent protected-rest semantics. A future tenant code
    can therefore become protected rest without changing the validator, while
    leave/sickness/non-duty categories are not silently treated as weekly rest.
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
    return str(code or "").upper() in {
        STATUTORY_TOTAL_HOURS_RULE,
        CONSECUTIVE_DUTY_RULE,
        PROTECTED_REST_RULE,
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
        configured = int(parameters.get("maximum_days") or 6)
        parameters["maximum_days"] = min(configured, 6)
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
        parameters.setdefault("classification", "ORDINARY_OT")
        parameters.setdefault("minimum_multiplier", 1.5)
        row.parameters_json = parameters
        # Crossing normal hours classifies excess time as overtime. It is not
        # the separate rolling total-hours illegality threshold.
        row.severity = models.RosterValidationSeverity.WARNING
        row.allow_override = False


def _local_date(row: Any, timezone_name: str) -> date:
    try:
        zone = ZoneInfo(timezone_name or "UTC")
    except Exception:
        zone = ZoneInfo("UTC")
    return row.starts_at.astimezone(zone).date()


def _finding(
    *,
    user_id: str,
    rule_id: str | None,
    message: str,
    details: dict[str, Any],
) -> validation.FindingSpec:
    return validation.FindingSpec(
        source=models.RosterValidationSource.RULE,
        severity=models.RosterValidationSeverity.BLOCKER,
        code=PROTECTED_REST_FINDING,
        message=message,
        user_id=user_id,
        rule_id=rule_id,
        details=details,
        overridable=False,
        sort_order=54,
    )


def _protected_rest_specs(
    version: models.RosterVersion,
    assignments: Sequence[models.RosterAssignment],
    rules: Sequence[models.RosterRule],
    *,
    policies: dict[str, RosterShiftTemplatePolicy] | None = None,
) -> list[validation.FindingSpec]:
    """Add explicit protected-rest blockers without inventing code semantics.

    The existing REQUIRED_DAYS_OFF rule remains the continuous-hours check.
    This companion rule closes two operational gaps: seven consecutive local
    duty dates cannot be published, and a rostered protected-rest date that is
    worked must have another explicit protected-rest date assigned.
    """

    timezone_name = version.period.timezone_name or "UTC"
    duty_by_user: dict[str, list[models.RosterAssignment]] = defaultdict(list)
    rest_by_user: dict[str, list[models.RosterAssignment]] = defaultdict(list)
    for row in assignments:
        if assignment_counts_as_duty(row):
            duty_by_user[row.user_id].append(row)
        elif assignment_is_protected_rest(row, policies=policies):
            rest_by_user[row.user_id].append(row)

    findings: list[validation.FindingSpec] = []
    period_start = version.period.starts_on
    period_end = version.period.ends_on

    for user_id, duty_rows in duty_by_user.items():
        duty_dates = {_local_date(row, timezone_name) for row in duty_rows}
        candidate_rest_dates = {_local_date(row, timezone_name) for row in rest_by_user.get(user_id, [])}
        valid_rest_dates = candidate_rest_dates - duty_dates
        worked_rest_dates = sorted(candidate_rest_dates & duty_dates)
        first_assignment = min(duty_rows, key=lambda row: row.starts_at)
        rest_rule = validation.find_rule(rules, models.RosterRuleType.REQUIRED_DAYS_OFF, first_assignment)
        rule_id = getattr(rest_rule, "id", None)

        cursor = period_start
        consecutive_blocked = False
        while cursor + timedelta(days=6) <= period_end:
            window_end = cursor + timedelta(days=6)
            window_dates = {cursor + timedelta(days=offset) for offset in range(7)}
            if window_dates.issubset(duty_dates):
                findings.append(
                    _finding(
                        user_id=user_id,
                        rule_id=rule_id,
                        message=(
                            "Seven consecutive local duty dates consume the employee's protected weekly rest. "
                            "Replan the sequence with a valid protected rest day before publication."
                        ),
                        details={
                            "window_start": cursor.isoformat(),
                            "window_end": window_end.isoformat(),
                            "duty_dates": sorted(item.isoformat() for item in window_dates),
                            "required_replacement_rest": True,
                        },
                    )
                )
                consecutive_blocked = True
                break
            cursor += timedelta(days=1)

        if consecutive_blocked:
            continue

        for worked_rest in worked_rest_dates:
            replacement_end = min(worked_rest + timedelta(days=7), period_end)
            replacements = sorted(
                day for day in valid_rest_dates if worked_rest < day <= replacement_end
            )
            if replacements:
                continue
            findings.append(
                _finding(
                    user_id=user_id,
                    rule_id=rule_id,
                    message=(
                        "A scheduled protected rest day is also assigned as duty. "
                        "Assign a replacement protected rest day before publication."
                    ),
                    details={
                        "worked_rest_date": worked_rest.isoformat(),
                        "replacement_due_by": replacement_end.isoformat(),
                        "required_replacement_rest": True,
                    },
                )
            )
            break
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
        policies = {
            str(row.shift_template_id): row
            for row in db.query(RosterShiftTemplatePolicy)
            .filter(RosterShiftTemplatePolicy.amo_id == version.amo_id)
            .all()
        }
        specs.extend(
            _protected_rest_specs(
                version,
                assignments,
                rules,
                policies=policies,
            )
        )
        return specs

    validation._is_productive = assignment_counts_as_duty
    validation.active_rules = governed_active_rules
    validation.build_findings = governed_build_findings
    _INSTALLED = True


__all__ = [
    "CONSECUTIVE_DUTY_RULE",
    "NORMAL_HOURS_CLASSIFICATION_RULE",
    "PROTECTED_REST_FINDING",
    "PROTECTED_REST_RULE",
    "STATUTORY_TOTAL_HOURS_RULE",
    "assignment_counts_as_duty",
    "assignment_is_protected_rest",
    "install_validation_policy",
    "statutory_rule_is_non_overridable",
]
