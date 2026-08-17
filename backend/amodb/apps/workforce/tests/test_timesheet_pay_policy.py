from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from amodb.apps.workforce import models, pay_policy, timesheet_pay_policy


def test_normal_hours_crossing_splits_only_excess_into_ordinary_ot():
    segments = timesheet_pay_policy.split_pay_segments(
        minutes=180,
        base_category=models.TimesheetCategory.ORDINARY,
        is_public_holiday=False,
        is_protected_rest_day=False,
        ordinary_minutes_before=39 * 60,
        normal_weekly_limit=40 * 60,
    )

    assert [(row.minutes, row.category, row.classification) for row in segments] == [
        (60, models.TimesheetCategory.ORDINARY, pay_policy.DutyPayClassification.NORMAL_DUTY),
        (120, models.TimesheetCategory.OVERTIME, pay_policy.DutyPayClassification.ORDINARY_OT),
    ]
    assert segments[0].minimum_multiplier == Decimal("1.00")
    assert segments[1].minimum_multiplier == Decimal("1.50")


def test_sunday_has_no_intrinsic_pay_category():
    segments = timesheet_pay_policy.split_pay_segments(
        minutes=480,
        base_category=models.TimesheetCategory.ORDINARY,
        is_public_holiday=False,
        is_protected_rest_day=False,
        ordinary_minutes_before=0,
        normal_weekly_limit=52 * 60,
    )

    assert len(segments) == 1
    assert segments[0].category == models.TimesheetCategory.ORDINARY
    assert segments[0].classification == pay_policy.DutyPayClassification.NORMAL_DUTY


def test_protected_rest_work_uses_rest_day_reason_and_double_floor():
    segments = timesheet_pay_policy.split_pay_segments(
        minutes=300,
        base_category=models.TimesheetCategory.STANDBY,
        is_public_holiday=False,
        is_protected_rest_day=True,
        ordinary_minutes_before=40 * 60,
        normal_weekly_limit=40 * 60,
    )

    assert len(segments) == 1
    assert segments[0].category == models.TimesheetCategory.WEEKEND
    assert segments[0].classification == pay_policy.DutyPayClassification.REST_DAY_WORK
    assert segments[0].minimum_multiplier == Decimal("2.00")


def test_public_holiday_reason_takes_precedence_over_rest_day():
    segments = timesheet_pay_policy.split_pay_segments(
        minutes=420,
        base_category=models.TimesheetCategory.ORDINARY,
        is_public_holiday=True,
        is_protected_rest_day=True,
        ordinary_minutes_before=50 * 60,
        normal_weekly_limit=40 * 60,
    )

    assert len(segments) == 1
    assert segments[0].category == models.TimesheetCategory.PUBLIC_HOLIDAY
    assert segments[0].classification == pay_policy.DutyPayClassification.PUBLIC_HOLIDAY_WORK
    assert segments[0].minimum_multiplier == Decimal("2.00")


def test_contractual_floor_is_server_resolved_and_can_only_raise_entitlement():
    contract = SimpleNamespace(ordinary_ot_multiplier=Decimal("1.75"), metadata_json=None)
    floor = timesheet_pay_policy._contractual_floor(
        contract,
        pay_policy.DutyPayClassification.ORDINARY_OT,
    )

    assert floor == Decimal("1.75")
    assert pay_policy.minimum_multiplier(
        pay_policy.DutyPayClassification.ORDINARY_OT,
        contractual_minimum=floor,
    ) == Decimal("1.75")
