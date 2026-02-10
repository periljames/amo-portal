from __future__ import annotations

from datetime import datetime, timezone

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import router_admin
from amodb.apps.accounts import schemas as account_schemas
from amodb.apps.audit import models as audit_models


def _create_amo(db_session, code: str = "AMO1") -> account_models.AMO:
    amo = account_models.AMO(amo_code=code, name=f"{code} Name", login_slug=code.lower(), is_active=True)
    db_session.add(amo)
    db_session.commit()
    db_session.refresh(amo)
    return amo


def _create_user(
    db_session,
    *,
    amo_id: str,
    email: str,
    is_admin: bool = False,
    is_superuser: bool = False,
) -> account_models.User:
    role = account_models.AccountRole.SUPERUSER if is_superuser else account_models.AccountRole.AMO_ADMIN if is_admin else account_models.AccountRole.TECHNICIAN
    user = account_models.User(
        amo_id=amo_id,
        staff_code=email.split("@")[0].upper(),
        email=email,
        first_name="First",
        last_name="Last",
        full_name="First Last",
        role=role,
        hashed_password="hashed",
        is_active=True,
        is_amo_admin=is_admin,
        is_superuser=is_superuser,
        must_change_password=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_force_password_reset_sets_flags_and_emits_audit_event(db_session):
    amo = _create_amo(db_session)
    admin = _create_user(db_session, amo_id=amo.id, email="admin@example.com", is_admin=True)
    subject = _create_user(db_session, amo_id=amo.id, email="user@example.com")

    result = router_admin.command_force_password_reset(subject.id, db=db_session, current_user=admin)

    db_session.refresh(subject)
    assert result.command == "force-password-reset"
    assert subject.must_change_password is True
    assert subject.token_revoked_at is not None

    event = (
        db_session.query(audit_models.AuditEvent)
        .filter(audit_models.AuditEvent.entity_type == "accounts.user.command", audit_models.AuditEvent.entity_id == subject.id)
        .order_by(audit_models.AuditEvent.created_at.desc())
        .first()
    )
    assert event is not None
    assert event.action == "PASSWORD_RESET_FORCED"


def test_schedule_review_creates_task_and_emits_command_event(db_session):
    amo = _create_amo(db_session, code="AMO2")
    admin = _create_user(db_session, amo_id=amo.id, email="admin2@example.com", is_admin=True)
    subject = _create_user(db_session, amo_id=amo.id, email="crew@example.com")

    due_at = datetime.now(timezone.utc)
    payload = account_schemas.UserCommandSchedulePayload(
        title="Authorization review",
        description="Quarterly authorization check",
        due_at=due_at,
        priority=2,
    )

    result = router_admin.command_schedule_review(subject.id, payload=payload, db=db_session, current_user=admin)

    assert result.command == "schedule-review"
    assert result.task_id is not None

    task_event = (
        db_session.query(audit_models.AuditEvent)
        .filter(audit_models.AuditEvent.entity_type == "tasks.task", audit_models.AuditEvent.entity_id == result.task_id)
        .first()
    )
    assert task_event is not None

    command_event = (
        db_session.query(audit_models.AuditEvent)
        .filter(audit_models.AuditEvent.entity_type == "accounts.user.command", audit_models.AuditEvent.entity_id == subject.id)
        .order_by(audit_models.AuditEvent.created_at.desc())
        .first()
    )
    assert command_event is not None
    assert command_event.action == "REVIEW_SCHEDULED"
