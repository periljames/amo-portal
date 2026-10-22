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


@pytest.mark.parametrize("period,hours", [("FOUR_HOURS", 4), ("TWENTY_FOUR_HOURS", 24), ("ONE_WEEK", 168)])
def test_standing_admin_view_is_explicit_timed_and_login_scoped(governed_tenant, period, hours):
    db, tenant, users = governed_tenant
    user = users["admin"]
    assert not governance._state(db, amo=tenant, user=user)["active"]
    before = datetime.now(timezone.utc)
    state = governance.activate_admin_profile("tenant-a", current_user=user, db=db, payload=governance.AdminProfileActivation(period=period))
    assert state["active"] and state["eligible"] and user.is_amo_admin
    assert abs((governance._as_utc(state["expires_at"]) - before).total_seconds() - hours * 3600) < 5
    assert active_admin_profile_session(db, user, tenant)
    user.auth_session_id = "another-login"
    assert not active_admin_profile_session(db, user, tenant)
    user.auth_session_id = "session-admin"
    governance.deactivate_admin_profile("tenant-a", current_user=user, db=db)
    assert not active_admin_profile_session(db, user, tenant)
    assert user.is_amo_admin and is_standing_admin(user)


def test_midnight_uses_tenant_timezone_and_handles_dst():
    now = datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc)
    assert governance._activation_expiry(now, "UNTIL_MIDNIGHT", "America/New_York") == datetime(2026, 11, 2, 5, 0, tzinfo=timezone.utc)
    assert governance._activation_expiry(now, "UNTIL_MIDNIGHT", "Africa/Nairobi") == datetime(2026, 11, 1, 21, 0, tzinfo=timezone.utc)
    assert governance.AdminProfileActivation().period == "FOUR_HOURS"


@pytest.mark.parametrize("role", ["AMO_ADMIN", "QUALITY_OFFICER", "TECHNICIAN"])
def test_admin_inherits_provider_quality_authority_without_changing_primary_role(governed_tenant, role):
    from amodb.apps.procurement import external_auth_router as auth
    from amodb.apps.procurement import external_provider_documents_router as documents
    from amodb.apps.procurement import external_contracted_work_router as work
    from amodb.apps.procurement import external_procurement_router as transactions
    from amodb.apps.quality import provider_qualification_router as qualification
    db, tenant, users = governed_tenant
    user = users["admin"]
    user.role = models.AccountRole(role)
    for gate in (auth._authorized_quality, documents._staff, work._staff, transactions._staff, transactions._technical_tenant):
        assert gate(db, "tenant-a", user) == tenant.id
        with pytest.raises(HTTPException) as error:
            gate(db, "tenant-b", user)
        assert error.value.status_code == 403
    assert documents._staff(db, "tenant-a", user, manage=True) == tenant.id
    assert documents.document_permissions("tenant-a", db, user) == {
        "quality_manager": True, "quality_reviewer": True, "document_controller": True,
    }
    auth._quality_manager(user)
    for allowed in (qualification.QUALITY, qualification.MAINTENANCE, qualification.SAFETY, {"QUALITY_MANAGER"}):
        qualification._require(user, allowed)
    assert user.role == models.AccountRole(role)
    assert user.is_amo_admin


def test_quality_officer_without_admin_appointment_keeps_existing_limits(governed_tenant):
    from amodb.apps.procurement import external_auth_router as auth
    from amodb.apps.procurement import external_provider_documents_router as documents
    from amodb.apps.quality import provider_qualification_router as qualification
    db, tenant, users = governed_tenant
    user = users["quality"]
    user.role = models.AccountRole.QUALITY_OFFICER
    assert auth._authorized_quality(db, "tenant-a", user) == tenant.id
    assert documents._staff(db, "tenant-a", user) == tenant.id
    for gate in (lambda: auth._quality_manager(user), lambda: documents._staff(db, "tenant-a", user, manage=True), lambda: qualification._require(user, {"QUALITY_MANAGER"})):
        with pytest.raises(HTTPException) as error:
            gate()
        assert error.value.status_code == 403


@pytest.mark.parametrize("state,action", [("QUALIFICATION_AGREEMENT_CHECK", "QUALITY_ACCEPTED"), ("INSPECTION", "TECHNICAL_ACCEPT"), ("AWAITING_AUTHORIZATION", "AUTHORIZE")])
def test_admin_contracted_work_actions_still_require_eligibility(monkeypatch, state, action):
    from amodb.apps.procurement import external_contracted_work_router as work
    record = {"id": "work-a", "amo_id": "tenant-a", "work_type": "BASE", "version": 1, "status": state}
    monkeypatch.setattr(work, "_one", lambda *args, **kwargs: None)
    def blocked(*args):
        raise HTTPException(409, "Qualification evidence is still required")
    monkeypatch.setattr(work, "_eligibility", blocked)
    payload = SimpleNamespace(action=action, reason="Administrator workflow verification", expected_version=1, idempotency_key="test-key")
    with pytest.raises(HTTPException) as error:
        work._transition(MagicMock(), record, payload, user=actor())
    assert error.value.status_code == 409
    assert error.value.detail == "Qualification evidence is still required"
    with pytest.raises(HTTPException) as foreign:
        work._transition(MagicMock(), record, payload, user=actor(amo_id="tenant-b", effective_amo_id="tenant-b"))
    assert foreign.value.status_code == 403


def test_admin_contracted_work_exposes_internal_actions_without_provider_impersonation(monkeypatch):
    from amodb.apps.procurement import external_contracted_work_router as work
    record = {"id": "work-a", "amo_id": "tenant-a", "work_type": "BASE", "status": "QUALIFICATION_AGREEMENT_CHECK"}
    monkeypatch.setattr(work, "_staff", lambda *args: "tenant-a")
    monkeypatch.setattr(work, "_work", lambda *args: record)
    monkeypatch.setattr(work, "_details", lambda *args: {})
    data = work.staff_detail("tenant-a", "work-a", MagicMock(), actor())
    assert "QUALITY_ACCEPTED" in data["allowed_actions"]
    assert data["can_review_inspections"]
    record["status"] = "DISPATCHED"
    assert "PROVIDER_ACCEPT" not in work.staff_detail("tenant-a", "work-a", MagicMock(), actor())["allowed_actions"]


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
    assert "qms.car.close" not in delegated.capability_codes
    assert "maintenance" not in delegated.module_access
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
    assert not state["active"] and state["eligible"] and state["grant_type"] == "PERMANENT"
    state = governance.activate_admin_profile("tenant-a", users["delegate"], db)
    assert state["active"] and state["expires_at"] is not None
    governance.remove_administrator("tenant-a", "delegate", governance.AdminRemovalDecision(), users["superuser"], db)
    assert not active_admin_profile_session(db, users["delegate"], tenant)


def test_revoking_platform_grant_removes_standing_authority(governed_tenant):
    db, tenant, users = governed_tenant
    result = grant(db, users["superuser"])
    governance.revoke_admin_grant("tenant-a", result["id"], governance.AdminGrantDecision(), users["ae"], db)
    db.refresh(users["delegate"])
    assert not users["delegate"].is_amo_admin
    assert not active_admin_profile_session(db, users["delegate"], tenant)


def test_organisation_profile_is_own_tenant_only_and_excludes_platform_controls(governed_tenant):
    from pydantic import ValidationError
    from amodb.apps.accounts import schemas
    db, tenant, users = governed_tenant
    assert router_admin.get_tenant_organisation(db, users["admin"]).id == tenant.id
    for key in ("quality", "delegate", "superuser"):
        with pytest.raises(HTTPException) as error:
            router_admin.get_tenant_organisation(db, users[key])
        assert error.value.status_code == 403
    for field in ("amo_id", "is_active", "is_demo", "login_slug"):
        with pytest.raises(ValidationError):
            schemas.TenantAMOProfileUpdate(name="Test AMO", **{field: "not-allowed"})
    grant(db, users["admin"])
    governance.activate_admin_profile("tenant-a", users["delegate"], db)
    delegate = get_current_active_user(users["delegate"], db)
    saved = router_admin.update_tenant_organisation(
        schemas.TenantAMOProfileUpdate(name="Updated tenant", time_zone="Africa/Nairobi"), db, delegate,
    )
    assert saved.name == "Updated tenant" and saved.id == tenant.id
    assert db.get(models.AMO, "tenant-b").name != "Updated tenant"
    with pytest.raises(HTTPException) as error:
        router_admin.update_tenant_organisation(
            schemas.TenantAMOProfileUpdate(name="Test", time_zone="Mars/Olympus"), db, delegate,
        )
    assert error.value.status_code == 422


def test_administrator_exposes_document_workflow_capabilities(governed_tenant):
    from amodb.apps.accounts import access_control
    db, _, users = governed_tenant
    codes = access_control.capability_codes_for_user(db, user=users["admin"])
    assert set(access_control.WORKFLOW_CAPABILITIES).issubset(codes)
    assert access_control.user_has_capability(db, user=users["admin"], capability_code="doc_control.revision.publish")


def test_admin_cannot_demote_another_legacy_admin(governed_tenant):
    db, _, users = governed_tenant
    users["delegate"].role = models.AccountRole.AMO_ADMIN
    db.commit()
    with pytest.raises(HTTPException) as error:
        router_admin._protect_tenant_admin_continuity(
            db, actor=users["admin"], users=[users["delegate"]], resulting_role=models.AccountRole.USER,
        )
    assert error.value.status_code == 403


def test_personnel_import_cannot_disable_a_delegated_administrator(governed_tenant):
    from amodb.apps.accounts.personnel_import import import_personnel_rows
    db, tenant, users = governed_tenant
    grant(db, users["admin"])
    rows = [{"row_number": 2, "PersonID": "delegate", "FIRSTNAME": "Delegate", "LASTNAME": "User",
             "Email": "delegate@example.test", "Status": "Inactive"}]
    with pytest.raises(HTTPException) as error:
        import_personnel_rows(db, amo_id=tenant.id, rows=rows, dry_run=False, actor_user_id="admin")
    assert error.value.status_code == 403
    db.rollback()
    assert db.get(models.User, "delegate").is_active


def test_import_undo_cannot_delete_a_subsequently_appointed_administrator(governed_tenant):
    from amodb.apps.audit import services as audit_services
    db, tenant, users = governed_tenant
    grant(db, users["admin"])
    audit_services.log_event(db, amo_id=tenant.id, actor_user_id="admin", entity_type="accounts.personnel_import",
                            entity_id=tenant.id, action="IMPORT", critical=True,
                            metadata={"undo_payload": {"created_user_ids": ["delegate"]}})
    db.commit()
    with pytest.raises(HTTPException) as error:
        router_admin.undo_last_personnel_import(db=db, current_user=users["admin"])
    assert error.value.status_code == 403
    assert db.get(models.User, "delegate") is not None


def test_admin_cannot_schedule_another_administrators_deactivation(governed_tenant):
    from amodb.apps.workforce.governance_mutations import _schedule_offboarding
    db, tenant, users = governed_tenant
    grant(db, users["admin"])
    with pytest.raises(HTTPException) as error:
        _schedule_offboarding(db, amo_id=tenant.id, user=users["delegate"],
                             payload={"revoke_access": True}, actor_user_id="admin")
    assert error.value.status_code == 403


def test_denied_offboarding_does_not_block_other_tenant_plans(monkeypatch):
    from datetime import date
    from amodb.apps.workforce import governance_mutations, offboarding_governance
    plans = [SimpleNamespace(id=str(index), amo_id="tenant-a", user_id=str(index),
                             requested_by_user_id="requester", effective_on=date.today(), status="SCHEDULED")
             for index in (1, 2)]
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.with_for_update.return_value.all.return_value = plans
    monkeypatch.setattr(offboarding_governance, "tenant_today", lambda *args, **kwargs: date.today())
    def execute(db, *, plan):
        if plan.id == "1":
            raise HTTPException(status_code=403, detail="Administrator removal denied")
        plan.status = "COMPLETED"
        return True
    monkeypatch.setattr(governance_mutations, "_execute_offboarding", execute)
    audit = MagicMock()
    monkeypatch.setattr(offboarding_governance.audit_services, "log_event", audit)
    assert offboarding_governance.apply_due_offboarding(db) == 1
    assert [plan.status for plan in plans] == ["FAILED", "COMPLETED"]
    assert audit.call_args_list[0].kwargs["action"] == "denied"


def test_rescheduling_offboarding_records_the_authorized_decision_maker(monkeypatch):
    from datetime import date
    from amodb.apps.workforce import offboarding_governance
    plan = SimpleNamespace(id="plan", effective_on=date.today() + timedelta(days=1), requested_by_user_id="old-requester")
    db = MagicMock()
    db.get.return_value = actor(id="ae", role=models.AccountRole.ACCOUNTABLE_EXECUTIVE, is_amo_admin=False)
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = plan
    monkeypatch.setattr(offboarding_governance, "tenant_today", lambda *args, **kwargs: date.today())
    offboarding_governance.schedule_offboarding(
        db, amo_id="tenant-a", user=actor(id="target"), actor_user_id="ae",
        payload={"effective_on": plan.effective_on, "offboarding_reason": "Approved removal", "revoke_access": True},
    )
    assert plan.requested_by_user_id == "ae" and plan.status == "SCHEDULED"
