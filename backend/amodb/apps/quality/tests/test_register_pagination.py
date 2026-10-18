from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID
import pytest

from amodb.apps.accounts import models as account_models
from amodb.apps.quality import models as quality_models
from amodb.apps.quality import register_pagination
from amodb.apps.quality import service as quality_service


def test_canonical_finding_register_read_owns_paged_url():
    from amodb.apps.quality import car_operational_route_order  # noqa: F401
    from amodb.apps.quality.canonical_router import router
    from starlette.routing import Match
    scope={"type":"http","method":"GET","path":"/api/maintenance/AMO/quality/audits/register/paged","root_path":""}
    matched=next(route for route in router.routes if route.matches(scope)[0] == Match.FULL)
    assert matched.endpoint is register_pagination.get_audit_register_paged


@pytest.mark.parametrize("status,rc,cap,expected", [
    ("OPEN", "SUBMITTED", "PENDING", "needs_review"),
    ("PENDING_VERIFICATION", "SUBMITTED", "SUBMITTED", "needs_review"),
    ("IN_PROGRESS", "REJECTED", "ACCEPTED", "with_auditee"),
    ("IN_PROGRESS", "ACCEPTED", "ACCEPTED", "implementation"),
    ("PENDING_VERIFICATION", "ACCEPTED", "ACCEPTED", "effectiveness"),
    ("CLOSED", "ACCEPTED", "ACCEPTED", "effectiveness"),
])
def test_finding_queues_follow_review_state_not_just_car_status(db_session, status, rc, cap, expected):
    amo = account_models.AMO(amo_code="STAGE", name="Stages", login_slug="stages")
    db_session.add(amo)
    db_session.commit()
    user = _user(db_session, amo_id=amo.id)
    finding = _finding(db_session, amo_id=amo.id)
    car = _car(db_session, amo_id=amo.id, requested_by_user_id=user.id, finding_id=finding.id, title="Stage test")
    car.status = quality_models.CARStatus(status)
    car.root_cause_status, car.capa_status = rc, cap
    car.assigned_to_user_id = user.id
    db_session.commit()
    for stage in ["needs_review", "with_auditee", "implementation", "effectiveness", "closed"]:
        result = register_pagination.get_audit_register_paged(domain=None, period=None,
            workflow_stage=stage, limit=25, offset=0, db=db_session, current_user=user)
        assert result.total == (1 if stage == expected else 0), stage
        if result.rows:
            assert result.rows[0].linked_cars[0].responsible_personnel == user.full_name
    if status == "PENDING_VERIFICATION":
        result = register_pagination.get_car_register_paged(program=None, scope="awaiting_effectiveness_review",
            limit=25, offset=0, db=db_session, current_user=user)
        assert result.total == (1 if expected == "effectiveness" else 0)


def _user(db_session, *, amo_id: str) -> account_models.User:
    user = account_models.User(
        amo_id=amo_id,
        email="auditee-queue@example.com",
        staff_code="QA-QUEUE",
        first_name="Quality",
        last_name="Queue",
        full_name="Quality Queue",
        hashed_password="hash",
        role=account_models.AccountRole.AMO_ADMIN,
        is_active=True,
        is_amo_admin=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _finding(db_session, *, amo_id: str) -> quality_models.QMSAuditFinding:
    audit = quality_models.QMSAudit(
        amo_id=amo_id,
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref="QAR/QUEUE/26/001",
        title="Returned CAR queue audit",
    )
    db_session.add(audit)
    db_session.commit()

    finding = quality_models.QMSAuditFinding(
        amo_id=amo_id,
        audit_id=audit.id,
        finding_ref="QAR/QUEUE/26/001-F-001",
        finding_type=quality_models.QMSFindingType.NON_CONFORMITY,
        severity=quality_models.QMSFindingSeverity.MINOR,
        level=quality_models.FindingLevel.LEVEL_3,
        description="Controlled finding used to exercise CAR queue lifecycle semantics.",
    )
    db_session.add(finding)
    db_session.commit()
    return finding


def _car(
    db_session,
    *,
    amo_id: str,
    requested_by_user_id: str,
    finding_id: UUID,
    title: str,
):
    car = quality_service.create_car(
        db_session,
        amo_id=amo_id,
        program=quality_models.CARProgram.QUALITY,
        title=title,
        summary=f"{title} summary",
        priority=quality_models.CARPriority.MEDIUM,
        requested_by_user_id=requested_by_user_id,
        assigned_to_user_id=None,
        due_date=None,
        target_closure_date=None,
        finding_id=finding_id,
    )
    car.status = quality_models.CARStatus.IN_PROGRESS
    car.submitted_at = datetime.now(timezone.utc)
    db_session.commit()
    return car


def test_returned_car_stays_in_awaiting_auditee_queue(db_session):
    amo = account_models.AMO(
        amo_code="AMO-QUEUE",
        name="Queue AMO",
        login_slug="queue-amo",
    )
    db_session.add(amo)
    db_session.commit()
    user = _user(db_session, amo_id=amo.id)
    finding = _finding(db_session, amo_id=amo.id)

    root_cause_return = _car(
        db_session,
        amo_id=amo.id,
        requested_by_user_id=user.id,
        finding_id=finding.id,
        title="Root cause returned",
    )
    root_cause_return.root_cause_status = "REJECTED"

    evidence_return = _car(
        db_session,
        amo_id=amo.id,
        requested_by_user_id=user.id,
        finding_id=finding.id,
        title="Evidence requested",
    )
    evidence_return.capa_status = "NEEDS_EVIDENCE"

    accepted_submission = _car(
        db_session,
        amo_id=amo.id,
        requested_by_user_id=user.id,
        finding_id=finding.id,
        title="Already submitted",
    )
    accepted_submission.root_cause_status = "ACCEPTED"
    accepted_submission.capa_status = "ACCEPTED"
    db_session.commit()

    result = register_pagination.get_car_register_paged(
        program=quality_models.CARProgram.QUALITY,
        status_=None,
        scope="awaiting_auditee",
        car_id=None,
        assigned_to_user_id=None,
        audit_id=None,
        search=None,
        due_soon_days=30,
        limit=25,
        offset=0,
        db=db_session,
        current_user=user,
    )

    returned_ids = {item.id for item in result.items}
    assert root_cause_return.id in returned_ids
    assert evidence_return.id in returned_ids
    assert accepted_submission.id not in returned_ids
    assert result.total == 2


def test_foreign_tenant_car_link_does_not_enter_audit_register(db_session):
    tenant = account_models.AMO(
        amo_code="AMO-ISO-A",
        name="Isolation A",
        login_slug="isolation-a",
    )
    foreign_tenant = account_models.AMO(
        amo_code="AMO-ISO-B",
        name="Isolation B",
        login_slug="isolation-b",
    )
    db_session.add_all([tenant, foreign_tenant])
    db_session.commit()

    user = _user(db_session, amo_id=tenant.id)
    finding = _finding(db_session, amo_id=tenant.id)
    foreign_car = quality_service.create_car(
        db_session,
        amo_id=foreign_tenant.id,
        program=quality_models.CARProgram.QUALITY,
        title="Foreign tenant CAR",
        summary="Deliberately corrupted cross-tenant relationship for read-isolation testing.",
        priority=quality_models.CARPriority.HIGH,
        requested_by_user_id=user.id,
        assigned_to_user_id=None,
        due_date=None,
        target_closure_date=None,
        finding_id=finding.id,
    )
    db_session.commit()

    car_only = register_pagination.get_audit_register_paged(
        domain=quality_models.QMSDomain.AMO,
        period=None,
        only_with_cars=True,
        limit=25,
        offset=0,
        db=db_session,
        current_user=user,
    )
    assert car_only.total == 0
    assert car_only.rows == []
    assert car_only.car_linked_findings == 0
    assert car_only.open_car_count == 0

    searched = register_pagination.get_audit_register_paged(
        domain=quality_models.QMSDomain.AMO,
        period=None,
        search=foreign_car.car_number,
        limit=25,
        offset=0,
        db=db_session,
        current_user=user,
    )
    assert searched.total == 0
    assert searched.rows == []
