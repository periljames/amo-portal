from datetime import datetime, timezone
from decimal import Decimal
from inspect import getsource
from types import SimpleNamespace

from amodb.apps.reliability import advanced_services
from amodb.apps.reliability import services as workbench_services


def test_negative_delay_is_rejected_before_orm_insertion():
    payload = {
        "event_type": "TECHNICAL_DELAY",
        "occurred_at": "2026-08-04T00:00:00Z",
        "flight_number": "KQ100",
        "delay_minutes": -1,
    }
    errors, _ = advanced_services._validate_ingestion_record(payload)
    assert "delay_minutes must be a nonnegative whole number" in errors


def test_valid_delay_is_normalized_to_an_integer():
    payload = {
        "event_type": "TECHNICAL_DELAY",
        "occurred_at": "2026-08-04T00:00:00Z",
        "flight_number": "KQ100",
        "delay_minutes": "15.0",
    }
    errors, _ = advanced_services._validate_ingestion_record(payload)
    assert not errors
    assert payload["delay_minutes"] == 15


def test_percentage_metric_contract_uses_all_scoped_events_as_denominator():
    numerator, denominator, label = advanced_services._metric_event_contract(
        method="PERCENT",
        configured_event_types=["TECHNICAL_DELAY"],
    )
    assert numerator == ["TECHNICAL_DELAY"]
    assert denominator == []
    assert label == "ALL_RELIABILITY_EVENTS"


def test_nff_metric_contract_uses_unscheduled_removals_as_denominator():
    numerator, denominator, label = advanced_services._metric_event_contract(
        method="NFF_RATE",
        configured_event_types=["DEFECT"],
    )
    assert numerator == ["NO_FAULT_FOUND"]
    assert denominator == ["UNSCHEDULED_REMOVAL"]
    assert label == "UNSCHEDULED_REMOVALS"
    value, lower, upper = advanced_services._rate_with_confidence(
        events=2,
        exposure=Decimal("8"),
        multiplier=Decimal("100"),
        method="NFF_RATE",
    )
    assert value == Decimal("25.00000000")
    assert lower is None
    assert upper is None


def test_subdaily_schedule_advances_after_each_execution():
    metric = SimpleNamespace(schedule_interval_minutes=60, last_run_at=None, next_run_at=None)
    cutoff = datetime(2026, 8, 4, 5, 0, tzinfo=timezone.utc)
    advanced_services._advance_metric_schedule(metric, cutoff)
    assert metric.last_run_at == cutoff
    assert metric.next_run_at == datetime(2026, 8, 4, 6, 0, tzinfo=timezone.utc)


def test_existing_period_result_creates_an_immutable_revision():
    source = getsource(advanced_services.execute_metric)
    assert "pg_advisory_xact_lock" in source
    assert "ReliabilityCalculationRun.revision.desc()" in source
    assert "revision=revision" in source
    assert 'audit_action = "CALCULATION_REFRESHED" if previous else "CALCULATION_EXECUTED"' in source
    assert "run = existing" not in source
    assert "run.source_cutoff_at = source_cutoff" not in source


def test_delay_integer_boundaries_are_validated_before_insertion():
    accepted = {
        "event_type": "TECHNICAL_DELAY",
        "occurred_at": "2026-08-04T00:00:00Z",
        "flight_number": "KQ100",
        "delay_minutes": "2147483647",
    }
    errors, _ = advanced_services._validate_ingestion_record(accepted)
    assert not errors
    assert accepted["delay_minutes"] == 2147483647

    rejected = {
        "event_type": "TECHNICAL_DELAY",
        "occurred_at": "2026-08-04T00:00:00Z",
        "flight_number": "KQ101",
        "delay_minutes": "2147483648",
    }
    errors, _ = advanced_services._validate_ingestion_record(rejected)
    assert "delay_minutes must be a nonnegative whole number" in errors
    assert rejected["delay_minutes"] == "2147483648"


def test_workbench_total_engine_shift_count_is_not_page_limited():
    source = getsource(workbench_services.build_reliability_workbench)
    assert "func.count(models.EngineTrendStatus.id)" in source
    assert "engine_shifts=engine_shift_count" in source
    assert "engine_shifts=len(engine_shifts)" not in source
