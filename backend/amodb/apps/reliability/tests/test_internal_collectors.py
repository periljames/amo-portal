from types import SimpleNamespace
from unittest.mock import MagicMock

from amodb.apps.reliability import internal_collectors
from amodb.apps.work.models import TaskCategoryEnum, TaskOriginTypeEnum, TaskStatusEnum


def task(**overrides):
    values = {
        "id": 41,
        "task_code": "MEL 27-10-01",
        "title": "Deferred elevator trim indication",
        "description": "Controlled under the MEL",
        "status": TaskStatusEnum.DEFERRED,
        "category": TaskCategoryEnum.DEFECT,
        "origin_type": TaskOriginTypeEnum.NON_ROUTINE,
        "updated_at": SimpleNamespace(isoformat=lambda: "2026-08-03T10:00:00+00:00"),
        "actual_start": None,
        "created_at": SimpleNamespace(isoformat=lambda: "2026-08-03T09:00:00+00:00"),
        "aircraft_serial_number": "AC-001",
        "ata_chapter": "27",
        "work_order_id": 9,
        "aircraft_component_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_deferred_task_requires_explicit_mel_or_cdl_text():
    assert internal_collectors._explicit_deferral_type(task()) == "MEL_DEFERRAL"
    assert internal_collectors._explicit_deferral_type(
        task(task_code="CDL 52-01", title="Door fairing", description="CDL control")
    ) == "CDL_DEFERRAL"
    assert internal_collectors._explicit_deferral_type(
        task(task_code="NR-001", title="Deferred defect", description="Awaiting part")
    ) == "DEFECT"


def test_task_record_preserves_source_state_and_traceability():
    record = internal_collectors._task_record(task())
    assert record["event_type"] == "MEL_DEFERRAL"
    assert record["task_card_id"] == 41
    assert record["work_order_id"] == 9
    assert record["aircraft_serial_number"] == "AC-001"
    assert record["ata_chapter"] == "27"
    assert record["maintenance_status"] == "DEFERRED"
    assert record["mel_reference"] == "MEL 27-10-01"
    assert record["external_id"] == "TASK_CARD_DEFERRAL:41"


def test_unsupported_internal_source_does_not_query_or_invent_records():
    db = MagicMock()
    records = internal_collectors.collect_internal_records(
        db,
        source_type="SMS",
        amo_id="amo-1",
        cursor=MagicMock(),
    )
    assert records == []
    db.query.assert_not_called()


def test_authoritative_collector_registry_is_explicit(monkeypatch):
    expected = {
        "TECH_LOG": "tech-log",
        "MAINTENANCE": "maintenance",
        "TECH_RECORDS": "tech-records",
        "QMS": "qms",
        "PROCUREMENT": "procurement",
    }
    monkeypatch.setattr(
        internal_collectors,
        "collect_tech_log_records",
        lambda *_args, **_kwargs: ["tech-log"],
    )
    monkeypatch.setattr(
        internal_collectors,
        "collect_maintenance_records",
        lambda *_args, **_kwargs: ["maintenance"],
    )
    monkeypatch.setattr(
        internal_collectors,
        "collect_technical_record_events",
        lambda *_args, **_kwargs: ["tech-records"],
    )
    monkeypatch.setattr(
        internal_collectors,
        "collect_reliability_qms_records",
        lambda *_args, **_kwargs: ["qms"],
    )
    monkeypatch.setattr(
        internal_collectors,
        "collect_procurement_quality_records",
        lambda *_args, **_kwargs: ["procurement"],
    )

    for source_type, marker in expected.items():
        assert internal_collectors.collect_internal_records(
            MagicMock(),
            source_type=source_type,
            amo_id="amo-1",
            cursor=MagicMock(),
            limit=1,
        ) == [marker]
