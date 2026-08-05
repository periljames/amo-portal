from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from amodb.apps.reliability import workpack_integration as integration
from amodb.apps.work import models as work_models


def test_reserved_sources_cover_authoritative_workpack_domains():
    codes = {item.code for item in integration.INTERNAL_SOURCE_SPECS}
    assert {
        "WORKPACK-TASKS",
        "COMPONENT-REMOVALS",
        "TECH-RECORDS-USAGE",
        "EHM-INTERNAL",
        "MANUAL-ENTRY",
    }.issubset(codes)
    assert all(item.manual_fallback for item in integration.INTERNAL_SOURCE_SPECS)


def test_manual_entry_rejects_unknown_event_type():
    with pytest.raises(ValidationError):
        integration.ManualReliabilityEntry(
            event_type="NOT_A_REAL_EVENT",
            occurred_at=datetime.now(timezone.utc),
            description="Test entry",
            submitted_reason="Controlled manual capture",
        )


def test_workpack_task_record_retains_source_links_and_revision_identity():
    now = datetime.now(timezone.utc)
    work_order = SimpleNamespace(
        wo_number="WO-100",
        work_package_ref="PACK-77",
        check_type="A-CHECK",
        operator_event_id=None,
        status=work_models.WorkOrderStatusEnum.IN_PROGRESS,
    )
    task = SimpleNamespace(
        id=55,
        work_order=work_order,
        work_order_id=12,
        aircraft_serial_number="AC-001",
        aircraft_component_id=8,
        ata_chapter="32",
        task_code="NR-55",
        operator_event_id=None,
        priority=work_models.TaskPriorityEnum.HIGH,
        title="Repeat landing gear indication",
        description="Repeat defect found during the workpack.",
        component=SimpleNamespace(part_number="PN-1", serial_number="SN-1"),
        actual_end=now,
        actual_start=None,
        updated_at=now,
        created_at=now,
        category=work_models.TaskCategoryEnum.DEFECT,
        origin_type=work_models.TaskOriginTypeEnum.NON_ROUTINE,
        status=work_models.TaskStatusEnum.IN_PROGRESS,
        parent_task_id=None,
        program_item_id=4,
    )
    record = integration._task_record(task)
    assert record["event_type"] == "REPEAT_DEFECT"
    assert record["work_order_id"] == 12
    assert record["task_card_id"] == 55
    assert record["work_package_ref"] == "PACK-77"
    assert record["part_number"] == "PN-1"
    assert record["external_id"].startswith("WORKPACK_TASK:55:")


def test_router_registers_manual_and_coverage_contracts():
    from amodb.apps.reliability.router import router

    paths = {route.path for route in router.routes}
    assert "/reliability/manual-entry" in paths
    assert "/reliability/internal-sources/configure" in paths
    assert "/reliability/internal-sources/coverage" in paths


def test_sync_cursor_overlaps_last_success_without_crossing_epoch():
    last_success = datetime(2026, 8, 5, 7, 0, tzinfo=timezone.utc)
    assert integration._sync_cursor(last_success) == last_success - timedelta(minutes=5)
    assert integration._sync_cursor(None) == datetime(1970, 1, 1, tzinfo=timezone.utc)


def test_unscheduled_reason_cannot_be_misclassified_as_scheduled():
    assert integration._removal_event_type("UNSCHEDULED FAILURE") == "UNSCHEDULED_REMOVAL"
    assert integration._removal_event_type("Planned TBO change") == "SCHEDULED_REMOVAL"
    assert integration._removal_event_type(None) == "UNSCHEDULED_REMOVAL"


def test_authoritative_reference_conflicts_are_rejected():
    with pytest.raises(Exception) as caught:
        integration._assert_reference_match("Aircraft", "AC-1", "AC-2")
    assert getattr(caught.value, "status_code", None) == 422


def test_duplicate_only_batch_advances_internal_source_cursor():
    source = SimpleNamespace(
        last_success_at=None,
        last_failure_at=datetime.now(timezone.utc),
        next_poll_at=None,
        poll_interval_minutes=60,
    )
    batch = SimpleNamespace(invalid_count=0, valid_count=0, duplicate_count=3)
    now = datetime.now(timezone.utc)
    integration._advance_internal_source_after_batch(source, batch, now=now)
    assert source.last_success_at == now
    assert source.last_failure_at is None
    assert source.next_poll_at == now + timedelta(minutes=60)
