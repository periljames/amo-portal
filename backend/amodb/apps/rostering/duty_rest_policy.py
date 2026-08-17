from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from . import models
from .code_registry_models import RosterDutySemantic, RosterShiftTemplatePolicy

UTC = timezone.utc

# These rules represent hard publication gates. Tenant configuration may be
# stricter, but it must not make the statutory/protected-rest floor overridable.
NON_OVERRIDABLE_RULE_CODES = frozenset(
    {
        "MAX_DUTY_14D_116H",
        "MAX_CONSECUTIVE_DUTY_DAYS_6",
        "REST_DAY_24H_IN_7D",
    }
)
NORMAL_HOURS_RULE_CODE = "MAX_NORMAL_DUTY_7D_52H"


def assignment_counts_as_duty(row: models.RosterAssignment) -> bool:
    """Return the configured duty meaning, never infer it from a code name.

    ShiftTemplate.counts_as_duty is authoritative for configured shifts such as
    D, SA, X, XH and any future tenant-defined working/standby code. The status
    fallback exists only for incomplete/imported rows that do not yet have a
    shift template.
    """

    template = getattr(row, "shift_template", None)
    if template is not None:
        return bool(template.counts_as_duty)
    return row.status in {
        models.RosterAssignmentStatus.DUTY,
        models.RosterAssignmentStatus.STANDBY,
        models.RosterAssignmentStatus.TRAINING,
    }


def _policy_by_template(
    db: Session,
    *,
    amo_id: str,
) -> dict[str, RosterShiftTemplatePolicy]:
    return {
        str(row.shift_template_id): row
        for row in db.query(RosterShiftTemplatePolicy)
        .filter(RosterShiftTemplatePolicy.amo_id == amo_id)
        .all()
    }


def assignment_is_protected_rest(
    row: models.RosterAssignment,
    *,
    policies: dict[str, RosterShiftTemplatePolicy],
) -> bool:
    """OFF and REST semantics are equivalent protected-rest assignments.

    This deliberately does not inspect literal shift codes. O, RD, or any future
    tenant label can represent protected rest when its configured semantic says
    so and the template does not count as duty.
    """

    if assignment_counts_as_duty(row):
        return False
    template = getattr(row, "shift_template", None)
    if template is None:
        return row.status == models.RosterAssignmentStatus.OFF
    policy = policies.get(str(template.id))
    if policy is not None:
        return policy.duty_semantic in {
            RosterDutySemantic.REST,
            RosterDutySemantic.OFF,
        }
    return template.kind == models.ShiftTemplateKind.OFF


def _merge_intervals(
    intervals: Sequence[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda value: (value[0], value[1]))
    merged: list[tuple[datetime, datetime]] = [ordered[0]]
    for starts_at, ends_at in ordered[1:]:
        previous_start, previous_end = merged[-1]
        if starts_at <= previous_end:
            merged[-1] = (previous_start, max(previous_end, ends_at))
        else:
            merged.append((starts_at, ends_at))
    return merged


def _protected_rest_findings(
    db: Session,
    *,
    version: models.RosterVersion,
    assignments: Sequence[models.RosterAssignment],
    rules: Sequence[models.RosterRule],
    validation_module: Any,
) -> list[Any]:
    """Require an explicit protected rest assignment in each governed window.

    A mere hole in the calendar is not treated as a rostered rest day. If an RD
    is worked, that rest record is consumed and another valid protected-rest
    interval must exist in the applicable rolling window.
    """

    policies = _policy_by_template(db, amo_id=version.amo_id)
    by_user: dict[str, list[models.RosterAssignment]] = defaultdict(list)
    for row in assignments:
        by_user[row.user_id].append(row)

    findings: list[Any] = []
    zone = validation_module.workforce_calculations.get_zone(
        version.period.timezone_name or "UTC"
    )
    period_start = datetime.combine(version.period.starts_on, time.min, tzinfo=zone).astimezone(UTC)
    period_end = datetime.combine(
        version.period.ends_on + timedelta(days=1), time.min, tzinfo=zone
    ).astimezone(UTC)

    for user_id, user_rows in by_user.items():
        duty_rows = sorted(
            (row for row in user_rows if assignment_counts_as_duty(row)),
            key=lambda row: (row.starts_at, row.ends_at, row.id),
        )
        if not duty_rows:
            continue
        rest_rows = sorted(
            (
                row
                for row in user_rows
                if assignment_is_protected_rest(row, policies=policies)
            ),
            key=lambda row: (row.starts_at, row.ends_at, row.id),
        )

        rule = validation_module.find_rule(
            rules,
            models.RosterRuleType.REQUIRED_DAYS_OFF,
            duty_rows[0],
        )
        if rule is None:
            continue
        parameters = validation_module._rule_parameters(rule)
        window_days = max(int(parameters.get("window_days", 7)), 1)
        required_minutes = max(
            int(parameters.get("minimum_continuous_minutes", 1440)), 1
        )

        # A rest assignment that overlaps duty is consumed and cannot itself
        # satisfy protected rest. Flag it directly so the planner can show the
        # exact rest record that needs compensating rest.
        consumed_rest_ids: set[str] = set()
        for rest in rest_rows:
            overlaps = [
                duty
                for duty in duty_rows
                if duty.starts_at < rest.ends_at and duty.ends_at > rest.starts_at
            ]
            if not overlaps:
                continue
            consumed_rest_ids.add(str(rest.id))
            findings.append(
                validation_module.FindingSpec(
                    source=models.RosterValidationSource.RULE,
                    severity=models.RosterValidationSeverity.BLOCKER,
                    code="PROTECTED_REST_WORKED",
                    message=(
                        "A protected rest assignment is overlapped by duty. "
                        "Assign replacement protected rest before publication."
                    ),
                    assignment_id=overlaps[-1].id,
                    user_id=user_id,
                    rule_id=rule.id,
                    details={
                        "protected_rest_assignment_id": rest.id,
                        "duty_assignment_ids": [row.id for row in overlaps],
                    },
                    overridable=False,
                    sort_order=53,
                )
            )

        valid_rest_intervals = _merge_intervals(
            [
                (row.starts_at, row.ends_at)
                for row in rest_rows
                if str(row.id) not in consumed_rest_ids
            ]
        )

        anchor = version.period.starts_on
        last_anchor = version.period.ends_on - timedelta(days=window_days - 1)
        while anchor <= last_anchor:
            window_start = datetime.combine(anchor, time.min, tzinfo=zone).astimezone(UTC)
            window_end = datetime.combine(
                anchor + timedelta(days=window_days), time.min, tzinfo=zone
            ).astimezone(UTC)
            window_duty = [
                row
                for row in duty_rows
                if row.starts_at < window_end and row.ends_at > window_start
            ]
            if not window_duty:
                anchor += timedelta(days=1)
                continue

            longest = 0
            qualifying_ids: list[str] = []
            for starts_at, ends_at in valid_rest_intervals:
                clipped_start = max(starts_at, window_start, period_start)
                clipped_end = min(ends_at, window_end, period_end)
                if clipped_end <= clipped_start:
                    continue
                duration = validation_module.workforce_calculations.duration_minutes(
                    clipped_start, clipped_end
                )
                longest = max(longest, duration)
                if duration >= required_minutes:
                    qualifying_ids.extend(
                        row.id
                        for row in rest_rows
                        if str(row.id) not in consumed_rest_ids
                        and row.starts_at <= clipped_start
                        and row.ends_at >= clipped_end
                    )
            if longest >= required_minutes:
                anchor += timedelta(days=1)
                continue

            findings.append(
                validation_module.FindingSpec(
                    source=models.RosterValidationSource.RULE,
                    severity=models.RosterValidationSeverity.BLOCKER,
                    code="PROTECTED_REST_NOT_ASSIGNED",
                    message=(
                        f"No explicit protected-rest assignment provides "
                        f"{required_minutes / 60:g} continuous hours in the "
                        f"{window_days}-day window starting {anchor.isoformat()}."
                    ),
                    assignment_id=window_duty[-1].id,
                    user_id=user_id,
                    rule_id=rule.id,
                    details={
                        "window_start": anchor.isoformat(),
                        "window_days": window_days,
                        "longest_explicit_rest_minutes": longest,
                        "required_rest_minutes": required_minutes,
                        "qualifying_rest_assignment_ids": qualifying_ids,
                    },
                    overridable=False,
                    sort_order=54,
                )
            )
            # One finding is enough to block publication and keeps the planner
            # actionable rather than flooding it with overlapping windows.
            break
    return findings


def _harden_seeded_rules(
    db: Session,
    *,
    amo_id: str,
) -> None:
    rows = (
        db.query(models.RosterRule)
        .filter(
            models.RosterRule.amo_id == amo_id,
            models.RosterRule.code.in_(
                list(NON_OVERRIDABLE_RULE_CODES | {NORMAL_HOURS_RULE_CODE})
            ),
        )
        .all()
    )
    for row in rows:
        if row.code in NON_OVERRIDABLE_RULE_CODES:
            row.severity = models.RosterValidationSeverity.BLOCKER
            row.allow_override = False
        elif row.code == NORMAL_HOURS_RULE_CODE:
            # Crossing normal hours is an overtime classification signal, not
            # an unlawful-roster blocker. Keep it visible as a warning.
            row.severity = models.RosterValidationSeverity.WARNING
            row.allow_override = False
            parameters = dict(row.parameters_json or {})
            parameters.setdefault("classification", "ORDINARY_OT")
            parameters.setdefault("minimum_multiplier", 1.5)
            row.parameters_json = parameters
        db.add(row)


def install_validation_policy(validation_module: Any) -> None:
    """Install the strengthened duty/rest policy behind the existing API."""

    original_seed = validation_module.seed_default_rules
    original_build = validation_module.build_findings

    def seed_default_rules(
        db: Session,
        *,
        amo_id: str,
        actor_user_id: Optional[str] = None,
    ) -> None:
        original_seed(db, amo_id=amo_id, actor_user_id=actor_user_id)
        _harden_seeded_rules(db, amo_id=amo_id)

    def build_findings(
        db: Session,
        *,
        version: models.RosterVersion,
        rules: Sequence[models.RosterRule],
    ) -> list[Any]:
        findings = list(original_build(db, version=version, rules=rules))
        assignments = [
            row for row in version.assignments or [] if row.deleted_at is None
        ]
        findings.extend(
            _protected_rest_findings(
                db,
                version=version,
                assignments=assignments,
                rules=rules,
                validation_module=validation_module,
            )
        )
        findings.sort(
            key=lambda item: (
                item.sort_order,
                validation_module._enum_value(item.severity),
                item.code,
                item.user_id or "",
                item.assignment_id or "",
                item.message,
            )
        )
        return findings

    validation_module.seed_default_rules = seed_default_rules
    validation_module._is_productive = assignment_counts_as_duty
    validation_module.build_findings = build_findings
