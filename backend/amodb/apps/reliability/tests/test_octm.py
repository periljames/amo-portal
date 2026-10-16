"""Focused source-to-interval OCTM regression tests."""
from datetime import date, datetime, timezone
from types import SimpleNamespace as Row

import pytest

from amodb.apps.reliability.octm import EntryPayload, EntryReview, ProfileApproval, calculate_windows, summarize_daily_coverage


def observation(seq, *, engine="PT6-123", install="INSTALL-001", qty=1,
                fh=10, day=1, event="TOP_UP", level="FULL"):
    return Row(
        id=str(seq), review_status="VERIFIED", engine_serial_number=engine,
        installation_ref=install, aircraft_serial_number="AC-001",
        engine_position="1", event_date=date(2026, 10, day),
        event_sequence=seq, created_at=datetime(2026, 10, day, tzinfo=timezone.utc),
        sector_ref=f"FLIGHT-{day}", event_type=event, oil_quantity=qty, oil_unit="QT",
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


def test_multiple_topups_same_sector_do_not_double_count_hours():
    rows = [
        observation(1, day=1, qty=1, fh=10),
        observation(2, day=1, qty=2, fh=10),
        observation(3, day=2, qty=1, fh=10),
        observation(4, day=3, qty=1, fh=10),
        observation(5, day=4, qty=1, fh=10),
    ]
    for row in rows:
        row.sector_ref = f"FLIGHT-{row.event_date.day}"
    result = calculate_windows(rows, [])
    assert len(result) == 1
    assert result[0]["flight_hours"] == 40
    assert result[0]["oil_added_quarts"] == 6
    assert result[0]["rate_qt_per_fh"] == 0.15
    assert len(result[0]["source_ids"]) == 5


def test_no_operation_day_does_not_break_continuous_interval():
    rows = [observation(i, day=i) for i in range(1, 5)]
    rows.append(observation(5, day=5, event="NO_OPERATION", fh=0, qty=None))
    result = calculate_windows(rows, [])
    assert len(result) == 1
    assert result[0]["flight_hours"] == 40


def test_nonroutine_oil_change_breaks_continuity():
    rows = [
        observation(1), observation(2, day=2),
        observation(3, day=3, event="OIL_CHANGE", qty=None, fh=0),
        observation(4, day=4), observation(5, day=5),
    ]
    assert calculate_windows(rows, []) == []


def test_draft_may_be_incomplete_but_no_false_zero_or_future_date():
    # Saving an unfinished draft is allowed, but the reviewer must fill the
    # quantity before verifying; an empty oil field is not a zero reading.
    entry = EntryPayload(
        aircraft_serial_number="AC-001", engine_position="1",
        engine_serial_number="E-1", installation_ref="INSTALL-001",
        event_date=date(2026, 10, 1), event_sequence=1,
        techsheet_ref="TS-002", event_type="TOP_UP",
    )
    assert entry.oil_quantity is None
    with pytest.raises(ValueError):
        EntryPayload(
            aircraft_serial_number="AC-001", engine_position="1",
            engine_serial_number="E-1", installation_ref="INSTALL-001",
            event_date=date(2026, 10, 1), event_sequence=1,
            techsheet_ref="TS-002", event_type="TOP_UP", oil_quantity=0,
        )


def test_invalid_flight_exposure_rejected_without_sector():
    with pytest.raises(ValueError):
        EntryPayload(
            aircraft_serial_number="AC-001", engine_position="1",
            engine_serial_number="E-1", installation_ref="INSTALL-001",
            event_date=date(2026, 10, 1), event_sequence=1,
            techsheet_ref="TS-003", event_type="TOP_UP", oil_quantity=1,
            oil_unit="QT", flight_hours=1.2,
        )


def test_invalid_numeric_values_rejected():
    with pytest.raises(ValueError):
        EntryPayload(
            aircraft_serial_number="AC-001", engine_position="1",
            engine_serial_number="E-1", installation_ref="INSTALL-001",
            event_date=date(2026, 10, 1), event_sequence=1,
            techsheet_ref="TS-003", event_type="TOP_UP", oil_quantity=float("inf"), oil_unit="QT",
        )


def test_review_attestation_required_for_verification():
    with pytest.raises(ValueError):
        EntryReview(decision="VERIFIED", note="Reviewed the techsheet")
    reviewed = EntryReview(
        decision="VERIFIED", note="Original techsheet and engine log checked",
        source_checked=True, engine_identity_checked=True, exposure_checked=True,
    )
    assert reviewed.source_checked and reviewed.exposure_checked
    returned = EntryReview(decision="RETURNED", note="Source is incomplete")
    assert not returned.source_checked


def test_manufacturer_limit_requires_current_technical_data_confirmation():
    with pytest.raises(ValueError):
        ProfileApproval(confirmed_current_technical_data=False, note="Unknown engine data")
    approved = ProfileApproval(
        confirmed_current_technical_data=True,
        note="Confirmed current engine maintenance manual and installed engine applicability",
    )
    assert approved.confirmed_current_technical_data


def test_daily_coverage_uses_snapshots_without_inventing_operational_completeness():
    snapshots = [
        Row(aircraft_serial_number="AC-001", engine_position="1", flight_leg="SL-001",
            engine_serial_number="ENGINE-123"),
        Row(aircraft_serial_number="AC-001", engine_position="1", flight_leg="SL-002",
            engine_serial_number="ENGINE-123"),
    ]
    entries = [
        Row(aircraft_serial_number="AC-001", engine_position="1", sector_ref="SL-001",
            engine_serial_number="ENGINE-123", event_type="TOP_UP", review_status="DRAFT"),
    ]
    report = summarize_daily_coverage(snapshots, entries)
    assert report["registered_snapshot_sectors"] == 2
    assert report["matched_sectors"] == 1
    assert report["unverified_observations"] == 1
    assert report["unmatched_sectors"][0]["flight_leg"] == "SL-002"
    empty = summarize_daily_coverage([], entries)
    assert empty["registered_snapshot_sectors"] == 0
    assert empty["coverage_basis"] == "RECORDED_ENGINE_FLIGHT_SNAPSHOTS_ONLY"
