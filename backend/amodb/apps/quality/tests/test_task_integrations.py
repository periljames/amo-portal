from __future__ import annotations

from datetime import date, datetime, timezone

from starlette.requests import Request

from amodb.apps.accounts import models as account_models
from amodb.apps.quality import models as quality_models
from amodb.apps.quality import schemas as quality_schemas
from amodb.apps.tasks import models as task_models
import importlib


quality_router = importlib.import_module("amodb.apps.quality.router")


def _make_request() -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(b"user-agent", b"pytest")],
            "client": ("127.0.0.1", 1234),
        }
    )


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


def test_finding_creation_creates_task(db_session):
    amo = account_models.AMO(amo_code="AMO-FIND-TASK", name="Find AMO", login_slug="find-task")
    db_session.add(amo)
    db_session.commit()
    user = _create_user(db_session, amo_id=amo.id)

    audit = quality_models.QMSAudit(
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref="AUD-301",
        title="Audit 301",
        lead_auditor_user_id=user.id,
    )
    db_session.add(audit)
    db_session.commit()

    payload = quality_schemas.QMSFindingCreate(
        description="Finding",
        severity=quality_models.QMSFindingSeverity.MINOR,
    )

    quality_router.add_finding(
        audit_id=audit.id,
        payload=payload,
        request=_make_request(),
        db=db_session,
        current_user=user,
    )

    task = (
        db_session.query(task_models.Task)
        .filter(task_models.Task.entity_type == "qms_finding")
        .first()
    )
    assert task is not None


def test_publish_revision_creates_ack_tasks(db_session):
    amo = account_models.AMO(amo_code="AMO-DOC-TASK", name="Doc AMO", login_slug="doc-task")
    db_session.add(amo)
    db_session.commit()
    user = _create_user(db_session, amo_id=amo.id)

    doc = quality_models.QMSDocument(
        domain=quality_models.QMSDomain.AMO,
        doc_type=quality_models.QMSDocType.MANUAL,
        doc_code="DOC-2",
        title="Manual",
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
        authority_ref="CAA-REF",
    )
    db_session.add(rev)
    db_session.commit()

    dist = quality_models.QMSDocumentDistribution(
        document_id=doc.id,
        revision_id=rev.id,
        holder_label="QA",
        holder_user_id=user.id,
        dist_format=quality_models.QMSDistributionFormat.SOFT_COPY,
        requires_ack=True,
    )
    db_session.add(dist)
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

    task = (
        db_session.query(task_models.Task)
        .filter(task_models.Task.entity_type == "qms_document_distribution")
        .first()
    )
    assert task is not None


def test_close_finding_completes_tasks(db_session):
    amo = account_models.AMO(amo_code="AMO-CLOSE-TASK", name="Close AMO", login_slug="close-task")
    db_session.add(amo)
    db_session.commit()
    user = _create_user(db_session, amo_id=amo.id)

    audit = quality_models.QMSAudit(
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref="AUD-302",
        title="Audit 302",
        lead_auditor_user_id=user.id,
    )
    db_session.add(audit)
    db_session.commit()

    finding = quality_models.QMSAuditFinding(
        audit_id=audit.id,
        description="Finding",
        severity=quality_models.QMSFindingSeverity.MINOR,
        level=quality_models.FindingLevel.LEVEL_3,
        objective_evidence="Evidence",
        verified_at=datetime.now(timezone.utc),
        verified_by_user_id=user.id,
    )
    db_session.add(finding)
    db_session.commit()

    task = task_models.Task(
        amo_id=amo.id,
        title="Respond to finding",
        status=task_models.TaskStatus.OPEN,
        owner_user_id=user.id,
        entity_type="qms_finding",
        entity_id=str(finding.id),
    )
    db_session.add(task)
    db_session.commit()

    quality_router.close_finding(
        finding_id=finding.id,
        request=_make_request(),
        db=db_session,
        current_user=user,
    )

    db_session.refresh(task)
    assert task.status == task_models.TaskStatus.DONE
    assert task.closed_at is not None
