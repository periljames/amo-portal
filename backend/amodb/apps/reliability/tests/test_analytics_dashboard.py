from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import APIRouter

from amodb.apps.reliability import analytics_common
from amodb.apps.reliability import analytics_dashboard
from amodb.apps.reliability import analytics_deferrals
from amodb.apps.reliability import analytics_event_charts


UTC = timezone.utc


def event(**overrides):
    values = {
        "id": 1,
        "event_type": "TECHNICAL_DELAY",
        "occurred_at": datetime(2026, 7, 1, 10, tzinfo=UTC),
        "aircraft_serial_number": "AC-001",
        "ata_chapter": "21",
        "origin_station": "NBO",
        "destination_station": "MBA",
        "delay_minutes": 30,
        "confirmed_failure": None,
        "part_number": None,
        "component_serial_number": None,
        "severity": "MEDIUM",
        "reference_code": "REL-1",
        "source_record_id": "SRC-1",
        "source_system": "FLIGHT-OPERATIONS",
        "validation_status": "VALID",
        "description": "Technical delay",
        "flight_number": "F100",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def utilisation(**overrides):
    values = {
        "date": date(2026, 7, 1),
        "aircraft_serial_number": "AC-001",
        "flight_hours": 10,
        "cycles": 5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def deferral(**overrides):
    applied = datetime(2026, 7, 1, tzinfo=UTC)
    values = {
        "id": "DEF-1",
        "status": "OPEN",
        "expires_at": datetime.now(UTC) + timedelta(days=5),
        "applied_at": applied,
        "closed_at": None,
        "category": "B",
        "aircraft_serial_number": "AC-001",
        "item_reference": "21-10-01",
        "ata_chapter": "21",
        "extension_history_json": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_bucket_selection_uses_window_size():
    assert analytics_common._bucket_for_window(date(2026, 7, 1), date(2026, 7, 30), "AUTO") == "DAY"
    assert analytics_common._bucket_for_window(date(2026, 1, 1), date(2026, 4, 30), "AUTO") == "WEEK"
    assert analytics_common._bucket_for_window(date(2025, 1, 1), date(2026, 1, 1), "AUTO") == "MONTH"
    assert analytics_common._bucket_for_window(date(2026, 1, 1), date(2026, 1, 2), "MONTH") == "MONTH"


def test_ratio_withholds_value_without_exposure():
    assert analytics_common._ratio(4, 0, 100) is None
    assert analytics_common._ratio(4, 20, 100) == 20


def test_event_totals_preserve_operational_consequences():
    totals = analytics_common._event_totals([
        event(),
        event(id=2, event_type="TECHNICAL_CANCELLATION", delay_minutes=None),
        event(id=3, event_type="REPEAT_DEFECT", delay_minutes=None),
        event(id=4, event_type="NO_FAULT_FOUND", delay_minutes=None),
    ])
    assert totals["events"] == 4
    assert totals["dispatch_events"] == 2
    assert totals["delays"] == 1
    assert totals["cancellations"] == 1
    assert totals["repeat_defects"] == 1
    assert totals["nff"] == 1
    assert totals["delay_minutes"] == 30


def test_time_series_calculates_rates_from_matching_exposure():
    points = analytics_event_charts._time_series([event()], [utilisation()], "DAY")
    assert len(points) == 1
    point = points[0]
    assert point.metrics["events"] == 1
    assert point.metrics["delay_minutes"] == 30
    assert point.metrics["event_rate_per_100_fh"] == 10
    assert point.metrics["dispatch_reliability_pct"] == 80
    assert point.drilldown["dimension"] == "period"


def test_open_deferral_is_counted_and_expiry_is_bucketed():
    status, expiry, categories, extensions, repeats, closure = analytics_deferrals._deferral_charts(
        [deferral()], datetime.now(UTC)
    )
    assert {point.key: point.metrics["count"] for point in status}["OPEN"] == 1
    assert {point.key: point.metrics["count"] for point in expiry}["0_7_DAYS"] == 1
    assert categories[0].key == "B"
    assert extensions == []
    assert repeats == []
    assert closure == []


def test_register_adds_dashboard_engine_and_drilldown_routes():
    router = APIRouter(prefix="/reliability")
    analytics_dashboard.register(router)
    paths = {route.path for route in router.routes}
    assert "/reliability/analytics-dashboard" in paths
    assert "/reliability/analytics-dashboard/engine-series" in paths
    assert "/reliability/analytics-dashboard/drilldown" in paths
