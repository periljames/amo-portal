from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from amodb.apps.rostering import compliance_policy, models
from amodb.apps.workforce import pay_policy

UTC = timezone.utc


def template(code: str, *, kind=models.ShiftTemplateKind.DAY, counts_as_duty: bool = True):
    return SimpleNamespace(id=f"shift-{code}", code=code, kind=kind, counts_as_duty=counts_as_duty)


def assignment(
    day: int,
    shift,
    *,
    start_hour: int = 8,
    start_minute: int = 0,
    duration: timedelta = timedelta(hours=8),
    status=models.RosterAssignmentStatus.DUTY,
    user_id="u1",
):
    start = datetime(2026, 8, day, start_hour, start_minute, tzinfo=UTC)
    return SimpleNamespace(
        id=f"{user_id}-{shift.code}-{day}-{start_hour:02d}{start_minute:02d}",
        user_id=user_id,
        starts_at=start,
        ends_at=start + duration,
        planned_minutes=int(duration.total_seconds() // 60),
        status=status,
        shift_template=shift,
        deleted_at=None,
    )


def version(assignments):
    return SimpleNamespace(
        assignments=assignments,
        period=SimpleNamespace(starts_on=date(2026, 8, 1), ends_on=date(2026, 8, 31), timezone_name="UTC"),
    )


def duty_interval(start: datetime, end: datetime, assignment_id: str = "a1"):
    return compliance_policy.DutyInterval(starts_at=start, ends_at=end, assignment_ids=(assignment_id,))


def one_window(intervals):
    start = datetime(2026, 8, 1, tzinfo=UTC)
    return compliance_policy.protected_rest_violation(
        intervals,
        evaluation_start=start,
        evaluation_end=start,
        window=timedelta(days=7),
        required_rest=timedelta(hours=24),
    )


def test_exact_24_hour_release_passes():
    intervals = [
        duty_interval(datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 8, 3, tzinfo=UTC), "before"),
        duty_interval(datetime(2026, 8, 4, tzinfo=UTC), datetime(2026, 8, 8, tzinfo=UTC), "after"),
    ]
    assert one_window(intervals) is None


def test_23h59_release_fails():
    intervals = [
        duty_interval(datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 8, 3, 0, 1, tzinfo=UTC), "before"),
        duty_interval(datetime(2026, 8, 4, tzinfo=UTC), datetime(2026, 8, 8, tzinfo=UTC), "after"),
    ]
    violation = one_window(intervals)
    assert violation is not None
    assert violation["longest_rest_minutes"] == 23 * 60 + 59
    assert violation["required_rest_minutes"] == 24 * 60


def test_more_than_24_hour_release_passes():
    intervals = [
        duty_interval(datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 8, 3, tzinfo=UTC), "before"),
        duty_interval(datetime(2026, 8, 4, 0, 1, tzinfo=UTC), datetime(2026, 8, 8, tzinfo=UTC), "after"),
    ]
    assert one_window(intervals) is None


def test_overlapping_and_adjacent_duty_intervals_are_merged():
    merged = compliance_policy._merge_intervals([
        duty_interval(datetime(2026, 8, 1, 20, tzinfo=UTC), datetime(2026, 8, 2, 4, tzinfo=UTC), "night"),
        duty_interval(datetime(2026, 8, 2, 3, tzinfo=UTC), datetime(2026, 8, 2, 8, tzinfo=UTC), "callout"),
        duty_interval(datetime(2026, 8, 2, 8, tzinfo=UTC), datetime(2026, 8, 2, 9, tzinfo=UTC), "handover"),
    ])
    assert len(merged) == 1
    assert merged[0].starts_at == datetime(2026, 8, 1, 20, tzinfo=UTC)
    assert merged[0].ends_at == datetime(2026, 8, 2, 9, tzinfo=UTC)
    assert set(merged[0].assignment_ids) == {"night", "callout", "handover"}


def test_shift_crossing_midnight_uses_actual_timestamps():
    night = template("TENANT_NIGHT", kind=models.ShiftTemplateKind.NIGHT)
    row = assignment(1, night, start_hour=20, duration=timedelta(hours=12))
    interval = compliance_policy._effective_interval(row)
    assert interval is not None
    assert interval.starts_at == datetime(2026, 8, 1, 20, tzinfo=UTC)
    assert interval.ends_at == datetime(2026, 8, 2, 8, tzinfo=UTC)


def test_complete_attendance_pair_replaces_planned_interval():
    duty = template("CUSTOM")
    row = assignment(1, duty, start_hour=8, duration=timedelta(hours=8))
    actual = {
        row.id: (
            datetime(2026, 8, 1, 7, 45, tzinfo=UTC),
            datetime(2026, 8, 1, 17, 20, tzinfo=UTC),
        )
    }
    interval = compliance_policy._effective_interval(row, actual_by_assignment=actual)
    assert interval is not None
    assert interval.source == "ACTUAL"
    assert interval.starts_at == actual[row.id][0]
    assert interval.ends_at == actual[row.id][1]


def test_tenant_defined_working_codes_and_standby_count_as_duty():
    for code in ("D", "SA", "XH", "X", "ANY_TENANT_CODE"):
        row = assignment(3, template(code, counts_as_duty=True), status=models.RosterAssignmentStatus.OFF)
        assert compliance_policy.assignment_counts_as_duty(row) is True

    rd = assignment(3, template("RD", kind=models.ShiftTemplateKind.OFF, counts_as_duty=False), status=models.RosterAssignmentStatus.OFF)
    assert compliance_policy.assignment_counts_as_duty(rd) is False
    assert compliance_policy.assignment_is_protected_rest(rd) is True


def test_nominal_rest_code_does_not_prove_24_hour_release():
    duty = template("WORK")
    rd = template("RD", kind=models.ShiftTemplateKind.OFF, counts_as_duty=False)
    rows = [assignment(day, duty, start_hour=8, duration=timedelta(hours=9)) for day in range(1, 8)]
    rows.append(assignment(4, rd, start_hour=0, duration=timedelta(days=1), status=models.RosterAssignmentStatus.OFF))
    findings = compliance_policy._protected_rest_specs(version(rows), rows, [])
    assert findings
    assert findings[0].code == compliance_policy.PROTECTED_REST_FINDING
    assert findings[0].overridable is False


def test_thomas_wambunya_regression_is_hard_block_even_with_following_rest_codes():
    x = template("X", kind=models.ShiftTemplateKind.STANDBY, counts_as_duty=True)
    ha = template("HA", counts_as_duty=True)
    rr = template("RR", kind=models.ShiftTemplateKind.OFF, counts_as_duty=False)
    rd = template("RD", kind=models.ShiftTemplateKind.OFF, counts_as_duty=False)

    rows = [
        assignment(1, x, start_hour=6, duration=timedelta(hours=12), status=models.RosterAssignmentStatus.STANDBY),
        assignment(2, x, start_hour=6, duration=timedelta(hours=12), status=models.RosterAssignmentStatus.STANDBY),
    ]
    rows.extend(assignment(day, ha, start_hour=8, duration=timedelta(hours=9)) for day in range(3, 8))
    rows.extend([
        assignment(8, rr, start_hour=0, duration=timedelta(days=1), status=models.RosterAssignmentStatus.OFF),
        assignment(9, rd, start_hour=0, duration=timedelta(days=1), status=models.RosterAssignmentStatus.OFF),
    ])

    findings = compliance_policy._protected_rest_specs(version(rows), rows, [])
    assert findings
    finding = findings[0]
    assert finding.severity == models.RosterValidationSeverity.BLOCKER
    assert finding.overridable is False
    assert finding.code == "ROSTER_PROTECTED_REST_VIOLATION"
    assert finding.details["longest_rest_minutes"] < 24 * 60
    assert finding.details["managerial_override_allowed"] is False
    assert finding.details["personnel_acknowledgement_can_cure"] is False


def test_consecutive_duty_rule_is_warning_heuristic_not_authoritative_statutory_test():
    row = SimpleNamespace(
        code=compliance_policy.CONSECUTIVE_DUTY_RULE,
        parameters_json={"maximum_days": 6},
        severity=models.RosterValidationSeverity.BLOCKER,
        allow_override=True,
    )
    compliance_policy._govern_rule(row)
    assert row.severity == models.RosterValidationSeverity.WARNING
    assert row.allow_override is False
    assert compliance_policy.statutory_rule_is_non_overridable(row.code) is False


def test_statutory_14_day_ceiling_and_protected_rest_are_non_overridable():
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
    assert compliance_policy.statutory_rule_is_non_overridable(compliance_policy.PROTECTED_REST_FINDING) is True


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
    assert pay_policy.enforce_multiplier(pay_policy.DutyPayClassification.ORDINARY_OT, requested_multiplier="1.75") == Decimal("1.75")
    assert pay_policy.enforce_multiplier(pay_policy.DutyPayClassification.REST_DAY_WORK, requested_multiplier=None) == Decimal("2.00")
    assert pay_policy.minimum_multiplier(pay_policy.DutyPayClassification.PUBLIC_HOLIDAY_WORK, contractual_minimum="2.50") == Decimal("2.50")

    with pytest.raises(ValueError, match="cannot be paid below"):
        pay_policy.enforce_multiplier(pay_policy.DutyPayClassification.PUBLIC_HOLIDAY_WORK, requested_multiplier="1.50")


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
