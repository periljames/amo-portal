from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from amodb.apps.accounts import models as account_models
from amodb.apps.quality import models as quality_models
from amodb.apps.quality.audit_lifecycle import (
    STAGE_ORDER,
    _checklist_metadata,
    _document_out,
    _previous_audits,
    build_workflow_v2,
)
from amodb.apps.quality.audit_lifecycle_models import (
    QualityAuditChecklistDocument,
    QualityAuditEvidenceReview,
    QualityAuditReportDocument,
    QualityAuditStageRecord,
)


def _user(db_session, amo_id: str, *, email: str, role: account_models.AccountRole) -> account_models.User:
    user = account_models.User(
        amo_id=amo_id,
        email=email,
        staff_code=email.split("@", 1)[0][:12].upper(),
        first_name="Quality",
        last_name="User",
        full_name="Quality User",
        hashed_password="x",
        role=role,
        is_active=True,
        is_amo_admin=role == account_models.AccountRole.AMO_ADMIN,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _audit(
    db_session,
    amo_id: str,
    lead_id: str,
    *,
    reference: str,
    title: str = "Base Audit",
    planned_start: date | None = None,
    planned_end: date | None = None,
    actual_start: date | None = None,
    actual_end: date | None = None,
    status: quality_models.QMSAuditStatus = quality_models.QMSAuditStatus.PLANNED,
    scope_id=None,
) -> quality_models.QMSAudit:
    row = quality_models.QMSAudit(
        amo_id=amo_id,
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        status=status,
        audit_ref=reference,
        reference_family="QAR",
        unit_code="MO",
        ref_year=26,
        ref_sequence=int(reference.rsplit("-", 1)[-1]) if reference.rsplit("-", 1)[-1].isdigit() else 1,
        title=title,
        audit_scope_id=scope_id,
        audit_scope_code="BASE",
        scope="Base maintenance processes and records",
        criteria="KCARs 2025 and MPM requirements",
        auditee="Base Maintenance",
        auditee_email="base@example.com",
        lead_auditor_user_id=lead_id,
        planned_start=planned_start,
        planned_end=planned_end,
        actual_start=actual_start,
        actual_end=actual_end,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _seed(db_session):
    amo = account_models.AMO(amo_code="AMO-LC", name="Lifecycle AMO", login_slug="lifecycle")
    db_session.add(amo)
    db_session.flush()
    lead = _user(db_session, amo.id, email="lead@example.com", role=account_models.AccountRole.QUALITY_MANAGER)
    db_session.commit()
    return amo, lead


def _checklist_version(db_session, audit, user, *, version=1, status="SOURCE"):
    row = QualityAuditChecklistDocument(
        amo_id=audit.amo_id,
        audit_id=audit.id,
        version_number=version,
        filename=f"checklist-v{version}.pdf",
        storage_key=f"/private/quality/{audit.id}/checklist-v{version}.pdf",
        content_type="application/pdf",
        size_bytes=100 + version,
        sha256=f"{version:064x}",
        source_type="TEST",
        fillable="YES",
        field_count=12,
        lifecycle_status=status,
        uploaded_by_user_id=user.id,
        committed_at=datetime.now(timezone.utc) if status in {"SOURCE", "COMMITTED"} else None,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _report_version(db_session, audit, user, *, version=1, status="ISSUED"):
    row = QualityAuditReportDocument(
        amo_id=audit.amo_id,
        audit_id=audit.id,
        version_number=version,
        filename=f"report-v{version}.pdf",
        storage_key=f"/private/quality/{audit.id}/report-v{version}.pdf",
        content_type="application/pdf",
        size_bytes=200 + version,
        sha256=f"{100 + version:064x}",
        lifecycle_status=status,
        issue_label="Issue 1" if status == "ISSUED" else None,
        uploaded_by_user_id=user.id,
        issued_by_user_id=user.id if status == "ISSUED" else None,
        issued_at=datetime.now(timezone.utc) if status == "ISSUED" else None,
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_planned_future_audit_never_inherits_false_completion_from_files(db_session):
    amo, lead = _seed(db_session)
    audit = _audit(
        db_session,
        amo.id,
        lead.id,
        reference="QAR-MO-26-001",
        planned_start=date.today() + timedelta(days=6),
        planned_end=date.today() + timedelta(days=7),
    )
    _checklist_version(db_session, audit, lead, status="SOURCE")
    _report_version(db_session, audit, lead, status="ISSUED")
    db_session.commit()

    workflow = build_workflow_v2(db_session, audit)
    states = {stage.id: stage for stage in workflow.stages}

    assert tuple(stage.id for stage in workflow.stages) == STAGE_ORDER
    assert workflow.percent_complete == 0
    assert states["war-room"].state == "READY"
    assert states["checklist"].complete is False
    assert states["findings"].state == "NOT_READY"
    assert states["cars"].state == "NOT_READY"
    assert states["evidence"].state == "NOT_READY"
    assert states["report"].complete is False
    assert states["closeout"].complete is False


def test_navigation_has_no_lifecycle_side_effect(db_session):
    amo, lead = _seed(db_session)
    audit = _audit(
        db_session,
        amo.id,
        lead.id,
        reference="QAR-MO-26-002",
        planned_start=date.today(),
        planned_end=date.today(),
    )
    db_session.commit()

    first = build_workflow_v2(db_session, audit).model_dump()
    second = build_workflow_v2(db_session, audit).model_dump()

    assert first == second
    assert db_session.query(QualityAuditStageRecord).filter(QualityAuditStageRecord.audit_id == audit.id).count() == 0


def test_checklist_source_is_readiness_not_completion(db_session):
    amo, lead = _seed(db_session)
    audit = _audit(
        db_session,
        amo.id,
        lead.id,
        reference="QAR-MO-26-003",
        planned_start=date.today(),
        planned_end=date.today(),
        actual_start=date.today(),
        status=quality_models.QMSAuditStatus.IN_PROGRESS,
    )
    _checklist_version(db_session, audit, lead, status="SOURCE")
    db_session.commit()

    workflow = build_workflow_v2(db_session, audit)
    checklist = next(stage for stage in workflow.stages if stage.id == "checklist")

    assert checklist.state == "IN_PROGRESS"
    assert checklist.complete is False
    assert workflow.checklist_uploaded is True
    assert workflow.checklist_complete is False


def test_explicit_checklist_and_fieldwork_records_drive_completion(db_session):
    amo, lead = _seed(db_session)
    audit = _audit(
        db_session,
        amo.id,
        lead.id,
        reference="QAR-MO-26-004",
        planned_start=date.today(),
        planned_end=date.today(),
        actual_start=date.today(),
        actual_end=date.today(),
        status=quality_models.QMSAuditStatus.IN_PROGRESS,
    )
    _checklist_version(db_session, audit, lead, status="COMMITTED")
    db_session.add_all([
        QualityAuditStageRecord(amo_id=amo.id, audit_id=audit.id, stage_id="war-room", state="COMPLETE", actor_user_id=lead.id),
        QualityAuditStageRecord(amo_id=amo.id, audit_id=audit.id, stage_id="checklist", state="COMPLETE", actor_user_id=lead.id),
        QualityAuditStageRecord(amo_id=amo.id, audit_id=audit.id, stage_id="findings", state="COMPLETE", actor_user_id=lead.id),
    ])
    db_session.commit()

    workflow = build_workflow_v2(db_session, audit)
    stages = {stage.id: stage for stage in workflow.stages}

    assert stages["war-room"].complete is True
    assert stages["checklist"].complete is True
    assert stages["findings"].complete is True
    assert stages["cars"].complete is True
    assert stages["evidence"].complete is False
    assert workflow.percent_complete == 57


def test_evidence_requires_explicit_acceptance(db_session):
    amo, lead = _seed(db_session)
    audit = _audit(
        db_session,
        amo.id,
        lead.id,
        reference="QAR-MO-26-005",
        planned_start=date.today(),
        planned_end=date.today(),
        actual_start=date.today(),
        actual_end=date.today(),
        status=quality_models.QMSAuditStatus.IN_PROGRESS,
    )
    checklist = _checklist_version(db_session, audit, lead, status="COMMITTED")
    db_session.add_all([
        QualityAuditStageRecord(amo_id=amo.id, audit_id=audit.id, stage_id="war-room", state="COMPLETE", actor_user_id=lead.id),
        QualityAuditStageRecord(amo_id=amo.id, audit_id=audit.id, stage_id="checklist", state="COMPLETE", actor_user_id=lead.id),
        QualityAuditStageRecord(amo_id=amo.id, audit_id=audit.id, stage_id="findings", state="COMPLETE", actor_user_id=lead.id),
    ])
    db_session.commit()

    pending = build_workflow_v2(db_session, audit)
    evidence_stage = next(stage for stage in pending.stages if stage.id == "evidence")
    assert evidence_stage.complete is False
    assert pending.evidence_pending == 1

    db_session.add(QualityAuditEvidenceReview(
        amo_id=amo.id,
        audit_id=audit.id,
        entity_type="CHECKLIST_VERSION",
        entity_id=str(checklist.id),
        status="ACCEPTED",
        reviewed_by_user_id=lead.id,
        reviewed_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    accepted = build_workflow_v2(db_session, audit)
    evidence_stage = next(stage for stage in accepted.stages if stage.id == "evidence")
    assert evidence_stage.complete is True
    assert accepted.evidence_pending == 0


def test_document_dto_never_exposes_storage_key(db_session):
    amo, lead = _seed(db_session)
    audit = _audit(db_session, amo.id, lead.id, reference="QAR-MO-26-006")
    version = _checklist_version(db_session, audit, lead)
    db_session.commit()

    payload = _document_out(version, kind="checklist").model_dump()

    assert "storage_key" not in payload
    assert str(Path(version.storage_key).parent) not in str(payload)
    assert payload["filename"] == "checklist-v1.pdf"
    assert payload["download_url"].endswith(f"/{version.id}/download")


def test_retained_checklist_versions_are_distinct_and_previous_source_remains(db_session):
    amo, lead = _seed(db_session)
    audit = _audit(db_session, amo.id, lead.id, reference="QAR-MO-26-007")
    source = _checklist_version(db_session, audit, lead, version=1, status="SOURCE")
    draft = _checklist_version(db_session, audit, lead, version=2, status="WORKING_DRAFT")
    committed = _checklist_version(db_session, audit, lead, version=3, status="COMMITTED")
    db_session.commit()

    metadata = _checklist_metadata(db_session, audit, lead)

    assert [row.version_number for row in metadata.versions] == [3, 2, 1]
    assert metadata.source is not None and metadata.source.id == source.id
    assert metadata.current is not None and metadata.current.id == committed.id
    assert draft.id != source.id != committed.id


def test_previous_audit_intelligence_requires_comparable_issued_report(db_session):
    amo, lead = _seed(db_session)
    previous = _audit(
        db_session,
        amo.id,
        lead.id,
        reference="QAR-MO-25-011",
        planned_start=date.today() - timedelta(days=190),
        planned_end=date.today() - timedelta(days=189),
        actual_start=date.today() - timedelta(days=190),
        actual_end=date.today() - timedelta(days=189),
        status=quality_models.QMSAuditStatus.CLOSED,
    )
    current = _audit(
        db_session,
        amo.id,
        lead.id,
        reference="QAR-MO-26-008",
        planned_start=date.today() + timedelta(days=5),
        planned_end=date.today() + timedelta(days=6),
    )
    _report_version(db_session, previous, lead, status="ISSUED")
    finding = quality_models.QMSAuditFinding(
        amo_id=amo.id,
        audit_id=previous.id,
        finding_ref="QAR-MO-25-011-F-001",
        description="Open carryover",
        finding_type=quality_models.QMSFindingType.NON_CONFORMITY,
        severity=quality_models.QMSFindingSeverity.MAJOR,
        level=quality_models.FindingLevel.LEVEL_2,
        requirement_ref="MPM 3.4",
        target_close_date=date.today() - timedelta(days=10),
    )
    db_session.add(finding)
    db_session.commit()

    matches, carryovers = _previous_audits(db_session, current)

    assert matches and matches[0].audit_ref == previous.audit_ref
    assert matches[0].report.available is True
    assert matches[0].report.download_url is not None
    assert matches[0].open_carryovers == 1
    assert carryovers and carryovers[0].overdue is True
