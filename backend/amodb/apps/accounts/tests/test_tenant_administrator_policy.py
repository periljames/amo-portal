from datetime import datetime, timedelta, timezone
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import text

from amodb.apps.accounts import admin_profile_router as governance, models, router_admin
from amodb.apps.accounts.tenant_authority import (
    active_admin_profile_session, is_tenant_admin, is_standing_admin,
)
from amodb.apps.training.permissions import ALL_TRAINING_CAPABILITIES, training_capabilities_for
from amodb.apps.workforce.permissions import ALL_PERMISSIONS, has_permission, permissions_for_user
from amodb.apps.quality.tenant_security import _has_role_permission
from amodb.apps.doc_control.workspace_service import is_control_user, is_accountable_approver
from amodb.apps.doc_control.workspace_decision_policy import is_decision_approver
from amodb.apps.reliability.advanced_services import ALL_CAPABILITIES, capabilities_for_user
from amodb.security import get_current_active_user, require_admin, require_roles


def actor(**overrides):
    return SimpleNamespace(**{
        "id": "actor", "amo_id": "tenant-a", "effective_amo_id": "tenant-a",
        "is_active": True, "is_superuser": False, "is_amo_admin": True,
        "role": models.AccountRole.TECHNICIAN, **overrides,
    })


@pytest.mark.parametrize("delegated", [False, True])
def test_administrator_inherits_all_tenant_role_and_module_authority(delegated):
    user = actor(is_amo_admin=not delegated, _admin_profile_elevated=delegated)
    for role in models.AccountRole:
        if role == models.AccountRole.SUPERUSER:
            with pytest.raises(HTTPException):
                require_roles(role)(user)
        else:
            assert require_roles(role)(user) is user
    assert user.role == models.AccountRole.TECHNICIAN
    assert require_admin(user) is user
    db = MagicMock()
    assert training_capabilities_for(db, user=user) == ALL_TRAINING_CAPABILITIES
    assert set(permissions_for_user(db, user=user)) == ALL_PERMISSIONS
    assert all(has_permission(db, user=user, permission=code) for code in ALL_PERMISSIONS)
    assert set(capabilities_for_user(db, user)) == set(ALL_CAPABILITIES)
    assert all(_has_role_permission(user, permission) for permission in (
        "qms.audit.programme.approve", "qms.audit.programme.quality_review", "qms.car.close",
    ))
    assert is_control_user(user) and is_accountable_approver(user) and is_decision_approver(user)


@pytest.mark.parametrize("overrides", [
    {"amo_id": None}, {"effective_amo_id": "tenant-b"}, {"is_active": False},
    {"is_superuser": True}, {"role": models.AccountRole.SUPERUSER},
])
def test_admin_overlay_never_creates_unscoped_or_platform_authority(overrides):
    user = actor(**overrides)
    assert not is_tenant_admin(user)
    with pytest.raises(HTTPException):
        require_roles(models.AccountRole.QUALITY_MANAGER)(user)


@pytest.fixture
def governed_tenant(db_session, monkeypatch):
    migration = import_module("amodb.alembic.versions.accounts_20260803_admin_profile_governance")
    monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(db_session.connection())))
    migration.upgrade()
    db_session.execute(text("ALTER TABLE admin_profile_sessions ADD COLUMN auth_session_id VARCHAR(64)"))
    db_session.execute(text("ALTER TABLE admin_access_grant_approvals ADD COLUMN approver_role VARCHAR(64)"))
    tenants = [models.AMO(id=key, amo_code=key, login_slug=key, name=key, is_active=True) for key in ("tenant-a", "tenant-b")]
    db_session.add_all(tenants)
    users = {}
    for key, role, tenant in (
        ("admin", "TECHNICIAN", "tenant-a"), ("delegate", "USER", "tenant-a"),
        ("quality", "QUALITY_MANAGER", "tenant-a"), ("ae", "ACCOUNTABLE_EXECUTIVE", "tenant-a"),
        ("foreign-ae", "ACCOUNTABLE_EXECUTIVE", "tenant-b"), ("superuser", "SUPERUSER", "tenant-b"),
    ):
        user = models.User(id=key, amo_id=tenant, staff_code=key, email=f"{key}@example.test",
                           first_name=key, last_name="User", full_name=key, hashed_password="test",
                           role=models.AccountRole(role), is_active=True, is_amo_admin=key == "admin",
                           is_superuser=key == "superuser", must_change_password=False)
        user.auth_session_id = f"session-{key}"
        users[key] = user
        db_session.add(user)
    db_session.commit()
    return db_session, tenants[0], users


def grant(db, creator, target="delegate", **overrides):
    payload = governance.AdminGrantRequest(user_id=target, reason="Tenant administrator coverage", **{
        "grant_type": "TEMPORARY", "valid_until": datetime.now(timezone.utc) + timedelta(hours=1), **overrides,
    })
    return governance.request_admin_grant("tenant-a", payload, current_user=creator, db=db)


def test_direct_delegation_expires_and_never_becomes_a_standing_appointment(governed_tenant):
    db, tenant, users = governed_tenant
    result = grant(db, users["admin"])
    assert result["status"] == "ACTIVE"
    assert not active_admin_profile_session(db, users["delegate"], tenant)
    state = governance.activate_admin_profile("tenant-a", current_user=users["delegate"], db=db)
    assert state["active"] and state["grant_type"] == "TEMPORARY"
    delegated = get_current_active_user(users["delegate"], db)
    assert is_tenant_admin(delegated) and not is_standing_admin(delegated)
    assert not delegated.is_amo_admin and delegated.role == models.AccountRole.USER
    delegated.auth_session_id = "other-browser"
    assert not active_admin_profile_session(db, delegated, tenant)
    delegated.auth_session_id = "session-delegate"
    assert not active_admin_profile_session(db, delegated, SimpleNamespace(id="tenant-b"))
    db.execute(text("UPDATE admin_access_grants SET valid_from = :start, valid_until = :expired WHERE id = :id"),
               {"id": result["id"], "start": datetime.now(timezone.utc) - timedelta(days=2), "expired": datetime.now(timezone.utc) - timedelta(days=1)})
    db.commit()
    assert not is_tenant_admin(get_current_active_user(delegated, db))


def test_self_request_requires_accountable_executive_and_revoke_rejects_other_admins(governed_tenant):
    db, tenant, users = governed_tenant
    result = grant(db, users["delegate"], grant_type="PERMANENT", valid_until=None)
    assert result["status"] == "PENDING"
    for key in ("admin", "quality", "foreign-ae", "delegate"):
        with pytest.raises(HTTPException) as error:
            governance.approve_admin_grant("tenant-a", result["id"], governance.AdminGrantDecision(), users[key], db)
        assert error.value.status_code == 403
    decision = governance.approve_admin_grant("tenant-a", result["id"], governance.AdminGrantDecision(), users["ae"], db)
    assert decision["status"] == "ACTIVE" and decision["required_approvals"] == 1
    governance.activate_admin_profile("tenant-a", users["delegate"], db)
    assert active_admin_profile_session(db, users["delegate"], tenant)
    for key in ("admin", "quality", "foreign-ae"):
        with pytest.raises(HTTPException) as error:
            governance.revoke_admin_grant("tenant-a", result["id"], governance.AdminGrantDecision(), users[key], db)
        assert error.value.status_code == 403
    governance.revoke_admin_grant("tenant-a", result["id"], governance.AdminGrantDecision(), users["ae"], db)
    assert not active_admin_profile_session(db, users["delegate"], tenant)


def test_only_superuser_or_accountable_executive_can_disable_admin_accounts(governed_tenant):
    db, _, users = governed_tenant
    grant(db, users["admin"])
    for key in ("admin", "quality", "foreign-ae"):
        with pytest.raises(HTTPException) as error:
            router_admin.command_disable_user("delegate", db=db, current_user=users[key])
        assert error.value.status_code in (403, 404)
    assert users["delegate"].is_active
    governance.remove_administrator("tenant-a", "admin", governance.AdminRemovalDecision(deactivate_account=True), users["ae"], db)
    db.refresh(users["admin"])
    assert not users["admin"].is_active and not users["admin"].is_amo_admin


def test_platform_appointment_is_permanent_and_tenant_scoped(governed_tenant):
    db, tenant, users = governed_tenant
    result = grant(db, users["superuser"])
    assert result["status"] == "ACTIVE"
    db.refresh(users["delegate"])
    assert is_standing_admin(users["delegate"])
    assert not is_tenant_admin(users["delegate"], "tenant-b")
    state = governance.admin_profile_state("tenant-a", users["delegate"], db)
    assert state["active"] and state["grant_type"] == "PERMANENT" and state["expires_at"] is None
    governance.remove_administrator("tenant-a", "delegate", governance.AdminRemovalDecision(), users["superuser"], db)
    assert not active_admin_profile_session(db, users["delegate"], tenant)
