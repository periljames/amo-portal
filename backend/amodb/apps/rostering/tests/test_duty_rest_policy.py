from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from amodb.apps.rostering import compliance_policy, models
from amodb.apps.workforce import pay_policy

UTC = timezone.utc


def template(code: str, *, kind=models.ShiftTemplateKind.DAY, counts_as_duty: bool = True):
    return SimpleNamespace(code=code, kind=kind, counts_as_duty=counts_as_duty)


def assignment(day: int, shift, *, status=models.RosterAssignmentStatus.OFF, user_id="u1"):
    start = datetime(2026, 8, day, 8, tzinfo=UTC)
    return SimpleNamespace(
        id=f"{user_id}-{shift.code}-{day}",
        user_id=user_id,
        starts_at=start,
        ends_at=start + timedelta(hours=8),
        planned_minutes=480,
        status=status,
        shift_template=shift,
        deleted_at=None,
    )


def version(assignments):
    return SimpleNamespace(
        assignments=assignments,
        period=SimpleNamespace(starts_on=date(2026, 8, 1), ends_on=date(2026, 8, 31), timezone_name="UTC"),
    )


def test_all_configured_working_codes_count_as_duty_without_code_checks():
    for code in ("D", "SA", "XH", "X"):
        row = assignment(3, template(code, counts_as_duty=True), status=models.RosterAssignmentStatus.OFF)
        assert compliance_policy.assignment_counts_as_duty(row) is True

    rd = assignment(3, template("RD", kind=models.ShiftTemplateKind.OFF, counts_as_duty=False))
    assert compliance_policy.assignment_counts_as_duty(rd) is False
    assert compliance_policy.assignment_is_protected_rest(rd) is True


def test_seven_day_duty_sequence_requires_explicit_protected_rest():
    duty = template("D")
    rows = [assignment(day, duty, status=models.RosterAssignmentStatus.DUTY) for day in range(1, 8)]
    findings = compliance_policy._protected_rest_specs(version(rows), rows, [])
    assert findings
    assert findings[0].code == compliance_policy.PROTECTED_REST_FINDING
    assert findings[0].severity == models.RosterValidationSeverity.BLOCKER
    assert findings[0].overridable is False


def test_compensating_rd_satisfies_protected_rest_window():
    duty = template("D")
    rd = template("RD", kind=models.ShiftTemplateKind.OFF, counts_as_duty=False)
    rows = [assignment(day, duty, status=models.RosterAssignmentStatus.DUTY) for day in (1, 2, 3, 5, 6, 7)]
    rows.append(assignment(4, rd, status=models.RosterAssignmentStatus.OFF))
    findings = compliance_policy._protected_rest_specs(version(rows), rows, [])
    assert findings == []


def test_worked_rd_is_consumed_and_requires_replacement_rest():
    duty = template("X", kind=models.ShiftTemplateKind.STANDBY, counts_as_duty=True)
    rd = template("RD", kind=models.ShiftTemplateKind.OFF, counts_as_duty=False)
    rows = [assignment(day, duty, status=models.RosterAssignmentStatus.STANDBY) for day in (1, 2, 3, 4, 5, 6, 7)]
    rows.append(assignment(7, rd, status=models.RosterAssignmentStatus.OFF))
    findings = compliance_policy._protected_rest_specs(version(rows), rows, [])
    assert findings
    assert findings[0].details["worked_rest_dates"] == ["2026-08-07"]
    assert findings[0].details["required_replacement_rest"] is True


def test_statutory_14_day_ceiling_and_weekly_rest_are_non_overridable():
    total = SimpleNamespace(
        code=compliance_policy.STATUTORY_TOTAL_HOURS_RULE,
        parameters_json={"window_days": 14, "maximum_minutes": 9999},
        severity=models.RosterValidationSeverity.WARNING,
        allow_override=True,
    )
    rest = SimpleNamespace(
        code=compliance_policy.PROTECTED_REST_RULE,
        parameters_json={"window_days": 7, "minimum_continuous_minutes": 60},
        severity=models.RosterValidationSeverity.WARNING,
        allow_override=True,
    )
    compliance_policy._govern_rule(total)
    compliance_policy._govern_rule(rest)

    assert total.parameters_json["maximum_minutes"] == 116 * 60
    assert total.severity == models.RosterValidationSeverity.BLOCKER
    assert total.allow_override is False
    assert rest.parameters_json["minimum_continuous_minutes"] == 24 * 60
    assert rest.severity == models.RosterValidationSeverity.BLOCKER
    assert rest.allow_override is False


def test_52_hour_threshold_remains_overtime_classification_not_illegality():
    row = SimpleNamespace(
        code=compliance_policy.NORMAL_HOURS_CLASSIFICATION_RULE,
        parameters_json={"window_days": 7, "maximum_minutes": 9999},
        severity=models.RosterValidationSeverity.BLOCKER,
        allow_override=True,
    )
    compliance_policy._govern_rule(row)
    assert row.parameters_json["maximum_minutes"] == 52 * 60
    assert row.severity == models.RosterValidationSeverity.WARNING

    classification = pay_policy.classify_work(
        is_public_holiday=False,
        is_protected_rest_day=False,
        ordinary_minutes_before=51 * 60,
        worked_minutes=2 * 60,
        contractual_normal_weekly_minutes=52 * 60,
    )
    assert classification == pay_policy.DutyPayClassification.ORDINARY_OT


def test_pay_reason_enforces_legal_floor_and_cannot_be_manually_reduced():
    assert pay_policy.enforce_multiplier(
        pay_policy.DutyPayClassification.ORDINARY_OT,
        requested_multiplier="1.75",
    ) == Decimal("1.75")
    assert pay_policy.enforce_multiplier(
        pay_policy.DutyPayClassification.REST_DAY_WORK,
        requested_multiplier=None,
    ) == Decimal("2.00")
    assert pay_policy.minimum_multiplier(
        pay_policy.DutyPayClassification.PUBLIC_HOLIDAY_WORK,
        contractual_minimum="2.50",
    ) == Decimal("2.50")

    with pytest.raises(ValueError, match="cannot be paid below"):
        pay_policy.enforce_multiplier(
            pay_policy.DutyPayClassification.PUBLIC_HOLIDAY_WORK,
            requested_multiplier="1.50",
        )


def test_sunday_is_not_a_pay_code_reason_controls_classification():
    normal = pay_policy.classify_work(
        is_public_holiday=False,
        is_protected_rest_day=False,
        ordinary_minutes_before=20 * 60,
        worked_minutes=8 * 60,
        contractual_normal_weekly_minutes=40 * 60,
    )
    rest_day = pay_policy.classify_work(
        is_public_holiday=False,
        is_protected_rest_day=True,
        ordinary_minutes_before=20 * 60,
        worked_minutes=8 * 60,
        contractual_normal_weekly_minutes=40 * 60,
    )
    public_holiday = pay_policy.classify_work(
        is_public_holiday=True,
        is_protected_rest_day=False,
        ordinary_minutes_before=20 * 60,
        worked_minutes=8 * 60,
        contractual_normal_weekly_minutes=40 * 60,
    )
    assert normal == pay_policy.DutyPayClassification.NORMAL_DUTY
    assert rest_day == pay_policy.DutyPayClassification.REST_DAY_WORK
    assert public_holiday == pay_policy.DutyPayClassification.PUBLIC_HOLIDAY_WORK
