from __future__ import annotations

from datetime import date
from decimal import Decimal

from amodb.apps.reliability.formal_reporting_history import (
    SOURCE_DOMAINS,
    _monthly_series,
    _window_summary,
    history_start,
    rate_per_100,
    shift_months,
)


def test_history_start_keeps_exact_calendar_month_count():
    assert history_start(date(2026, 12, 31), 12) == date(2026, 1, 1)
    assert history_start(date(2026, 6, 30), 24) == date(2024, 7, 1)
    assert history_start(date(2026, 1, 31), 36) == date(2023, 2, 1)
    assert shift_months(date(2026, 1, 1), -1) == date(2025, 12, 1)


def test_rate_withholds_zero_or_missing_flight_hours():
    assert rate_per_100(3, None) is None
    assert rate_per_100(3, Decimal("0")) is None
    assert rate_per_100(3, Decimal("12.5")) == Decimal("24")


def test_monthly_history_uses_exact_decimal_strings_and_all_domains():
    series = _monthly_series(
        date(2026, 1, 1),
        date(2026, 2, 28),
        utilisation=[
            {
                "month": date(2026, 1, 1),
                "flight_hours": Decimal("10.25"),
                "flight_cycles": Decimal("7"),
                "fh_observations": 2,
                "fc_observations": 2,
                "source_rows": 2,
            }
        ],
        events=[{"month": date(2026, 1, 1), "event_count": 2}],
        domains=[
            {"month": date(2026, 1, 1), "dataset_code": "AU", "record_count": 2},
            {"month": date(2026, 1, 1), "dataset_code": "FI", "record_count": 1},
        ],
    )
    assert series[0]["exact_flight_hours"] == "10.25"
    assert series[0]["exact_flight_cycles"] == "7"
    assert series[0]["exact_event_rate_per_100_fh"] == "19.51219512195121951219512195121951"
    assert set(series[0]["source_domain_counts"]) == set(SOURCE_DOMAINS)
    assert series[1]["exact_flight_hours"] is None
    assert series[1]["exact_event_rate_per_100_fh"] is None
    assert series[1]["event_rate_quality"] == "WITHHELD_NO_FLIGHT_HOURS"


def test_window_summary_does_not_turn_missing_exposure_into_zero_rate():
    series = [
        {
            "month": "2026-01-01",
            "exact_flight_hours": None,
            "exact_flight_cycles": None,
            "canonical_event_count": 4,
        },
        {
            "month": "2026-02-01",
            "exact_flight_hours": None,
            "exact_flight_cycles": None,
            "canonical_event_count": 1,
        },
    ]
    summary = _window_summary(series, 2)
    assert summary["canonical_event_count"] == 5
    assert summary["exact_flight_hours"] is None
    assert summary["exact_event_rate_per_100_fh"] is None
    assert summary["event_rate_quality"] == "WITHHELD_NO_FLIGHT_HOURS"
