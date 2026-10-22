from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from amodb.apps.accounts import models as accounts
from amodb.apps.quality import models, register_pagination
from amodb.apps.quality import people_authorization_router as people
from amodb.apps.quality.people_models import QualityPrivilegeRule, QualityPrivilege
from amodb.apps.quality.people_authorization_models import QualityAuthorizationCase, QualityAuthorizationCaseEvent
from amodb.apps.quality.tenant_security import TenantContext
from amodb.apps.training import models as training
from amodb.apps.notifications.models import EmailLog
from amodb.apps.quality.tests.test_register_pagination import _user, _finding, _car


@pytest.fixture()
def authorization_context(db_session):
    # All mutations here are confined to the harness's in-memory SQLite database.
    for table in [training.TrainingCourse.__table__, training.TrainingEvent.__table__, training.TrainingRecord.__table__]:
        table.create(db_session.get_bind(), checkfirst=True)
    amo = accounts.AMO(amo_code="VERIFY", name="Isolated assurance tests", login_slug="verify")
    db_session.add(amo); db_session.commit()
    actor = _user(db_session, amo_id=amo.id)
    subject = accounts.User(amo_id=amo.id, email="subject@example.test", staff_code="VERIFY-02", first_name="Test", last_name="Subject", full_name="Test Subject", hashed_password="test", role=accounts.AccountRole.AMO_ADMIN, is_active=True)
    rule = QualityPrivilegeRule(amo_id=amo.id, privilege_code="TEST_INSPECTION", title="Isolated test inspection", privilege_type="CUSTOM", required_training_course_codes=[], scope_schema={}, is_active=True)
    db_session.add_all([subject, rule]); db_session.commit()
    ctx = TenantContext(amo_code=amo.amo_code, amo_id=amo.id, user_id=actor.id, is_superuser=False, admin_authority=True)
    return ctx, subject, rule


def test_observations_are_separate_from_rca_and_close_independently(db_session):
    amo = accounts.AMO(amo_code="OBS", name="Observation stages", login_slug="obs")
    db_session.add(amo); db_session.commit()
    actor = _user(db_session, amo_id=amo.id)
    finding = _finding(db_session, amo_id=amo.id)
    finding.finding_type = models.QMSFindingType.OBSERVATION
    finding.level = models.FindingLevel.LEVEL_4
    db_session.commit()
    def read(stage):
        return register_pagination.get_audit_register_paged(domain=None, period=None, workflow_stage=stage, limit=25, offset=0, db=db_session, current_user=actor)
    assert read("observation").total == 1
    assert read("needs_review").total == 0
    from datetime import datetime, timezone
    finding.closed_at = datetime.now(timezone.utc); db_session.commit()
    assert read("closed").total == 1
    assert read("observation").total == 0


def test_finding_due_filters_honor_the_agreed_target_date(db_session):
    amo = accounts.AMO(amo_code="DUE", name="Due dates", login_slug="due")
    db_session.add(amo); db_session.commit()
    actor = _user(db_session, amo_id=amo.id)
    finding = _finding(db_session, amo_id=amo.id)
    car = _car(db_session, amo_id=amo.id, requested_by_user_id=actor.id, finding_id=finding.id, title="Agreed target")
    car.due_date = date.today() - timedelta(days=4)
    car.target_closure_date = date.today() + timedelta(days=4)
    db_session.commit()
    overdue = register_pagination.get_audit_register_paged(domain=None, period=None, car_timing="overdue", limit=25, offset=0, db=db_session, current_user=actor)
    assert overdue.total == 0


def test_authorization_register_paging_is_complete(db_session, authorization_context):
    ctx, subject, rule = authorization_context
    first = people.authorization_people(search=None, include_inactive=False, limit=1, offset=0, ctx=ctx, db=db_session)
    second = people.authorization_people(search=None, include_inactive=False, limit=1, offset=1, ctx=ctx, db=db_session)
    assert first["total"] == second["total"] == 2
    assert first["has_more"] and not second["has_more"]
    assert first["items"][0]["key"] != second["items"][0]["key"]


def test_authorization_requires_preparation_then_retains_decision_review_and_lifecycle(db_session, authorization_context):
    ctx, subject, rule = authorization_context
    created = people.create_authorization_case(people.AuthorizationCaseCreate(user_id=subject.id, requested_rule_id=rule.id, nomination_reason="Isolated workflow verification"), ctx=ctx, db=db_session)
    case_id = created["case"]["id"]
    approval = people.AuthorizationCaseDecisionCreate(decision="APPROVE", reason="Evidence reviewed in isolated test", effective_from=date.today(), expires_on=date.today()+timedelta(days=180), next_review_due=date.today()+timedelta(days=90), confirmed=True)
    with pytest.raises(HTTPException) as blocked:
        people.decide_authorization_case(case_id, approval, ctx=ctx, db=db_session)
    assert blocked.value.status_code == 409
    people.prepare_authorization_case(case_id, people.AuthorizationCasePrepare(status="UNDER_REVIEW", recommendation="Recommend the isolated test authorization", reason="Read source-backed readiness and scope"), ctx=ctx, db=db_session)
    people.add_case_evidence_reference(case_id, people.EvidenceReferenceCreate(evidence_type="OTHER", label="Isolated verification evidence", source_module="TEST", source_reference={"reference":"TEST-ONLY"}), ctx=ctx, db=db_session)
    submitted = people.submit_authorization_case(case_id, people.AuthorizationCaseSubmit(recommendation="Recommend the isolated test authorization", reason="Prepared evidence reviewed before decision"), ctx=ctx, db=db_session)
    assert submitted["status"] == "READY_FOR_DECISION"
    returned = people.decide_authorization_case(case_id, people.AuthorizationCaseDecisionCreate(decision="RETURN", reason="Request clearer evidence in isolated test", confirmed=True), ctx=ctx, db=db_session)
    assert returned["status"] == "RETURNED"
    people.prepare_authorization_case(case_id, people.AuthorizationCasePrepare(status="UNDER_REVIEW", recommendation="Clarified evidence reviewed", reason="Complete the returned preparation"), ctx=ctx, db=db_session)
    people.submit_authorization_case(case_id, people.AuthorizationCaseSubmit(recommendation="Recommend after evidence clarification", reason="Evidence clarification complete"), ctx=ctx, db=db_session)
    approved = people.decide_authorization_case(case_id, approval, ctx=ctx, db=db_session)
    assert approved["status"] == "APPROVED"
    privilege = db_session.query(QualityPrivilege).filter_by(user_id=subject.id, rule_id=rule.id).one()
    assert privilege.status == "ACTIVE"
    reviewed = people.create_authorization_review(privilege.id, people.AuthorizationReviewCreate(review_outcome="CONTINUE", review_reason="Periodic verification in isolated test", next_review_due=date.today()+timedelta(days=60), review_evidence=[{"reference":"TEST-ONLY"}], confirmed=True), ctx=ctx, db=db_session)
    assert reviewed
    people.authorization_lifecycle_decision(privilege.id, people.LifecycleDecisionCreate(decision="SUSPEND", reason="Isolated lifecycle verification only", effective_date=date.today(), confirmed=True), ctx=ctx, db=db_session)
    db_session.refresh(privilege)
    assert privilege.status == "SUSPENDED"
    people.authorization_lifecycle_decision(privilege.id, people.LifecycleDecisionCreate(decision="REINSTATE", reason="Readiness verified before reinstatement", effective_date=date.today(), confirmed=True), ctx=ctx, db=db_session)
    db_session.refresh(privilege)
    assert privilege.status == "ACTIVE"
    people.authorization_lifecycle_decision(privilege.id, people.LifecycleDecisionCreate(decision="RENEW", reason="Readiness verified before renewal", effective_date=date.today(), expires_on=date.today()+timedelta(days=240), confirmed=True), ctx=ctx, db=db_session)
    db_session.refresh(privilege)
    assert privilege.expires_on == date.today()+timedelta(days=240)
    people.authorization_lifecycle_decision(privilege.id, people.LifecycleDecisionCreate(decision="REVOKE", reason="Revoke isolated verification privilege", effective_date=date.today(), confirmed=True), ctx=ctx, db=db_session)
    db_session.refresh(privilege)
    assert privilege.status == "REVOKED"
    assert db_session.query(QualityAuthorizationCaseEvent).filter_by(case_id=case_id).count() >= 4
    assert db_session.query(EmailLog).count() == 0


def test_cancelled_nomination_is_retained_without_issuing_authority(db_session, authorization_context):
    ctx, subject, rule = authorization_context
    created = people.create_authorization_case(people.AuthorizationCaseCreate(user_id=subject.id, requested_rule_id=rule.id, nomination_reason="Isolated cancellation verification"), ctx=ctx, db=db_session)
    case_id = created["case"]["id"]
    cancelled = people.decide_authorization_case(case_id, people.AuthorizationCaseDecisionCreate(decision="CANCEL", reason="Cancel isolated test nomination without issuing authority", confirmed=True), ctx=ctx, db=db_session)
    assert cancelled["status"] == "CANCELLED"
    assert db_session.query(QualityAuthorizationCase).filter_by(id=case_id).one().status == "CANCELLED"
    assert db_session.query(QualityPrivilege).filter_by(user_id=subject.id).count() == 0
    assert db_session.query(QualityAuthorizationCaseEvent).filter_by(case_id=case_id, action="CANCELLED").count() == 1
    assert db_session.query(EmailLog).count() == 0


def test_case_lock_excludes_nullable_joined_rule_on_postgresql(db_session, authorization_context):
    from sqlalchemy import event
    from sqlalchemy.dialects import postgresql
    ctx, subject, rule = authorization_context
    created = people.create_authorization_case(people.AuthorizationCaseCreate(user_id=subject.id, requested_rule_id=rule.id, nomination_reason="Verify PostgreSQL lock scope"), ctx=ctx, db=db_session)
    statements = []
    def capture(state):
        if state.statement._for_update_arg is not None:
            statements.append(str(state.statement.compile(dialect=postgresql.dialect())))
    event.listen(db_session, "do_orm_execute", capture)
    try:
        people._case(db_session, amo_id=ctx.amo_id, case_id=created["case"]["id"], lock=True)
    finally:
        event.remove(db_session, "do_orm_execute", capture)
    assert len(statements) == 1
    assert "FOR UPDATE OF quality_authorization_cases" in statements[0]
    assert statements[0].rstrip().endswith("FOR UPDATE OF quality_authorization_cases")
