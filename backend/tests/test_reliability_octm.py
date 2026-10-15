"""Focused source-to-interval OCTM regression tests."""
from datetime import date, datetime, timezone
from types import SimpleNamespace as Row

import pytest

from amodb.apps.reliability.octm import EntryPayload, calculate_windows


def observation(seq, *, engine="PT6-123", install="INSTALL-001", qty=1,
                fh=10, day=1, event="TOP_UP", level="FULL"):
    return Row(
        id=str(seq), review_status="VERIFIED", engine_serial_number=engine,
        installation_ref=install, aircraft_serial_number="AC-001",
        engine_position="1", event_date=date(2026, 10, day),
        event_sequence=seq, created_at=datetime(2026, 10, day, tzinfo=timezone.utc),
        event_type=event, oil_quantity=qty, oil_unit="QT",
        reference_method="DIPSTICK", reference_level=level, flight_hours=fh,
    )


def test_consumption_uses_matched_oil_and_flight_hours():
    result = calculate_windows([observation(i, day=i, qty=1, fh=10) for i in range(1, 5)], [])
    assert len(result) == 1
    assert result[0]["oil_added_quarts"] == 4
    assert result[0]["flight_hours"] == 40
    assert result[0]["rate_qt_per_fh"] == 0.1
    assert result[0]["manufacturer_limit_qt_per_fh"] is None
    assert result[0]["manufacturer_limit_exceeded"] is None


def test_physical_engine_and_installation_are_independent():
    rows = [observation(i, day=i) for i in range(1, 5)]
    rows += [observation(i + 4, engine="PT6-456", install="INSTALL-002", day=i) for i in range(1, 5)]
    results = calculate_windows(rows, [])
    assert len(results) == 2
    assert {r["engine_serial_number"] for r in results} == {"PT6-123", "PT6-456"}


def test_missing_oil_information_breaks_interval():
    rows = [observation(1), observation(2, day=2),
            observation(3, day=3, event="MISSING", qty=None, fh=None),
            observation(4, day=4), observation(5, day=5)]
    assert calculate_windows(rows, []) == []


def test_reference_change_resets_continuity():
    rows = [observation(1), observation(2, day=2),
            observation(3, day=3, level="LOW"), observation(4, day=4, level="LOW")]
    assert calculate_windows(rows, []) == []


def test_excessive_window_withholds_rate():
    rows = [observation(1, fh=28), observation(2, day=2, fh=25)]
    result = calculate_windows(rows, [])
    assert len(result) == 1
    assert result[0]["status"] == "OUT_OF_RANGE"
    assert result[0]["rate_qt_per_fh"] is None


def test_oil_checked_zero_distinct_from_missing():
    zero = EntryPayload(
        aircraft_serial_number="AC-001", engine_position="1",
        engine_serial_number="E-1", installation_ref="INSTALL-001",
        event_date=date(2026, 10, 1), event_sequence=1,
        techsheet_ref="TS-001", event_type="CHECK_ZERO", oil_quantity=0,
        oil_unit="QT",
    )
    assert zero.event_type == "CHECK_ZERO"
    with pytest.raises(ValueError):
        EntryPayload(
            aircraft_serial_number="AC-001", engine_position="1",
            engine_serial_number="E-1", installation_ref="INSTALL-001",
            event_date=date(2026, 10, 1), event_sequence=1,
            techsheet_ref="TS-001", event_type="MISSING", oil_quantity=0,
            oil_unit="QT",
        )


def test_unverified_rows_cannot_change_formal_monitoring():
    data = [observation(i, day=i) for i in range(1, 5)]
    data[0].review_status = "DRAFT"
    assert calculate_windows(data, []) == []
