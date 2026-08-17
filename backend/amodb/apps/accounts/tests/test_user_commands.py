from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

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
        is_amo_admin=is_admin or is_superuser,
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


def test_bulk_role_change_cannot_promote_tenant_user_to_platform_superuser(db_session):
    amo = _create_amo(db_session, code="AMO3")
    admin = _create_user(db_session, amo_id=amo.id, email="admin3@example.com", is_admin=True)
    subject = _create_user(db_session, amo_id=amo.id, email="tenant-user@example.com")

    with pytest.raises(HTTPException) as caught:
        router_admin.bulk_user_action(
            account_schemas.BulkUserActionRequest(
                user_ids=[subject.id],
                action="change_role",
                role=account_models.AccountRole.SUPERUSER,
            ),
            db=db_session,
            current_user=admin,
        )

    assert caught.value.status_code == 403
    db_session.refresh(subject)
    assert subject.role == account_models.AccountRole.TECHNICIAN
    assert subject.is_superuser is False


def test_bulk_superuser_role_reconciliation_preserves_platform_identity_flags(db_session):
    root = _create_amo(db_session, code="ROOT")
    platform_user = _create_user(
        db_session,
        amo_id=root.id,
        email="platform-bulk@example.com",
        is_superuser=True,
    )

    result = router_admin.bulk_user_action(
        account_schemas.BulkUserActionRequest(
            user_ids=[platform_user.id],
            action="change_role",
            role=account_models.AccountRole.SUPERUSER,
        ),
        db=db_session,
        current_user=platform_user,
    )

    db_session.refresh(platform_user)
    assert result.processed == 1
    assert platform_user.is_superuser is True
    assert platform_user.is_amo_admin is True


def test_admin_cannot_disable_current_signed_in_account(db_session):
    amo = _create_amo(db_session, code="AMO4")
    admin = _create_user(db_session, amo_id=amo.id, email="admin4@example.com", is_admin=True)

    with pytest.raises(HTTPException) as caught:
        router_admin.command_disable_user(admin.id, db=db_session, current_user=admin)

    assert caught.value.status_code == 400
    assert "current signed-in user" in str(caught.value.detail)


def test_platform_superuser_cannot_remove_tenants_last_admin(db_session):
    root = _create_amo(db_session, code="ROOT")
    tenant = _create_amo(db_session, code="AMO5")
    platform_user = _create_user(
        db_session,
        amo_id=root.id,
        email="platform@example.com",
        is_superuser=True,
    )
    tenant_admin = _create_user(
        db_session,
        amo_id=tenant.id,
        email="only-admin@example.com",
        is_admin=True,
    )

    with pytest.raises(HTTPException) as caught:
        router_admin.command_disable_user(
            tenant_admin.id,
            db=db_session,
            current_user=platform_user,
        )

    assert caught.value.status_code == 409
    assert "last administrator" in str(caught.value.detail)


def test_additional_superuser_creation_is_root_scoped_and_sets_identity_flag(db_session):
    root = _create_amo(db_session, code="ROOT")
    tenant = _create_amo(db_session, code="AMO6")
    platform_user = _create_user(
        db_session,
        amo_id=root.id,
        email="owner@example.com",
        is_superuser=True,
    )
    payload = account_schemas.UserCreate(
        amo_id=tenant.id,
        staff_code="PLAT2",
        email="owner2@example.com",
        first_name="Second",
        last_name="Owner",
        full_name="Second Owner",
        role=account_models.AccountRole.SUPERUSER,
        position_title="Platform Owner",
        password="StrongPlatform2!",
    )

    created = router_admin.create_user_admin(
        payload,
        db=db_session,
        current_user=platform_user,
    )

    assert created.amo_id == root.id
    assert created.role == account_models.AccountRole.SUPERUSER
    assert created.is_superuser is True
    assert created.is_amo_admin is True


def test_position_title_edit_cannot_silently_demote_an_administrator(db_session):
    root = _create_amo(db_session, code="ROOT-TITLE")
    platform_user = _create_user(
        db_session,
        amo_id=root.id,
        email="platform-title@example.com",
        is_superuser=True,
    )

    updated = router_admin.update_user_admin(
        platform_user.id,
        account_schemas.UserUpdate(position_title="Quality Manager"),
        db=db_session,
        current_user=platform_user,
    )

    assert updated.role == account_models.AccountRole.SUPERUSER
    assert updated.is_superuser is True
    assert updated.is_amo_admin is True
