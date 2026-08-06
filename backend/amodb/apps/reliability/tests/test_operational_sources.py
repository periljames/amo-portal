from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from amodb.apps.reliability import operational_sources as ops


NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


def test_flight_delay_is_derived_from_departure_times():
    payload = ops.FlightOperationCreate(
        record_number="OPS-001",
        event_type="TECHNICAL_DELAY",
        scheduled_departure_at=NOW,
        actual_departure_at=NOW + timedelta(minutes=18),
        aircraft_serial_number="AC-001",
        flight_number="SLK101",
        description="Technical departure delay.",
    )
    assert payload.delay_minutes == 18
    assert payload.occurred_at == NOW + timedelta(minutes=18)
    assert payload.dispatch_impact == "DELAYED_DEPARTURE"


def test_flight_delay_rejects_missing_or_conflicting_timing():
    common = dict(
        record_number="OPS-001",
        event_type="TECHNICAL_DELAY",
        aircraft_serial_number="AC-001",
        flight_number="SLK101",
        description="Technical departure delay.",
    )
    with pytest.raises(ValidationError, match="scheduled and actual"):
        ops.FlightOperationCreate(**common)
    with pytest.raises(ValidationError, match="after scheduled"):
        ops.FlightOperationCreate(
            **common,
            scheduled_departure_at=NOW,
            actual_departure_at=NOW,
        )
    with pytest.raises(ValidationError, match="must match"):
        ops.FlightOperationCreate(
            **common,
            scheduled_departure_at=NOW,
            actual_departure_at=NOW + timedelta(minutes=18),
            delay_minutes=17,
        )


def test_flight_event_rejects_conflicting_dispatch_impact():
    with pytest.raises(ValidationError, match="dispatch_impact conflicts"):
        ops.FlightOperationCreate(
            record_number="OPS-CONFLICT",
            event_type="DIVERSION",
            occurred_at=NOW,
            aircraft_serial_number="AC-001",
            flight_number="SLK100",
            dispatch_impact="RETURN_TO_GATE",
            description="Conflicting operational classification.",
        )


def test_flight_cancellation_uses_schedule_without_actual_departure():
    payload = ops.FlightOperationCreate(
        record_number="OPS-002",
        event_type="TECHNICAL_CANCELLATION",
        occurred_at=NOW - timedelta(minutes=30),
        scheduled_departure_at=NOW,
        aircraft_serial_number="AC-001",
        flight_number="SLK102",
        description="Flight cancelled following an unserviceable condition.",
    )
    assert payload.delay_minutes is None
    assert payload.dispatch_impact == "CANCELLED"
    with pytest.raises(ValidationError, match="cannot contain an actual departure"):
        ops.FlightOperationCreate(
            record_number="OPS-003",
            event_type="TECHNICAL_CANCELLATION",
            occurred_at=NOW - timedelta(minutes=30),
            scheduled_departure_at=NOW,
            actual_departure_at=NOW + timedelta(minutes=5),
            aircraft_serial_number="AC-001",
            flight_number="SLK103",
            description="Contradictory cancellation timing.",
        )


def test_non_delay_flight_event_derives_dispatch_impact():
    payload = ops.FlightOperationCreate(
        record_number="OPS-004",
        event_type="DIVERSION",
        occurred_at=NOW,
        aircraft_serial_number="AC-001",
        flight_number="SLK104",
        description="Diversion due to a technical indication.",
    )
    assert payload.dispatch_impact == "DIVERTED"
    assert payload.delay_minutes is None


def test_non_delay_flight_event_requires_occurrence_time():
    with pytest.raises(ValidationError, match="requires an occurrence time"):
        ops.FlightOperationCreate(
            record_number="OPS-004",
            event_type="DIVERSION",
            aircraft_serial_number="AC-001",
            flight_number="SLK104",
            description="Diversion due to a technical indication.",
        )


def test_deferral_expiry_cannot_precede_application():
    with pytest.raises(ValidationError):
        ops.DeferralCreate(
            deferral_number="MEL-001",
            deferral_type="MEL",
            aircraft_serial_number="AC-001",
            defect_reference="TL-100",
            item_reference="MEL 32-10-01",
            applied_at=NOW,
            expires_at=NOW - timedelta(minutes=1),
            control_basis="Approved MEL revision 12.",
            description="Nose wheel steering indication deferred.",
        )


def test_nff_requires_explicit_false_confirmed_failure():
    common = dict(
        shop_order_reference="SO-001",
        event_type="NO_FAULT_FOUND",
        part_number="PN-01",
        component_serial_number="SN-01",
        received_at=NOW,
        inspected_at=NOW + timedelta(hours=1),
        test_result="Bench test passed all approved limits.",
        disposition="Returned serviceable after repeat testing.",
        description="Intermittent report not reproduced.",
    )
    with pytest.raises(ValidationError):
        ops.ShopFindingCreate(**common)
    payload = ops.ShopFindingCreate(**common, confirmed_failure=False)
    assert payload.confirmed_failure is False


def test_sms_relevance_requires_accountable_reason():
    with pytest.raises(ValidationError):
        ops.SmsAssessment(
            reliability_relevant=True,
            investigation_status="UNDER_INVESTIGATION",
        )
    payload = ops.SmsAssessment(
        reliability_relevant=True,
        reliability_link_reason="Technical recurrence requires Reliability trending.",
        investigation_status="UNDER_INVESTIGATION",
    )
    assert payload.reliability_relevant is True


def test_workbook_mapping_requires_canonical_fields():
    with pytest.raises(ValidationError):
        ops.WorkbookMapRequest(mapping={"event_type": "Type"})
    payload = ops.WorkbookMapRequest(
        mapping={
            "event_type": "Type",
            "occurred_at": "Date",
            "description": "Description",
        }
    )
    assert payload.mapping["occurred_at"] == "Date"


def test_exact_aviation_decimal_uses_decimal_string_conversion():
    column_type = ops.ExactAviationDecimal()
    assert column_type.process_bind_param(0.1, None) == Decimal("0.100")
    assert column_type.process_bind_param("1234.5674", None) == Decimal("1234.567")


def test_exact_cycle_count_rejects_fractional_values():
    column_type = ops.ExactAviationCount()
    assert column_type.process_bind_param("1200", None) == 1200
    with pytest.raises(ValueError, match="whole number"):
        column_type.process_bind_param("12.5", None)


def test_operational_routes_replace_direct_adapter_bypass_routes():
    from amodb.apps.reliability import authoritative_adapters
    from amodb.apps.reliability import router as reliability_router

    paths = {route.path for route in reliability_router.routes}
    assert any(path.endswith("/operational-sources/flight-operations") for path in paths)
    assert any(path.endswith("/operational-sources/deferrals") for path in paths)
    assert any(path.endswith("/operational-sources/component-shop") for path in paths)
    assert any(path.endswith("/operational-sources/sms") for path in paths)
    assert any(path.endswith("/operational-sources/workbooks/upload") for path in paths)
    assert not any(path.endswith("/authoritative-sources/flight-operations/ingest") for path in paths)
    assert not any(path.endswith("/authoritative-sources/mel-cdl/ingest") for path in paths)
    assert not any(path.endswith("/authoritative-sources/component-shop/ingest") for path in paths)
    assert not any(path.endswith("/authoritative-sources/sms/ingest") for path in paths)
    assert not any(path.endswith("/authoritative-sources/workbook-history/ingest") for path in paths)

    states = {spec.code: spec.implementation_state for spec in authoritative_adapters.ADAPTER_SPECS}
    assert states["FLIGHT-OPERATIONS"] == "READY"
    assert states["MEL-CDL"] == "READY"
    assert states["COMPONENT-SHOP-FINDINGS"] == "READY"
    assert states["SMS-EVENTS"] == "READY"
    assert states["WORKBOOK-HISTORY"] == "READY"
