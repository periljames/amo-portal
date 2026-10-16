"""Source-document fidelity regression tests for SL/MCM/1 page entry."""
from datetime import date

import pytest

from amodb.apps.reliability import octm, techlog_capture as capture


def page(**changes):
    data = {
        "aircraft_serial_number": "A/C-SN-0001",
        "techsheet_ref": "SL-MCM-1-12345",
        "event_date": date(2026, 10, 5),
        "source_evidence_ref": "TECH-RECORDS-DOC-5688",
        "legs": [
            {"number": 1, "from_airport": "WIL", "to_airport": "MBA", "flight_hours": 1.25,
             "left_oil_level": "3", "right_oil_level": "4"},
            {"number": 2, "from_airport": "MBA", "to_airport": "WIL", "flight_hours": 1.5,
             "left_oil_level": "3", "right_oil_level": "3"},
        ],
        "page_flight_hours": 2.75,
        "ttaf_brought_forward": 15420.0,
        "ttaf_updated": 15422.75,
        "maintenance_complete": "UNKNOWN",
        "apu_oil_added": 1.5,
        "apu_oil_unit": "QT",
        "defect_references": ["DEF-001"],
        "deferred_defect_references": ["ADD-0750"],
        "engines": [
            {"position": "1", "engine_serial_number": "PCE-AAA",
             "installation_ref": "INSTALL-2026-10", "observation": "TOP_UP",
             "quantity_added": 1.25, "original_unit": "QT",
             "reference_method": "DIPSTICK", "reference_level": "FULL",
             "oil_specification": "Source to confirm"},
            {"position": "2", "engine_serial_number": "PCE-BBB",
             "installation_ref": "INSTALL-2026-10-RH", "observation": "MISSING"},
        ],
    }
    data.update(changes)
    return capture.TechlogPage(**data)


def test_page_uplift_remains_page_level_and_not_sector_assigned():
    candidates = capture.build_page_entries(page())
    assert len(candidates) == 2
    assert all(e.source_scope == "TECHLOG_PAGE" for e in candidates)
    assert all(e.sector_ref == "TECHLOG_PAGE:SL-MCM-1-12345" for e in candidates)
    assert all(e.flight_hours == 2.75 for e in candidates)
    assert candidates[0].oil_quantity == 1.25
    assert candidates[1].oil_quantity is None
    assert candidates[1].event_type == "MISSING"
    assert candidates[0].engine_counter_hours is None  # TTAF is aircraft, not engine ETSN
    assert candidates[0].source_context["apu_oil_added"] == 1.5
    assert candidates[0].source_context["deferred_defect_references"] == ["ADD-0750"]
    assert len(candidates[0].source_context["original_legs"]) == 2


def test_single_engine_page_never_invents_right_engine_or_apu_consumption():
    lone = page(engines=[
        {"position": "1", "engine_serial_number": "PCE-SINGLE",
         "installation_ref": "C208B-INSTALL", "observation": "MISSING"}
    ])
    entries = capture.build_page_entries(lone)
    assert len(entries) == 1
    assert entries[0].oil_quantity is None
    assert entries[0].flight_hours == 2.75


def test_flight_leg_totals_must_reconcile_with_page_total():
    with pytest.raises(ValueError, match="Flight Time"):
        page(page_flight_hours=4.5)


def test_aircraft_tt_af_must_reconcile_without_becoming_engine_etsn():
    with pytest.raises(ValueError, match="TTAF"):
        page(ttaf_updated=15426.0)


def test_duplicate_leg_numbers_and_engine_positions_rejected():
    with pytest.raises(ValueError, match="leg number"):
        page(legs=[
            {"number": 1, "flight_hours": 1.25},
            {"number": 1, "flight_hours": 1.5},
        ])
    with pytest.raises(ValueError, match="position"):
        page(engines=[
            {"position": "1", "engine_serial_number": "PCE-AAA", "installation_ref": "INST-A",
             "observation": "MISSING"},
            {"position": "1", "engine_serial_number": "PCE-BBB", "installation_ref": "INST-B",
             "observation": "MISSING"},
        ])


def test_blank_oil_added_never_creates_confirmed_zero():
    data = page()
    assert capture.build_page_entries(data)[1].event_type == "MISSING"
    with pytest.raises(ValueError):
        capture.TechlogEngineOil(
            position="1", engine_serial_number="ENGINE", installation_ref="INST",
            observation="CHECK_ZERO", quantity_added=2, original_unit="QT",
        )


def test_page_total_and_sector_exposure_cannot_form_same_engine_daily_window():
    from types import SimpleNamespace as Row
    from datetime import datetime, timezone
    def event(seq, day, scope, fh=10):
        return Row(
            id=str(seq), review_status="VERIFIED", engine_serial_number="PCE-123",
            installation_ref="INST", aircraft_serial_number="A/C-01", engine_position="1",
            event_date=date(2026, 10, day), event_sequence=seq,
            created_at=datetime(2026, 10, day, tzinfo=timezone.utc),
            sector_ref=("TECHLOG_PAGE:P1" if scope == "TECHLOG_PAGE" else "LEG-1"),
            source_scope=scope, event_type="TOP_UP",
            oil_quantity=1, oil_unit="QT", reference_method="DIPSTICK",
            reference_level="FULL", flight_hours=fh,
        )
    rows = [event(1, 1, "SECTOR"), event(2, 2, "SECTOR"),
            event(3, 3, "SECTOR"), event(4, 3, "TECHLOG_PAGE"),
            event(5, 4, "SECTOR")]
    assert octm.calculate_windows(rows, []) == []
