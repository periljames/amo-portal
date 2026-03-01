from __future__ import annotations

from io import BytesIO
from uuid import uuid4

from fastapi import UploadFile
from starlette.requests import Request

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.apps.quality import models as quality_models
import importlib
quality_router = importlib.import_module("amodb.apps.quality.router")
from amodb.apps.quality import schemas as quality_schemas


def _ensure_tables(db_session):
    quality_models.QMSPhysicalControlledCopy.__table__.create(bind=db_session.bind, checkfirst=True)
    quality_models.QMSCustodyLog.__table__.create(bind=db_session.bind, checkfirst=True)


def _request() -> Request:
    return Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1234)})


def _user(db_session, amo_id: str, role: account_models.AccountRole = account_models.AccountRole.QUALITY_MANAGER) -> account_models.User:
    user = account_models.User(
        amo_id=amo_id,
        email=f"qa-{uuid4()}@example.com",
        staff_code=f"QA-{uuid4().hex[:6]}",
        first_name="QA",
        last_name="User",
        full_name="QA User",
        hashed_password="hash",
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _doc(db_session):
    doc = quality_models.QMSDocument(
        domain=quality_models.QMSDomain.AMO,
        doc_type=quality_models.QMSDocType.MANUAL,
        doc_code=f"DOC-{uuid4().hex[:6]}",
        title="Hybrid DMS Doc",
    )
    db_session.add(doc)
    db_session.commit()
    return doc


def test_upload_revision_computes_sha_and_logs_event(db_session):
    _ensure_tables(db_session)
    amo = account_models.AMO(amo_code=f"AMO-{uuid4().hex[:6]}", name="AMO", login_slug=f"amo-{uuid4().hex[:6]}")
    db_session.add(amo)
    db_session.commit()
    user = _user(db_session, amo.id)
    doc = _doc(db_session)

    upload = UploadFile(filename="manual.txt", file=BytesIO(b"controlled copy content"), headers={"content-type": "text/plain"})

    out = quality_router.upload_doc_revision(
        doc_id=doc.id,
        issue_no=1,
        rev_no=0,
        version_semver="1.0.0",
        request=_request(),
        file=upload,
        db=db_session,
        current_user=user,
    )

    rev = db_session.query(quality_models.QMSDocumentRevision).filter_by(id=out.revision_id).first()
    assert rev is not None
    assert rev.sha256 and len(rev.sha256) == 64

    event = db_session.query(audit_models.AuditEvent).filter_by(entity_type="qms.document.revision", action="uploaded").first()
    assert event is not None


def test_verify_physical_copy_green_only_for_approved(db_session):
    _ensure_tables(db_session)
    amo = account_models.AMO(amo_code=f"AMO-{uuid4().hex[:6]}", name="AMO", login_slug=f"amo-{uuid4().hex[:6]}")
    db_session.add(amo)
    db_session.commit()
    user = _user(db_session, amo.id)
    doc = _doc(db_session)

    rev = quality_models.QMSDocumentRevision(
        document_id=doc.id,
        issue_no=1,
        rev_no=0,
        lifecycle_status=quality_models.QMSRevisionLifecycleStatus.APPROVED,
        version_semver="1.2.3",
    )
    db_session.add(rev)
    db_session.flush()

    copy = quality_models.QMSPhysicalControlledCopy(
        amo_id=amo.id,
        digital_revision_id=rev.id,
        copy_serial_number="OPS-MAN-001-COPY-001",
    )
    db_session.add(copy)
    db_session.commit()

    out = quality_router.verify_physical_copy(copy.copy_serial_number, db=db_session, current_user=user)
    assert out.status == "GREEN"

    copy.voided_at = rev.created_at
    db_session.commit()

    out_red = quality_router.verify_physical_copy(copy.copy_serial_number, db=db_session, current_user=user)
    assert out_red.status == "RED"


def test_damage_workflow_voids_old_and_replaces(db_session):
    _ensure_tables(db_session)
    amo = account_models.AMO(amo_code=f"AMO-{uuid4().hex[:6]}", name="AMO", login_slug=f"amo-{uuid4().hex[:6]}")
    db_session.add(amo)
    db_session.commit()
    user = _user(db_session, amo.id)
    doc = _doc(db_session)

    rev = quality_models.QMSDocumentRevision(document_id=doc.id, issue_no=1, rev_no=0)
    db_session.add(rev)
    db_session.flush()

    copy = quality_models.QMSPhysicalControlledCopy(amo_id=amo.id, digital_revision_id=rev.id, copy_serial_number="OPS-MAN-001-COPY-002")
    db_session.add(copy)
    db_session.commit()

    out = quality_router.report_damage(
        copy_id=copy.id,
        payload=quality_schemas.QMSDamageReportRequest(notes="teared"),
        request=_request(),
        db=db_session,
        current_user=user,
    )

    db_session.refresh(copy)
    replacement = db_session.query(quality_models.QMSPhysicalControlledCopy).filter_by(id=out.new_copy_id).first()
    assert copy.voided_at is not None
    assert str(copy.replaced_by_copy_id) == str(out.new_copy_id)
    assert replacement is not None



def test_verify_physical_copy_is_tenant_scoped(db_session):
    _ensure_tables(db_session)
    amo_a = account_models.AMO(amo_code=f"AMO-{uuid4().hex[:6]}", name="AMO A", login_slug=f"amo-{uuid4().hex[:6]}")
    amo_b = account_models.AMO(amo_code=f"AMO-{uuid4().hex[:6]}", name="AMO B", login_slug=f"amo-{uuid4().hex[:6]}")
    db_session.add_all([amo_a, amo_b])
    db_session.commit()

    user_b = _user(db_session, amo_b.id)
    doc = _doc(db_session)
    rev = quality_models.QMSDocumentRevision(
        document_id=doc.id,
        issue_no=1,
        rev_no=0,
        lifecycle_status=quality_models.QMSRevisionLifecycleStatus.APPROVED,
        version_semver="2.0.0",
    )
    db_session.add(rev)
    db_session.flush()

    copy_a = quality_models.QMSPhysicalControlledCopy(
        amo_id=amo_a.id,
        digital_revision_id=rev.id,
        copy_serial_number="OPS-MAN-001-COPY-TENANT-A",
    )
    db_session.add(copy_a)
    db_session.commit()

    out = quality_router.verify_physical_copy(copy_a.copy_serial_number, db=db_session, current_user=user_b)
    assert out.status == "RED"



def test_report_damage_rejects_cross_tenant_access(db_session):
    _ensure_tables(db_session)
    amo_a = account_models.AMO(amo_code=f"AMO-{uuid4().hex[:6]}", name="AMO A", login_slug=f"amo-{uuid4().hex[:6]}")
    amo_b = account_models.AMO(amo_code=f"AMO-{uuid4().hex[:6]}", name="AMO B", login_slug=f"amo-{uuid4().hex[:6]}")
    db_session.add_all([amo_a, amo_b])
    db_session.commit()

    user_b = _user(db_session, amo_b.id)
    doc = _doc(db_session)
    rev = quality_models.QMSDocumentRevision(document_id=doc.id, issue_no=1, rev_no=0)
    db_session.add(rev)
    db_session.flush()

    copy_a = quality_models.QMSPhysicalControlledCopy(
        amo_id=amo_a.id,
        digital_revision_id=rev.id,
        copy_serial_number="OPS-MAN-001-COPY-DAMAGE-A",
    )
    db_session.add(copy_a)
    db_session.commit()

    from fastapi import HTTPException

    try:
        quality_router.report_damage(
            copy_id=copy_a.id,
            payload=quality_schemas.QMSDamageReportRequest(notes="should block"),
            request=_request(),
            db=db_session,
            current_user=user_b,
        )
        assert False, "expected tenant scope block"
    except HTTPException as exc:
        assert exc.status_code == 404



def test_upload_revision_requires_control_role(db_session):
    _ensure_tables(db_session)
    amo = account_models.AMO(amo_code=f"AMO-{uuid4().hex[:6]}", name="AMO", login_slug=f"amo-{uuid4().hex[:6]}")
    db_session.add(amo)
    db_session.commit()
    viewer = _user(db_session, amo.id, role=account_models.AccountRole.VIEW_ONLY)
    doc = _doc(db_session)
    upload = UploadFile(filename="manual.txt", file=BytesIO(b"viewer cannot upload"), headers={"content-type": "text/plain"})

    from fastapi import HTTPException

    try:
        quality_router.upload_doc_revision(
            doc_id=doc.id,
            issue_no=1,
            rev_no=0,
            version_semver="1.0.0",
            request=_request(),
            file=upload,
            db=db_session,
            current_user=viewer,
        )
        assert False, "expected role gate"
    except HTTPException as exc:
        assert exc.status_code == 403



def test_request_physical_copy_requires_control_role(db_session):
    _ensure_tables(db_session)
    amo = account_models.AMO(amo_code=f"AMO-{uuid4().hex[:6]}", name="AMO", login_slug=f"amo-{uuid4().hex[:6]}")
    db_session.add(amo)
    db_session.commit()
    viewer = _user(db_session, amo.id, role=account_models.AccountRole.VIEW_ONLY)
    doc = _doc(db_session)
    rev = quality_models.QMSDocumentRevision(document_id=doc.id, issue_no=1, rev_no=0)
    db_session.add(rev)
    db_session.commit()

    from fastapi import HTTPException

    try:
        quality_router.request_physical_copy(
            payload=quality_schemas.QMSPhysicalCopyRequest(revision_id=rev.id, count=1, base_serial="OPS-MAN-001"),
            request=_request(),
            db=db_session,
            current_user=viewer,
        )
        assert False, "expected role gate"
    except HTTPException as exc:
        assert exc.status_code == 403
