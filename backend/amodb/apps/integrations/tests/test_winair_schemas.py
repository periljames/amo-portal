from datetime import date

import pytest
from pydantic import ValidationError

from amodb.apps.integrations.winair_schemas import (
    WinAirAircraftCounterPayload,
    WinAirConflictDecision,
    WinAirInboundBatch,
    WinAirInboundRecord,
    WinAirProfileCreate,
)


def test_profile_defaults_to_shadow_mode_and_controlled_authority():
    profile = WinAirProfileCreate(
        integration_config_id="cfg-1",
        name="Primary WinAir",
    )
    assert profile.mode == "SHADOW"
    assert profile.authority_json["AIRCRAFT_COUNTER"] == "WINAIR"
    assert profile.authority_json["MAINTENANCE_DUE"] == "PORTAL"


def test_counter_payload_requires_aircraft_identity():
    with pytest.raises(ValidationError):
        WinAirAircraftCounterPayload(
            entry_date=date(2026, 8, 4),
            techlog_no="TL-100",
            total_hours=1200.5,
            total_cycles=930,
        )


def test_inbound_batch_requires_records():
    with pytest.raises(ValidationError):
        WinAirInboundBatch(records=[])


def test_merged_conflict_requires_payload():
    with pytest.raises(ValidationError):
        WinAirConflictDecision(
            decision="MERGED",
            resolution_notes="Use reviewed values",
        )


def test_inbound_record_accepts_counter_dataset():
    record = WinAirInboundRecord(
        dataset="AIRCRAFT_COUNTER",
        external_key="flight-log-100",
        payload={
            "registration": "5Y-SLS",
            "entry_date": "2026-08-04",
            "techlog_no": "TL-100",
            "total_hours": 1200.5,
            "total_cycles": 930,
        },
    )
    batch = WinAirInboundBatch(records=[record], dry_run=True)
    assert batch.dry_run is True
    assert batch.records[0].external_key == "flight-log-100"
