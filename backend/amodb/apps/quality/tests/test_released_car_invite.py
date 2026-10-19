from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.database import Base
from amodb.apps.accounts import models as accounts
from amodb.apps.quality import models
from amodb.apps.quality import audit_car_invite as delivery
from amodb.apps.quality.audit_external_access_models import QualityAuditFindingReleaseEvent


@pytest.fixture
def released_car(db_session, monkeypatch):
    Base.metadata.create_all(db_session.get_bind(), tables=[QualityAuditFindingReleaseEvent.__table__])
    amo = accounts.AMO(amo_code="INVITE", login_slug="invite", name="Invite test")
    db_session.add(amo)
    db_session.flush()
    user = accounts.User(amo_id=amo.id, email="auditee@example.test", staff_code="E1",
        first_name="Test", last_name="Auditee", full_name="Test Auditee", position_title="Auditee",
        hashed_password="test", is_active=True, role=accounts.AccountRole.QUALITY_OFFICER)
    db_session.add(user)
    db_session.flush()
    audit = models.QMSAudit(amo_id=amo.id, domain=models.QMSDomain.AMO, audit_ref="QAR/TEST",
        title="Simulated test", auditee_user_id=user.id, auditee_email="other@example.test")
    db_session.add(audit)
    db_session.flush()
    finding = models.QMSAuditFinding(amo_id=amo.id, audit_id=audit.id, finding_ref="F-001",
        finding_type=models.QMSFindingType.NON_CONFORMITY, severity=models.QMSFindingSeverity.MAJOR,
        description="Released description", objective_evidence="Private evidence", requirement_ref="1.1")
    db_session.add(finding)
    db_session.flush()
    car = models.CorrectiveActionRequest(amo_id=amo.id, program=models.CARProgram.QUALITY,
        car_number="CAR/TEST", title="Test CAR", summary="Not the email projection",
        priority=models.CARPriority.HIGH, assigned_to_user_id=user.id, finding_id=finding.id,
        invite_token="isolated-test-token")
    release = QualityAuditFindingReleaseEvent(amo_id=amo.id, audit_id=audit.id,
        finding_id=finding.id, action="RELEASED", reason="Test", include_objective_evidence=False)
    db_session.add_all([car, release])
    db_session.commit()
    sends = []
    def send(**kwargs):
        sends.append(kwargs)
        return SimpleNamespace(status="SENT", provider_message_id="test-message")
    monkeypatch.setattr(delivery.notifications, "send_email", send)
    return SimpleNamespace(db=db_session, ctx=SimpleNamespace(amo_id=amo.id), audit=audit,
        finding=finding, car=car, release=release, user=user, sends=sends)


def deliver(case):
    return delivery.deliver_released_car_invite(case.db, ctx=case.ctx,
        audit_id=case.audit.id, finding_id=case.finding.id)


def test_email_uses_actual_assignee_and_released_projection(released_car):
    case = released_car
    result = deliver(case)
    assert result["sent"] is True
    sent = case.sends[0]
    assert sent["recipient"] == case.user.email
    assert "Private evidence" not in sent["context"]["summary"]
    assert sent["correlation_id"] == f"car-release:{case.car.id}:{case.release.id}"
    case.release.include_objective_evidence = True
    case.db.commit()
    deliver(case)
    assert "Private evidence" in case.sends[-1]["context"]["summary"]


@pytest.mark.parametrize("failure", ["withdrawn", "wrong_tenant", "no_car", "no_recipient"])
def test_unavailable_or_unreleased_car_is_not_emailed(released_car, failure):
    case = released_car
    if failure == "withdrawn":
        case.release.action = "WITHDRAWN"
    elif failure == "wrong_tenant":
        case.ctx.amo_id = "different-tenant"
    elif failure == "no_car":
        case.db.delete(case.car)
    else:
        case.car.assigned_to_user_id = None
        case.audit.auditee_email = None
    case.db.commit()
    with pytest.raises(HTTPException) as caught:
        deliver(case)
    assert caught.value.status_code in {404, 409}
    assert case.sends == []


def test_provider_failure_does_not_claim_delivery_or_withdraw_finding(released_car, monkeypatch):
    case = released_car
    monkeypatch.setattr(delivery.notifications, "send_email", lambda **kwargs: SimpleNamespace(
        status="FAILED", provider_message_id=None))
    result = deliver(case)
    assert result["sent"] is False
    assert case.release.action == "RELEASED"


def test_canonical_completion_retains_assigned_lead_gate(released_car, monkeypatch):
    from amodb.apps.quality import audit_checklist_execution_router as execution
    from amodb.apps.quality import audit_session_router as session
    from amodb.apps.quality.schemas import QualityFieldworkComplete

    case = released_car
    case.ctx.user_id = case.user.id
    case.user.role = accounts.AccountRole.AMO_ADMIN
    case.user.is_amo_admin = True
    monkeypatch.setattr(session, "set_postgres_tenant_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(execution, "_internal_fieldwork_viewer", lambda *args, **kwargs: (case.audit, case.user, None))
    with pytest.raises(HTTPException) as caught:
        session.complete_occurrence_fieldwork(case.audit.id, QualityFieldworkComplete(),
            SimpleNamespace(), ctx=case.ctx, db=case.db)
    assert caught.value.status_code == 403
    assert "lead auditor" in caught.value.detail
