import pytest
from pydantic import ValidationError

from amodb.apps.integrations.rollout_schemas import RolloutWaveCreate
from amodb.apps.integrations.rollout_services import (
    AIRCRAFT_TRANSITIONS,
    SPREADSHEET_TRANSITIONS,
    WAVE_TRANSITIONS,
)


def test_wave_dates_must_be_ordered():
    with pytest.raises(ValidationError):
        RolloutWaveCreate(
            name="Wave 1",
            sequence_no=1,
            planned_start="2026-09-10",
            planned_end="2026-09-01",
            aircraft_serial_numbers=["MSN-1"],
        )


def test_wave_requires_ready_before_progress():
    assert "READY" in WAVE_TRANSITIONS["PLANNED"]
    assert "IN_PROGRESS" not in WAVE_TRANSITIONS["PLANNED"]
    assert "IN_PROGRESS" in WAVE_TRANSITIONS["READY"]


def test_aircraft_cutover_cannot_skip_dual_run():
    assert "DUAL_RUN" in AIRCRAFT_TRANSITIONS["PLANNED"]
    assert "CUTOVER" not in AIRCRAFT_TRANSITIONS["PLANNED"]
    assert "CUTOVER" in AIRCRAFT_TRANSITIONS["DUAL_RUN"]


def test_spreadsheet_retirement_cannot_skip_read_only():
    assert SPREADSHEET_TRANSITIONS["LIVE"] == {"DUAL_RUN"}
    assert "RETIRED" not in SPREADSHEET_TRANSITIONS["DUAL_RUN"]
    assert "RETIRED" in SPREADSHEET_TRANSITIONS["READ_ONLY"]
