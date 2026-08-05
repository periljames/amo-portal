from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from amodb.apps.reliability.authoritative_adapters import (
    ComponentShopOccurrence,
    DeferralOccurrence,
    FlightOperationsOccurrence,
    HistoricalOccurrence,
    _qms_severity,
    _revisioned_external_id,
    _scheduled_check_context,
)


NOW = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)


def test_revisioned_external_id_retains_source_revision():
    assert _revisioned_external_id("MEL-CDL", "MEL-001", "3") == "MEL-CDL:MEL-001:3"


def test_technical_delay_requires_delay_minutes():
    with pytest.raises(ValidationError):
        FlightOperationsOccurrence(
            source_record_id="OPS-1",
            source_revision="1",
            occurred_at=NOW,
            aircraft_serial_number="AC-1",
            description="Technical delay",
            event_type="TECHNICAL_DELAY",
            flight_number="XY123",
        )


def test_deferral_expiry_cannot_precede_occurrence():
    with pytest.raises(ValidationError):
        DeferralOccurrence(
            source_record_id="MEL-1",
            source_revision="1",
            occurred_at=NOW,
            aircraft_serial_number="AC-1",
            description="Deferred item",
            event_type="MEL_DEFERRAL",
            mel_reference="28-01",
            deferred_until=NOW - timedelta(minutes=1),
            control_basis="Approved MEL control procedure",
        )


def test_nff_requires_explicit_false_confirmed_failure():
    with pytest.raises(ValidationError):
        ComponentShopOccurrence(
            source_record_id="SHOP-1",
            source_revision="1",
            occurred_at=NOW,
            description="No fault found after bench test",
            event_type="NO_FAULT_FOUND",
            part_number="PN-1",
            component_serial_number="SN-1",
            shop_order_reference="SO-1",
            disposition="Returned serviceable",
            confirmed_failure=None,
        )


def test_historical_occurrence_accepts_only_canonical_taxonomy():
    with pytest.raises(ValidationError):
        HistoricalOccurrence(
            source_record_id="ROW-1",
            source_revision="1",
            occurred_at=NOW,
            description="Legacy row",
            event_type="NOT_A_REAL_EVENT",
            source_workbook="legacy.xlsx",
            source_sheet="Events",
            source_row_number=2,
            mapping_profile="tenant-v1",
            reconciliation_status="APPROVED",
            reconciliation_note="Approved during migration review",
        )


def test_scheduled_non_routine_gets_explicit_context_and_new_mapping_revision():
    task = SimpleNamespace(
        origin_type=SimpleNamespace(value="NON_ROUTINE"),
        parent_task_id=99,
        work_order=SimpleNamespace(is_scheduled=True),
    )
    record = {"external_id": "WORKPACK_TASK:42:2026-08-05T08:00:00+00:00"}
    decorated = _scheduled_check_context(task, record)
    assert decorated["scheduled_check_finding"] is True
    assert decorated["maintenance_finding_context"] == "SCHEDULED_CHECK"
    assert decorated["parent_scheduled_task_id"] == 99
    assert decorated["external_id"].endswith(":SCHEDULED_CHECK_V2")
    assert record == {"external_id": "WORKPACK_TASK:42:2026-08-05T08:00:00+00:00"}


def test_unscheduled_non_routine_is_not_mislabeled_as_scheduled_check():
    task = SimpleNamespace(
        origin_type=SimpleNamespace(value="NON_ROUTINE"),
        parent_task_id=None,
        work_order=SimpleNamespace(is_scheduled=False),
    )
    record = {"external_id": "WORKPACK_TASK:7:REV"}
    assert _scheduled_check_context(task, record) is record


def test_qms_safety_sensitive_severity_is_critical():
    assert _qms_severity("MINOR", safety_sensitive=True) == "CRITICAL"
