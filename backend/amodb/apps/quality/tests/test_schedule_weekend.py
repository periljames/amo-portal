from datetime import date

import pytest
from fastapi import HTTPException

from amodb.apps.quality.schedule_weekend import (
    add_business_days,
    resolve_schedule_window,
    weekend_dates_in_range,
)

# Fixed "today" so weekend fixtures stay stable regardless of wall-clock date.
_AS_OF = date(2026, 8, 20)


def test_weekend_dates_in_fri_mon_span() -> None:
    hits = weekend_dates_in_range(date(2026, 8, 21), date(2026, 8, 24))
    assert hits == [date(2026, 8, 22), date(2026, 8, 23)]


def test_resolve_without_weekend_passthrough() -> None:
    start, end, duration = resolve_schedule_window(
        start=date(2026, 8, 25),
        duration_days=3,
        weekend_policy=None,
        title="Weekday audit",
        as_of=_AS_OF,
    )
    assert start == date(2026, 8, 25)
    assert end == date(2026, 8, 27)
    assert duration == 3


def test_resolve_rejects_start_before_today() -> None:
    with pytest.raises(HTTPException) as raised:
        resolve_schedule_window(
            start=date(2026, 8, 14),
            duration_days=3,
            weekend_policy="SKIP_WEEKEND",
            title="Past start",
            as_of=date(2026, 8, 25),
        )
    assert raised.value.status_code == 422
    detail = raised.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "SCHEDULE_START_IN_PAST"
    assert detail["start_date"] == "2026-08-14"
    assert detail["today"] == "2026-08-25"


def test_resolve_allows_today() -> None:
    start, end, duration = resolve_schedule_window(
        start=date(2026, 8, 25),
        duration_days=1,
        weekend_policy=None,
        title="Same-day audit",
        as_of=date(2026, 8, 25),
    )
    assert (start, end, duration) == (date(2026, 8, 25), date(2026, 8, 25), 1)


def test_resolve_requires_confirmation_when_weekend_present() -> None:
    with pytest.raises(HTTPException) as raised:
        resolve_schedule_window(
            start=date(2026, 8, 21),
            duration_days=4,
            weekend_policy=None,
            title="Base test audit",
            as_of=_AS_OF,
        )
    assert raised.value.status_code == 422
    detail = raised.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "WEEKEND_CONFIRMATION_REQUIRED"
    assert detail["options"]["SKIP_WEEKEND"]["start_date"] == "2026-08-21"
    assert detail["options"]["SKIP_WEEKEND"]["end_date"] == "2026-08-26"


def test_include_weekend_keeps_calendar_span() -> None:
    start, end, duration = resolve_schedule_window(
        start=date(2026, 8, 21),
        duration_days=4,
        weekend_policy="INCLUDE_WEEKEND",
        title="Base test audit",
        as_of=_AS_OF,
    )
    assert (start, end, duration) == (date(2026, 8, 21), date(2026, 8, 24), 4)


def test_skip_weekend_uses_working_days_only() -> None:
    start, end, duration = resolve_schedule_window(
        start=date(2026, 8, 21),
        duration_days=4,
        weekend_policy="SKIP_WEEKEND",
        title="Base test audit",
        as_of=_AS_OF,
    )
    # Fri + Mon + Tue + Wed = working duration 4; calendar Fri..Wed
    assert start == date(2026, 8, 21)
    assert end == date(2026, 8, 26)
    assert duration == 6
    assert add_business_days(date(2026, 8, 21), 3) == date(2026, 8, 26)


def test_skip_weekend_bumps_saturday_start_to_monday() -> None:
    start, end, duration = resolve_schedule_window(
        start=date(2026, 8, 22),
        duration_days=2,
        weekend_policy="SKIP_WEEKEND",
        title="Weekend start",
        as_of=_AS_OF,
    )
    assert start == date(2026, 8, 24)
    assert end == date(2026, 8, 25)
    assert duration == 2
