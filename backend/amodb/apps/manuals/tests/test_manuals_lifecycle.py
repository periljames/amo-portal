from __future__ import annotations

from datetime import date

from fastapi import HTTPException

from amodb.apps.accounts.models import AMO, User, AccountRole
from amodb.apps.manuals import models
import importlib
manuals_router = importlib.import_module("amodb.apps.manuals.router")


def _seed(db_session):
    amo = AMO(amo_code="AMO-LIFE", name="Lifecycle", login_slug="life")
    user = User(
        amo=amo,
        staff_code="S100",
        email="lifecycle@example.com",
        first_name="Life",
        last_name="Cycle",
        full_name="Life Cycle",
        role=AccountRole.AMO_ADMIN,
        hashed_password="x",
    )
    db_session.add_all([amo, user])
    db_session.commit()

    tenant = models.Tenant(amo_id=amo.id, slug="life", name="Lifecycle", settings_json={"ack_due_days": 10})
    db_session.add(tenant)
    db_session.flush()

    manual = models.Manual(tenant_id=tenant.id, code="MOM", title="Manual", manual_type="MOM", owner_role="Doc Control")
    db_session.add(manual)
    db_session.flush()

    rev = models.ManualRevision(
        manual_id=manual.id,
        rev_number="1",
        effective_date=date.today(),
        created_by=user.id,
        status_enum=models.ManualRevisionStatus.DRAFT,
    )
    db_session.add(rev)
    db_session.commit()
    return tenant, manual, rev, user


def test_lifecycle_state_machine_happy_path(db_session):
    tenant, manual, rev, user = _seed(db_session)

    prev, reset = manuals_router._apply_lifecycle_transition(
        rev=rev,
        manual=manual,
        tenant=tenant,
        action="submit_for_review",
        actor_id=user.id,
        db=db_session,
    )
    assert prev == models.ManualRevisionStatus.DRAFT
    assert reset is False
    assert rev.status_enum == models.ManualRevisionStatus.DEPARTMENT_REVIEW

    manuals_router._apply_lifecycle_transition(rev=rev, manual=manual, tenant=tenant, action="verify_compliance", actor_id=user.id, db=db_session)
    assert rev.status_enum == models.ManualRevisionStatus.QUALITY_APPROVAL

    manuals_router._apply_lifecycle_transition(rev=rev, manual=manual, tenant=tenant, action="sign_approval", actor_id=user.id, db=db_session)
    assert rev.status_enum == models.ManualRevisionStatus.REGULATOR_SIGNOFF
    assert rev.authority_approval_ref

    manuals_router._apply_lifecycle_transition(rev=rev, manual=manual, tenant=tenant, action="publish", actor_id=user.id, db=db_session)
    assert rev.status_enum == models.ManualRevisionStatus.PUBLISHED
    assert rev.immutable_locked is True


def test_reject_resets_chain_back_to_draft(db_session):
    tenant, manual, rev, user = _seed(db_session)
    rev.status_enum = models.ManualRevisionStatus.QUALITY_APPROVAL
    rev.authority_approval_ref = "signed"
    rev.immutable_locked = True

    prev, reset = manuals_router._apply_lifecycle_transition(
        rev=rev,
        manual=manual,
        tenant=tenant,
        action="reject_to_draft",
        actor_id=user.id,
        db=db_session,
    )
    assert prev == models.ManualRevisionStatus.QUALITY_APPROVAL
    assert reset is True
    assert rev.status_enum == models.ManualRevisionStatus.DRAFT
    assert rev.authority_approval_ref is None
    assert rev.immutable_locked is False


def test_reject_from_draft_fails(db_session):
    tenant, manual, rev, user = _seed(db_session)

    try:
        manuals_router._apply_lifecycle_transition(
            rev=rev,
            manual=manual,
            tenant=tenant,
            action="reject_to_draft",
            actor_id=user.id,
            db=db_session,
        )
        assert False, "expected error"
    except HTTPException as exc:
        assert exc.status_code == 400
