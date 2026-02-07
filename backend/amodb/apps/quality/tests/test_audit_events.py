from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from starlette.requests import Request

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.apps.quality import models as quality_models
import importlib
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
        domain=quality_models.QMSDomain.AMO,
        doc_type=quality_models.QMSDocType.MANUAL,
        doc_code="DOC-1",
        title="Test Manual",
    )
    db_session.add(doc)
    db_session.commit()

    rev = quality_models.QMSDocumentRevision(
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
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref="AUD-1",
        title="Audit 1",
    )
    db_session.add(audit)
    db_session.commit()

    finding = quality_models.QMSAuditFinding(
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
