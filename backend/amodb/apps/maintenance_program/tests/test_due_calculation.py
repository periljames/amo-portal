from datetime import date, datetime, timezone
from types import SimpleNamespace

from amodb.apps.maintenance_program import service
from amodb.apps.maintenance_program.models import AircraftProgramStatusEnum


def program(**overrides):
    values = {
        "interval_hours": None,
        "interval_cycles": None,
        "interval_days": None,
        "threshold_hours": None,
        "threshold_cycles": None,
        "threshold_days": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def aircraft_item(**overrides):
    values = {
        "last_done_hours": None,
        "last_done_cycles": None,
        "last_done_date": None,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "next_due_hours": None,
        "next_due_cycles": None,
        "next_due_date": None,
        "remaining_hours": None,
        "remaining_cycles": None,
        "remaining_days": None,
        "status": AircraftProgramStatusEnum.PLANNED,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_calendar_threshold_has_stable_baseline():
    state = service._calculate_due_state(
        program_item=program(threshold_days=30),
        api=aircraft_item(),
        current_hours=0.0,
        current_cycles=0.0,
        today=date(2026, 2, 15),
    )
    assert state["next_due_date"] == date(2026, 1, 31)
    assert state["remaining_days"] == -15.0
    assert state["overdue_by_days"] == 15.0
    assert state["status"] == AircraftProgramStatusEnum.OVERDUE


def test_signed_values_are_only_clamped_for_storage():
    item = aircraft_item()
    state = service._calculate_due_state(
        program_item=program(threshold_hours=100.0, threshold_cycles=50.0),
        api=item,
        current_hours=115.5,
        current_cycles=54.0,
        today=date(2026, 2, 15),
    )
    assert state["remaining_hours"] == -15.5
    assert state["remaining_cycles"] == -4.0
    service._persist_due_state(item, state)
    assert item.remaining_hours == 0.0
    assert item.remaining_cycles == 0.0
    assert item.status == AircraftProgramStatusEnum.OVERDUE


def test_missing_calendar_accomplishment_is_unbaselined():
    state = service._calculate_due_state(
        program_item=program(interval_days=180),
        api=aircraft_item(created_at=None),
        current_hours=0.0,
        current_cycles=0.0,
        today=date(2026, 2, 15),
    )
    assert state["next_due_date"] is None
    assert state["baseline_status"] == "MISSING_BASELINE"


def test_due_soon_uses_non_negative_remaining_limit():
    state = service._calculate_due_state(
        program_item=program(threshold_hours=500.0),
        api=aircraft_item(),
        current_hours=475.0,
        current_cycles=0.0,
        today=date(2026, 2, 15),
    )
    assert state["remaining_hours"] == 25.0
    assert state["status"] == AircraftProgramStatusEnum.DUE_SOON
