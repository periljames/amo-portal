from amodb.apps.work.readiness_services import _projected_days


def test_calendar_is_earliest_trigger():
    days, trigger = _projected_days(
        remaining_days=10,
        remaining_hours=100,
        remaining_cycles=60,
        daily_hours=5,
        daily_cycles=3,
    )
    assert days == 10
    assert trigger == "CALENDAR"


def test_hours_projection_uses_daily_rate():
    days, trigger = _projected_days(
        remaining_days=90,
        remaining_hours=20,
        remaining_cycles=100,
        daily_hours=5,
        daily_cycles=2,
    )
    assert days == 4
    assert trigger == "HOURS"


def test_zero_rate_does_not_divide():
    days, trigger = _projected_days(
        remaining_days=None,
        remaining_hours=20,
        remaining_cycles=8,
        daily_hours=0,
        daily_cycles=2,
    )
    assert days == 4
    assert trigger == "CYCLES"


def test_missing_limits_returns_no_projection():
    days, trigger = _projected_days(
        remaining_days=None,
        remaining_hours=None,
        remaining_cycles=None,
        daily_hours=5,
        daily_cycles=3,
    )
    assert days is None
    assert trigger is None
