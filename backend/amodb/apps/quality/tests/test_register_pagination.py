from __future__ import annotations

from datetime import datetime

from amodb.apps.accounts import models as account_models
from amodb.apps.quality import models as quality_models
from amodb.apps.quality import register_pagination
from amodb.apps.quality import service as quality_service


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


def _car(db_session, *, amo_id: str, requested_by_user_id: str, title: str):
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
        finding_id=None,
    )
    car.status = quality_models.CARStatus.IN_PROGRESS
    car.submitted_at = datetime.utcnow()
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

    root_cause_return = _car(
        db_session,
        amo_id=amo.id,
        requested_by_user_id=user.id,
        title="Root cause returned",
    )
    root_cause_return.root_cause_status = "REJECTED"

    evidence_return = _car(
        db_session,
        amo_id=amo.id,
        requested_by_user_id=user.id,
        title="Evidence requested",
    )
    evidence_return.capa_status = "NEEDS_EVIDENCE"

    accepted_submission = _car(
        db_session,
        amo_id=amo.id,
        requested_by_user_id=user.id,
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
