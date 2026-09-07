from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import event, text
from starlette.requests import Request

from amodb.database import Base
from amodb.apps.accounts import models as account_models
from amodb.apps.quality import models as quality_models
from amodb.apps.quality.audit_deletion_service import (
    _audit_schema,
    build_audit_deletion_impact,
    permanently_delete_audit,
    recycle_bin_days_remaining,
    recycle_bin_purge_at,
)
from amodb.apps.quality.audit_notice_models import (
    QualityAuditNotice,
    QualityAuditNoticeArtifact,
    QualityAuditNoticePolicy,
)
from amodb.apps.quality.audit_schedule_rules import validate_planned_window
from amodb.apps.quality.router import (
    _require_quality_audit_manager,
    delete_audit,
    delete_audit_schedule,
    list_audit_schedules,
    list_audits,
    restore_audit,
    restore_audit_schedule,
)
from amodb.jobs import quality_recycle_bin_automation


def _request() -> Request:
    return Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1)})


def test_planned_window_enforces_tenant_business_hours_and_no_overnight() -> None:
    assert validate_planned_window(
        planned_start=date(2026, 9, 10),
        planned_end=date(2026, 9, 12),
        planned_start_time=time(10, 0),
        planned_end_time=time(13, 0),
    ) == (time(10, 0), time(13, 0))

    with pytest.raises(HTTPException, match="between 09:00 and 17:00"):
        validate_planned_window(
            planned_start=date(2026, 9, 10),
            planned_end=date(2026, 9, 10),
            planned_start_time=time(8, 59),
            planned_end_time=time(13, 0),
        )

    with pytest.raises(HTTPException, match="overnight audits are not permitted"):
        validate_planned_window(
            planned_start=date(2026, 9, 10),
            planned_end=date(2026, 9, 12),
            planned_start_time=time(14, 0),
            planned_end_time=time(10, 0),
        )


def test_permanent_delete_permission_excludes_ordinary_auditors() -> None:
    with pytest.raises(HTTPException) as denied:
        _require_quality_audit_manager(SimpleNamespace(
            role=account_models.AccountRole.AUDITOR,
            is_amo_admin=False,
            is_superuser=False,
        ))
    assert denied.value.status_code == 403

    _require_quality_audit_manager(SimpleNamespace(
        role=account_models.AccountRole.QUALITY_OFFICER,
        is_amo_admin=False,
        is_superuser=False,
    ))


def test_recycle_bin_retention_is_exactly_thirty_days() -> None:
    deleted_at = datetime(2026, 9, 5, 10, 30, tzinfo=timezone.utc)
    assert recycle_bin_purge_at(deleted_at) == deleted_at + timedelta(days=30)
    assert recycle_bin_days_remaining(deleted_at, now=deleted_at) == 30
    assert recycle_bin_days_remaining(deleted_at, now=deleted_at + timedelta(days=29, hours=1)) == 1
    assert recycle_bin_days_remaining(deleted_at, now=deleted_at + timedelta(days=31)) == 0


def test_soft_delete_and_restore_preserve_audit_workflow_and_schedule_state(db_session) -> None:
    amo = account_models.AMO(
        amo_code="AMO-RECYCLE",
        login_slug="amo-recycle",
        name="Recycle Test AMO",
    )
    db_session.add(amo)
    db_session.flush()
    manager = account_models.User(
        amo_id=amo.id,
        email="quality.manager@example.test",
        staff_code="QM-RECYCLE",
        first_name="Quality",
        last_name="Manager",
        full_name="Quality Manager",
        hashed_password="hash",
        role=account_models.AccountRole.QUALITY_MANAGER,
        is_active=True,
    )
    db_session.add(manager)
    db_session.flush()
    audit = quality_models.QMSAudit(
        amo_id=amo.id,
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        status=quality_models.QMSAuditStatus.CAP_OPEN,
        audit_ref="QAR/MO/26/150",
        reference_family="QAR",
        unit_code="MO",
        ref_year=26,
        ref_sequence=150,
        title="Recoverable audit",
        planned_start=date(2026, 9, 10),
        planned_end=date(2026, 9, 11),
        planned_start_time=time(10, 0),
        planned_end_time=time(13, 0),
        report_file_ref="s3://test/recoverable-report.pdf",
    )
    schedule = quality_models.QMSAuditSchedule(
        amo_id=amo.id,
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        frequency=quality_models.QMSAuditScheduleFrequency.ANNUAL,
        title="Recoverable schedule",
        duration_days=2,
        next_due_date=date(2027, 9, 10),
        is_active=True,
    )
    db_session.add_all([audit, schedule])
    db_session.flush()
    finding = quality_models.QMSAuditFinding(
        amo_id=amo.id,
        audit_id=audit.id,
        description="Finding state must survive recycling.",
    )
    db_session.add(finding)
    db_session.commit()

    delete_result = delete_audit(
        audit_id=audit.id,
        request=_request(),
        reason="Duplicate audit",
        db=db_session,
        current_user=manager,
    )
    db_session.refresh(audit)
    assert delete_result["recoverable"] is True
    assert audit.deleted_at is not None
    assert audit.delete_reason == "Duplicate audit"
    assert audit.status == quality_models.QMSAuditStatus.CAP_OPEN
    assert audit.report_file_ref == "s3://test/recoverable-report.pdf"
    assert db_session.query(quality_models.QMSAuditFinding).filter_by(id=finding.id).count() == 1

    other_amo = account_models.AMO(
        amo_code="AMO-OTHER",
        login_slug="amo-other",
        name="Other AMO",
    )
    db_session.add(other_amo)
    db_session.flush()
    other_manager = account_models.User(
        amo_id=other_amo.id,
        email="other.quality@example.test",
        staff_code="QM-OTHER",
        first_name="Other",
        last_name="Manager",
        full_name="Other Manager",
        hashed_password="hash",
        role=account_models.AccountRole.QUALITY_MANAGER,
        is_active=True,
    )
    db_session.add(other_manager)
    db_session.commit()
    with pytest.raises(HTTPException) as tenant_denied:
        restore_audit(
            audit_id=audit.id,
            request=_request(),
            db=db_session,
            current_user=other_manager,
        )
    assert tenant_denied.value.status_code == 404

    restored = restore_audit(
        audit_id=audit.id,
        request=_request(),
        db=db_session,
        current_user=manager,
    )
    assert restored.deleted_at is None
    assert restored.status == quality_models.QMSAuditStatus.CAP_OPEN
    assert db_session.query(quality_models.QMSAuditFinding).filter_by(id=finding.id).count() == 1

    delete_audit_schedule(
        schedule_id=schedule.id,
        request=_request(),
        reason=None,
        db=db_session,
        current_user=manager,
    )
    db_session.refresh(schedule)
    assert schedule.deleted_at is not None
    assert schedule.is_active is True
    assert list_audit_schedules(
        db=db_session,
        domain=None,
        active=None,
        deleted_only=False,
        include_deleted=False,
        limit=250,
        current_user=manager,
    ) == []
    deleted_schedule_rows = list_audit_schedules(
        db=db_session,
        domain=None,
        active=None,
        deleted_only=True,
        include_deleted=False,
        limit=250,
        current_user=manager,
    )
    assert [row.id for row in deleted_schedule_rows] == [schedule.id]
    assert deleted_schedule_rows[0].purge_at is not None
    assert deleted_schedule_rows[0].days_remaining == 30

    # The active audit register excludes recycled audits and includes them only
    # in the explicit recycle-bin query.
    delete_audit(
        audit_id=audit.id,
        request=_request(),
        reason=None,
        db=db_session,
        current_user=manager,
    )
    assert list_audits(
        db=db_session,
        domain=None,
        status_=None,
        kind=None,
        deleted_only=False,
        include_deleted=False,
        limit=250,
        current_user=manager,
    ) == []
    assert [row.id for row in list_audits(
        db=db_session,
        domain=None,
        status_=None,
        kind=None,
        deleted_only=True,
        include_deleted=False,
        limit=250,
        current_user=manager,
    )] == [audit.id]
    restore_audit(
        audit_id=audit.id,
        request=_request(),
        db=db_session,
        current_user=manager,
    )

    restored_schedule = restore_audit_schedule(
        schedule_id=schedule.id,
        request=_request(),
        db=db_session,
        current_user=manager,
    )
    assert restored_schedule.deleted_at is None
    assert restored_schedule.is_active is True


def test_retention_worker_purges_only_records_older_than_thirty_days(db_session, monkeypatch) -> None:
    now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
    amo = account_models.AMO(
        amo_code="AMO-TTL",
        login_slug="amo-ttl",
        name="Retention Test AMO",
    )
    db_session.add(amo)
    db_session.flush()
    expired_audit = quality_models.QMSAudit(
        amo_id=amo.id,
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref="QAR/MO/26/201",
        reference_family="QAR",
        unit_code="MO",
        ref_year=26,
        ref_sequence=201,
        title="Expired recycle audit",
        deleted_at=now - timedelta(days=31),
    )
    expired_schedule = quality_models.QMSAuditSchedule(
        amo_id=amo.id,
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        frequency=quality_models.QMSAuditScheduleFrequency.ANNUAL,
        title="Expired recycle schedule",
        duration_days=1,
        next_due_date=date(2027, 9, 5),
        deleted_at=now - timedelta(days=31),
    )
    recoverable_schedule = quality_models.QMSAuditSchedule(
        amo_id=amo.id,
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        frequency=quality_models.QMSAuditScheduleFrequency.ANNUAL,
        title="Still recoverable schedule",
        duration_days=1,
        next_due_date=date(2027, 9, 6),
        deleted_at=now - timedelta(days=29),
    )
    db_session.add_all([expired_audit, expired_schedule, recoverable_schedule])
    db_session.commit()

    monkeypatch.setattr(quality_recycle_bin_automation, "WriteSessionLocal", lambda: db_session)
    monkeypatch.setattr(quality_recycle_bin_automation, "close_session_safely", lambda _db: None)
    result = quality_recycle_bin_automation.run_once(now=now)

    assert result == {"audits_purged": 1, "schedules_purged": 1, "failed": 0}
    assert db_session.query(quality_models.QMSAudit).filter_by(id=expired_audit.id).count() == 0
    assert db_session.query(quality_models.QMSAuditSchedule).filter_by(id=expired_schedule.id).count() == 0
    assert db_session.query(quality_models.QMSAuditSchedule).filter_by(id=recoverable_schedule.id).count() == 1


def test_audit_deletion_schema_avoids_per_table_catalogue_fk_queries(db_session) -> None:
    statements: list[str] = []
    engine = db_session.get_bind()

    def capture_statement(_connection, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(str(statement).lower())

    event.listen(engine, "before_cursor_execute", capture_statement)
    try:
        first = _audit_schema(db_session)
        second = _audit_schema(db_session)
    finally:
        event.remove(engine, "before_cursor_execute", capture_statement)

    assert first is second
    assert "qms_audits" in first.tables
    assert "qms_audits" in first.cascade_children
    assert not any("foreign_key_list" in statement for statement in statements)

def test_permanent_audit_delete_inventories_nested_records_and_files(db_session, tmp_path, monkeypatch) -> None:
    Base.metadata.create_all(
        bind=db_session.get_bind(),
        tables=[
            quality_models.QMSFindingAttachment.__table__,
            QualityAuditNoticePolicy.__table__,
            QualityAuditNotice.__table__,
            QualityAuditNoticeArtifact.__table__,
        ],
    )
    db_session.execute(text("PRAGMA foreign_keys=ON"))
    storage_root = tmp_path / "objects"
    storage_root.mkdir()
    monkeypatch.setenv("AMO_STORAGE_BACKEND", "local")
    monkeypatch.setenv("AMO_STORAGE_LOCAL_ROOT", str(storage_root))

    amo = account_models.AMO(
        amo_code="AMO-PURGE",
        login_slug="amo-purge",
        name="Purge Test AMO",
        contact_email="quality@example.test",
        time_zone="Africa/Nairobi",
    )
    db_session.add(amo)
    db_session.flush()
    audit = quality_models.QMSAudit(
        amo_id=amo.id,
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref="QAR/MO/26/099",
        reference_family="QAR",
        unit_code="MO",
        ref_year=26,
        ref_sequence=99,
        title="Deletion cascade audit",
        planned_start=date(2026, 9, 10),
        planned_end=date(2026, 9, 10),
        planned_start_time=time(10, 0),
        planned_end_time=time(13, 0),
    )
    db_session.add(audit)
    db_session.flush()
    finding = quality_models.QMSAuditFinding(
        amo_id=amo.id,
        audit_id=audit.id,
        description="Controlled test finding",
    )
    db_session.add(finding)
    db_session.flush()

    file_names = ["report.pdf", "cap.pdf", "car.pdf", "response.pdf", "attachment.pdf", "notice.pdf", "finding.pdf"]
    files = {name: storage_root / name for name in file_names}
    for path in files.values():
        path.write_bytes(b"controlled audit object")
    audit.report_file_ref = str(files["report.pdf"])
    db_session.add_all([
        quality_models.QMSCorrectiveAction(
            amo_id=amo.id,
            finding_id=finding.id,
            evidence_ref=str(files["cap.pdf"]),
        ),
        quality_models.QMSFindingAttachment(
            finding_id=finding.id,
            filename="finding.pdf",
            file_ref=str(files["finding.pdf"]),
        ),
    ])
    car = quality_models.CorrectiveActionRequest(
        amo_id=amo.id,
        program=quality_models.CARProgram.QUALITY,
        car_number="Q-2026-0099",
        title="Finding corrective action",
        summary="Corrective action created from the audit finding.",
        invite_token="audit-purge-token",
        finding_id=finding.id,
        evidence_ref=str(files["car.pdf"]),
    )
    db_session.add(car)
    db_session.flush()
    db_session.add_all([
        quality_models.CARActionLog(car_id=car.id, message="Corrective action opened."),
        quality_models.CARResponse(car_id=car.id, evidence_ref=str(files["response.pdf"])),
        quality_models.CARAttachment(
            car_id=car.id,
            filename="attachment.pdf",
            file_ref=str(files["attachment.pdf"]),
        ),
    ])
    notice = QualityAuditNotice(
        amo_id=amo.id,
        audit_id=audit.id,
        revision_no=1,
        status="DRAFT",
        required_notice_days=14,
        notice_date=date(2026, 9, 1),
        subject="Audit notice",
        body="Controlled audit notice",
        audit_snapshot={},
        recipient_snapshot=[],
    )
    db_session.add(notice)
    db_session.flush()
    db_session.add(QualityAuditNoticeArtifact(
        amo_id=amo.id,
        audit_id=audit.id,
        notice_id=notice.id,
        source_type="GENERATED",
        storage_ref=str(files["notice.pdf"]),
        filename="notice.pdf",
        content_type="application/pdf",
        size_bytes=10,
        sha256="a" * 64,
    ))
    db_session.commit()

    impact = build_audit_deletion_impact(db_session, audit=audit)
    assert impact["database_record_count"] == 10
    assert impact["managed_file_count"] == len(files)
    assert sum(group["count"] for group in impact["groups"]) == 9
    assert impact["controlled_dms_sources_preserved"] is True

    result = permanently_delete_audit(db_session, audit=audit, actor_user_id="user-1")
    assert result["managed_files_deleted"] == len(files)
    assert db_session.query(quality_models.QMSAudit).filter_by(id=audit.id).count() == 0
    assert db_session.query(quality_models.QMSAuditFinding).filter_by(id=finding.id).count() == 0
    assert db_session.query(quality_models.CorrectiveActionRequest).filter_by(id=car.id).count() == 0
    assert db_session.query(QualityAuditNotice).count() == 0
    assert all(not path.exists() for path in files.values())
