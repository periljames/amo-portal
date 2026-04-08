from __future__ import annotations

import importlib
from datetime import date

import pytest
from starlette.requests import Request
from fastapi import HTTPException

from amodb.apps.accounts import models as account_models
from amodb.apps.notifications import models as notification_models, providers as notification_providers
from amodb.apps.quality import models as quality_models
from amodb.apps.quality import schemas as quality_schemas

quality_router = importlib.import_module("amodb.apps.quality.router")


def _req() -> Request:
    return Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1)})


def _user(db_session, amo_id: str, role: account_models.AccountRole) -> account_models.User:
    user = account_models.User(
        amo_id=amo_id,
        email=f"{role.value.lower()}@example.com",
        staff_code=role.value[:6],
        first_name="Test",
        last_name=role.value,
        full_name="Test User",
        hashed_password="x",
        role=role,
        is_active=True,
        is_amo_admin=role == account_models.AccountRole.AMO_ADMIN,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _seed_audit(db_session):
    amo = account_models.AMO(amo_code="AMO-WF", name="Workflow", login_slug="workflow")
    db_session.add(amo)
    db_session.commit()
    quality = _user(db_session, amo.id, account_models.AccountRole.QUALITY_MANAGER)
    tech = _user(db_session, amo.id, account_models.AccountRole.TECHNICIAN)
    audit = quality_models.QMSAudit(
        amo_id=amo.id,
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref="AUD-WF-1",
        title="Workflow Audit",
        lead_auditor_user_id=quality.id,
    )
    db_session.add(audit)
    db_session.commit()
    return amo, quality, tech, audit


def test_rbac_blocks_non_quality_audit_schedule_creation(db_session):
    _, _, tech, _ = _seed_audit(db_session)
    payload = quality_schemas.QMSAuditScheduleCreate(
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        frequency=quality_models.QMSAuditScheduleFrequency.MONTHLY,
        title="Monthly",
        duration_days=1,
        next_due_date=date.today(),
    )
    with pytest.raises(HTTPException) as exc:
        quality_router.create_audit_schedule(payload=payload, request=_req(), db=db_session, current_user=tech)
    assert exc.value.status_code == 403


def test_car_cannot_be_created_for_non_nc_finding(db_session):
    _, quality, _, audit = _seed_audit(db_session)
    finding = quality_models.QMSAuditFinding(
        audit_id=audit.id,
        description="Observation",
        finding_type=quality_models.QMSFindingType.OBSERVATION,
        severity=quality_models.QMSFindingSeverity.MINOR,
        level=quality_models.FindingLevel.LEVEL_3,
    )
    db_session.add(finding)
    db_session.commit()

    payload = quality_schemas.CARCreate(title="CAR", summary="S", finding_id=finding.id)
    with pytest.raises(HTTPException) as exc:
        quality_router.create_car_request(payload=payload, request=_req(), db=db_session, current_user=quality)
    assert exc.value.status_code == 400


def test_review_rejection_requires_reason_note(db_session):
    _, quality, _, audit = _seed_audit(db_session)
    finding = quality_models.QMSAuditFinding(
        audit_id=audit.id,
        description="NC",
        finding_type=quality_models.QMSFindingType.NON_CONFORMITY,
        severity=quality_models.QMSFindingSeverity.MAJOR,
        level=quality_models.FindingLevel.LEVEL_2,
    )
    db_session.add(finding)
    db_session.flush()
    car = quality_models.CorrectiveActionRequest(
        program=quality_models.CARProgram.QUALITY,
        car_number="Q-2026-0001",
        title="NC CAR",
        summary="Summary",
        status=quality_models.CARStatus.IN_PROGRESS,
        invite_token="tok1",
        finding_id=finding.id,
    )
    db_session.add(car)
    db_session.flush()
    response = quality_models.CARResponse(car_id=car.id, status=quality_models.CARResponseStatus.SUBMITTED)
    db_session.add(response)
    db_session.commit()

    payload = quality_schemas.CARReviewUpdate(root_cause_status="REJECTED")
    with pytest.raises(HTTPException) as exc:
        quality_router.review_car_response(car_id=car.id, payload=payload, request=_req(), db=db_session, current_user=quality)
    assert exc.value.status_code == 400


def test_evidence_required_blocks_invite_submission_without_attachment(db_session):
    _, _, _, audit = _seed_audit(db_session)
    finding = quality_models.QMSAuditFinding(
        audit_id=audit.id,
        description="NC",
        finding_type=quality_models.QMSFindingType.NON_CONFORMITY,
        severity=quality_models.QMSFindingSeverity.MAJOR,
        level=quality_models.FindingLevel.LEVEL_2,
    )
    db_session.add(finding)
    db_session.flush()
    car = quality_models.CorrectiveActionRequest(
        program=quality_models.CARProgram.QUALITY,
        car_number="Q-2026-0002",
        title="NC CAR",
        summary="Summary",
        status=quality_models.CARStatus.OPEN,
        invite_token="tok2",
        finding_id=finding.id,
        evidence_required=True,
    )
    db_session.add(car)
    db_session.commit()

    payload = quality_schemas.CARInviteUpdate(root_cause_text="Human factor", capa_text="Retraining")
    with pytest.raises(HTTPException) as exc:
        quality_router.submit_car_from_invite(invite_token="tok2", payload=payload, db=db_session)
    assert exc.value.status_code == 400


class _FakeProvider(notification_providers.EmailProvider):
    def __init__(self):
        self.sent = []

    def send(self, *, template_key: str, recipient: str, subject: str, context: dict, correlation_id: str | None) -> None:
        self.sent.append({
            "template_key": template_key,
            "recipient": recipient,
            "subject": subject,
            "context": context,
            "correlation_id": correlation_id,
        })


def test_schedule_creation_notifies_lead_auditor_and_auditee(db_session):
    amo, quality, _, _ = _seed_audit(db_session)
    lead = _user(db_session, amo.id, account_models.AccountRole.QUALITY_INSPECTOR)
    auditee = _user(db_session, amo.id, account_models.AccountRole.TECHNICIAN)
    payload = quality_schemas.QMSAuditScheduleCreate(
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        frequency=quality_models.QMSAuditScheduleFrequency.QUARTERLY,
        title="Quarterly Procurement Audit",
        duration_days=3,
        next_due_date=date.today(),
        lead_auditor_user_id=lead.id,
        auditee_user_id=auditee.id,
        auditee_email=auditee.email,
        auditee="Stores",
    )

    schedule = quality_router.create_audit_schedule(payload=payload, request=_req(), db=db_session, current_user=quality)
    lead_note = (
        db_session.query(quality_models.QMSNotification)
        .filter(quality_models.QMSNotification.user_id == lead.id)
        .order_by(quality_models.QMSNotification.created_at.desc())
        .first()
    )
    auditee_note = (
        db_session.query(quality_models.QMSNotification)
        .filter(quality_models.QMSNotification.user_id == auditee.id)
        .order_by(quality_models.QMSNotification.created_at.desc())
        .first()
    )

    assert schedule.lead_auditor_user_id == lead.id
    assert lead_note is not None
    assert "assigned as lead auditor" in lead_note.message
    assert "Quarterly Procurement Audit" in lead_note.message
    assert auditee_note is not None
    assert "listed as auditee" in auditee_note.message


def test_running_schedule_sends_notice_notification_and_email(db_session, monkeypatch):
    amo, quality, _, _ = _seed_audit(db_session)
    lead = _user(db_session, amo.id, account_models.AccountRole.QUALITY_INSPECTOR)
    auditee = _user(db_session, amo.id, account_models.AccountRole.TECHNICIAN)
    fake_provider = _FakeProvider()
    monkeypatch.setattr(notification_providers, "get_email_provider", lambda: (fake_provider, True))

    schedule = quality_models.QMSAuditSchedule(
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        frequency=quality_models.QMSAuditScheduleFrequency.MONTHLY,
        title="Hangar Readiness Audit",
        lead_auditor_user_id=lead.id,
        auditee_user_id=auditee.id,
        auditee_email=auditee.email,
        auditee="Hangar team",
        duration_days=2,
        next_due_date=date.today(),
        created_by_user_id=quality.id,
    )
    db_session.add(schedule)
    db_session.commit()

    audit = quality_router.run_audit_schedule(schedule_id=schedule.id, request=_req(), db=db_session, current_user=quality)

    lead_note = (
        db_session.query(quality_models.QMSNotification)
        .filter(quality_models.QMSNotification.user_id == lead.id)
        .order_by(quality_models.QMSNotification.created_at.desc())
        .first()
    )
    auditee_note = (
        db_session.query(quality_models.QMSNotification)
        .filter(quality_models.QMSNotification.user_id == auditee.id)
        .order_by(quality_models.QMSNotification.created_at.desc())
        .first()
    )
    email_logs = (
        db_session.query(notification_models.EmailLog)
        .filter(notification_models.EmailLog.template_key == "qms_audit_notice_memo")
        .order_by(notification_models.EmailLog.created_at.asc())
        .all()
    )
    recipients = {log.recipient for log in email_logs}

    assert audit.lead_auditor_user_id == lead.id
    assert lead_note is not None
    assert "Audit notice memo" in lead_note.message
    assert audit.audit_ref in lead_note.message
    assert auditee_note is not None
    assert "Audit notice memo issued to auditee" in auditee_note.message
    assert lead.email in recipients
    assert auditee.email in recipients
    assert {entry["recipient"] for entry in fake_provider.sent} >= {lead.email, auditee.email}
