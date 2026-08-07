from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from starlette.requests import Request

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.apps.quality import models as quality_models
import importlib
from amodb.apps.quality import register_pagination
from amodb.apps.quality import schemas as quality_schemas
from amodb.apps.quality import service as quality_service


def _make_request() -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(b"user-agent", b"pytest")],
            "client": ("127.0.0.1", 1234),
        }
    )


quality_router = importlib.import_module("amodb.apps.quality.router")


def _create_user(db_session, *, amo_id: str) -> account_models.User:
    user = account_models.User(
        amo_id=amo_id,
        email="qa@example.com",
        staff_code="QA1",
        first_name="QA",
        last_name="User",
        full_name="QA User",
        hashed_password="hash",
        role=account_models.AccountRole.AMO_ADMIN,
        is_active=True,
        is_amo_admin=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_publish_revision_logs_audit_event(db_session):
    amo = account_models.AMO(
        amo_code="AMO-PUB",
        name="Publish AMO",
        login_slug="publish",
    )
    db_session.add(amo)
    db_session.commit()
    user = _create_user(db_session, amo_id=amo.id)

    doc = quality_models.QMSDocument(
        amo_id=amo.id,
        domain=quality_models.QMSDomain.AMO,
        doc_type=quality_models.QMSDocType.MANUAL,
        doc_code="DOC-1",
        title="Test Manual",
    )
    db_session.add(doc)
    db_session.commit()

    rev = quality_models.QMSDocumentRevision(
        amo_id=amo.id,
        document_id=doc.id,
        issue_no=1,
        rev_no=0,
        issued_date=date.today(),
        file_ref="file.pdf",
        approved_by_authority=True,
        authority_ref="CAA-APP-1",
    )
    db_session.add(rev)
    db_session.commit()

    payload = quality_schemas.QMSPublishRevision(
        effective_date=date.today(),
        current_file_ref="file.pdf",
    )

    quality_router.publish_revision(
        doc_id=doc.id,
        revision_id=rev.id,
        payload=payload,
        request=_make_request(),
        db=db_session,
        current_user=user,
    )

    event = (
        db_session.query(audit_models.AuditEvent)
        .filter(audit_models.AuditEvent.entity_type == "qms_document", audit_models.AuditEvent.action == "transition")
        .first()
    )
    assert event is not None


def test_close_finding_logs_audit_event(db_session):
    amo = account_models.AMO(
        amo_code="AMO-FIND",
        name="Finding AMO",
        login_slug="finding",
    )
    db_session.add(amo)
    db_session.commit()
    user = _create_user(db_session, amo_id=amo.id)

    audit = quality_models.QMSAudit(
        amo_id=amo.id,
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref="AUD-1",
        title="Audit 1",
    )
    db_session.add(audit)
    db_session.commit()

    finding = quality_models.QMSAuditFinding(
        amo_id=amo.id,
        audit_id=audit.id,
        description="Finding",
        severity=quality_models.QMSFindingSeverity.MINOR,
        level=quality_models.FindingLevel.LEVEL_3,
        objective_evidence="Evidence attached",
        verified_at=datetime.utcnow(),
        verified_by_user_id=user.id,
    )
    db_session.add(finding)
    db_session.commit()

    quality_router.close_finding(
        finding_id=finding.id,
        request=_make_request(),
        db=db_session,
        current_user=user,
    )

    event = (
        db_session.query(audit_models.AuditEvent)
        .filter(audit_models.AuditEvent.entity_type == "qms_finding", audit_models.AuditEvent.action == "transition")
        .first()
    )
    assert event is not None


def test_export_car_pdf_logs_audit_event(db_session, monkeypatch, tmp_path):
    amo = account_models.AMO(
        amo_code="AMO-CAR",
        name="CAR AMO",
        login_slug="car",
    )
    db_session.add(amo)
    db_session.commit()
    user = _create_user(db_session, amo_id=amo.id)

    car = quality_service.create_car(
        db_session,
        amo_id=amo.id,
        program=quality_models.CARProgram.QUALITY,
        title="Test CAR",
        summary="Summary",
        priority=quality_models.CARPriority.MEDIUM,
        requested_by_user_id=user.id,
        assigned_to_user_id=None,
        due_date=None,
        target_closure_date=None,
        finding_id=None,
    )
    db_session.commit()

    pdf_path = tmp_path / "car.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 dummy")

    def _fake_generate(*args, **kwargs):
        return Path(pdf_path)

    monkeypatch.setattr(quality_router, "generate_car_form_pdf", _fake_generate)

    quality_router.print_car_form(
        car_id=car.id,
        request=_make_request(),
        db=db_session,
        current_user=user,
    )

    event = (
        db_session.query(audit_models.AuditEvent)
        .filter(audit_models.AuditEvent.entity_type == "qms_car", audit_models.AuditEvent.action == "export")
        .first()
    )
    assert event is not None


def test_audit_register_page_is_bounded_and_tenant_scoped(db_session):
    amo_a = account_models.AMO(amo_code="AMO-PAGE-A", name="Page A", login_slug="page-a")
    amo_b = account_models.AMO(amo_code="AMO-PAGE-B", name="Page B", login_slug="page-b")
    db_session.add_all([amo_a, amo_b])
    db_session.commit()
    user_a = _create_user(db_session, amo_id=amo_a.id)

    audit_a = quality_models.QMSAudit(
        amo_id=amo_a.id,
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref="QAR/MO/26/101",
        title="Tenant A audit",
    )
    audit_b = quality_models.QMSAudit(
        amo_id=amo_b.id,
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref="QAR/MO/26/201",
        title="Tenant B audit",
    )
    db_session.add_all([audit_a, audit_b])
    db_session.commit()

    findings = [
        quality_models.QMSAuditFinding(
            amo_id=amo_a.id,
            audit_id=audit_a.id,
            finding_ref=f"QAR/MO/26/101-F-00{index}",
            finding_type=quality_models.QMSFindingType.NON_CONFORMITY,
            severity=quality_models.QMSFindingSeverity.MINOR,
            level=quality_models.FindingLevel.LEVEL_3,
            description=description,
        )
        for index, description in enumerate(
            ["Training record not current", "Calibration label missing", "Procedure copy superseded"],
            start=1,
        )
    ]
    other_tenant_finding = quality_models.QMSAuditFinding(
        amo_id=amo_b.id,
        audit_id=audit_b.id,
        finding_ref="QAR/MO/26/201-F-001",
        finding_type=quality_models.QMSFindingType.NON_CONFORMITY,
        severity=quality_models.QMSFindingSeverity.MINOR,
        level=quality_models.FindingLevel.LEVEL_3,
        description="Other tenant finding",
    )
    db_session.add_all([*findings, other_tenant_finding])
    db_session.commit()

    car = quality_service.create_car(
        db_session,
        amo_id=amo_a.id,
        program=quality_models.CARProgram.QUALITY,
        title="Restore training currency",
        summary="Update the affected training record",
        priority=quality_models.CARPriority.HIGH,
        requested_by_user_id=user_a.id,
        assigned_to_user_id=None,
        due_date=date(2020, 1, 1),
        target_closure_date=None,
        finding_id=findings[0].id,
    )
    second_car = quality_service.create_car(
        db_session,
        amo_id=amo_a.id,
        program=quality_models.CARProgram.QUALITY,
        title="Restore calibration identification",
        summary="Replace the missing calibration label",
        priority=quality_models.CARPriority.MEDIUM,
        requested_by_user_id=user_a.id,
        assigned_to_user_id=None,
        due_date=None,
        target_closure_date=None,
        finding_id=findings[1].id,
    )
    third_car = quality_service.create_car(
        db_session,
        amo_id=amo_a.id,
        program=quality_models.CARProgram.QUALITY,
        title="Remove superseded procedure",
        summary="Replace the controlled copy",
        priority=quality_models.CARPriority.MEDIUM,
        requested_by_user_id=user_a.id,
        assigned_to_user_id=None,
        due_date=None,
        target_closure_date=None,
        finding_id=findings[2].id,
    )
    quality_service.create_car(
        db_session,
        amo_id=amo_b.id,
        program=quality_models.CARProgram.QUALITY,
        title="Other tenant corrective action",
        summary="Must never appear in tenant A results",
        priority=quality_models.CARPriority.MEDIUM,
        requested_by_user_id=None,
        assigned_to_user_id=None,
        due_date=None,
        target_closure_date=None,
        finding_id=other_tenant_finding.id,
    )
    db_session.commit()

    first_page = register_pagination.get_audit_register_paged(
        domain=quality_models.QMSDomain.AMO,
        limit=1,
        offset=0,
        db=db_session,
        current_user=user_a,
    )
    assert first_page.total == 3
    assert len(first_page.rows) == 1
    assert first_page.has_more is True
    assert first_page.car_linked_findings == 3
    assert first_page.open_car_count == 3
    assert first_page.rows[0].audit.amo_id == amo_a.id

    car_only = register_pagination.get_audit_register_paged(
        domain=quality_models.QMSDomain.AMO,
        only_with_cars=True,
        limit=25,
        offset=0,
        db=db_session,
        current_user=user_a,
    )
    assert car_only.total == 3
    assert {row.finding.id for row in car_only.rows} == {finding.id for finding in findings}

    searched = register_pagination.get_audit_register_paged(
        domain=quality_models.QMSDomain.AMO,
        search=car.car_number,
        limit=25,
        offset=0,
        db=db_session,
        current_user=user_a,
    )
    assert searched.total == 1
    assert searched.rows[0].finding.id == findings[0].id

    car_page = register_pagination.get_car_register_paged(
        program=quality_models.CARProgram.QUALITY,
        scope="all",
        search=None,
        assigned_to_user_id=None,
        due_soon_days=30,
        limit=1,
        offset=0,
        db=db_session,
        current_user=user_a,
    )
    assert car_page.total == 3
    assert len(car_page.items) == 1
    assert car_page.has_more is True
    assert car_page.summary.total == 3
    assert car_page.summary.overdue == 1

    exact_car = register_pagination.get_car_register_paged(
        program=quality_models.CARProgram.QUALITY,
        scope="all",
        car_id=second_car.id,
        search=None,
        assigned_to_user_id=None,
        due_soon_days=30,
        limit=25,
        offset=0,
        db=db_session,
        current_user=user_a,
    )
    assert exact_car.total == 1
    assert exact_car.items[0].id == second_car.id

    overdue = register_pagination.get_car_register_paged(
        program=quality_models.CARProgram.QUALITY,
        scope="overdue",
        search=None,
        assigned_to_user_id=None,
        due_soon_days=30,
        limit=25,
        offset=0,
        db=db_session,
        current_user=user_a,
    )
    assert overdue.total == 1
    assert overdue.items[0].id == car.id

    car_search = register_pagination.get_car_register_paged(
        program=quality_models.CARProgram.QUALITY,
        scope="all",
        search=third_car.car_number,
        assigned_to_user_id=None,
        due_soon_days=30,
        limit=25,
        offset=0,
        db=db_session,
        current_user=user_a,
    )
    assert car_search.total == 1
    assert car_search.items[0].id == third_car.id
