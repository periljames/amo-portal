"""Persisted capability/appointment contracts; execution belongs to Phase 3."""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from amodb.database import Base
from amodb.apps.accounts import access_control, models
from amodb.apps.quality import tenant_security
from amodb.apps.workforce import governance_models as org


@pytest.fixture
def authority(db_session, monkeypatch):
    db = db_session
    Base.metadata.create_all(db.get_bind(), tables=[
        org.WorkforceOrgUnit.__table__, org.WorkforceJobFamily.__table__,
        org.WorkforceGrade.__table__, org.WorkforcePosition.__table__,
        org.WorkforcePersonPlacement.__table__,
    ])
    today = date(2026, 11, 27)
    monkeypatch.setattr("amodb.apps.workforce.hr_people_directory._today", lambda *a, **kw: today)
    db.add_all([
        models.AMO(id="tenant", amo_code="tenant", login_slug="tenant", name="Tenant"),
        models.AMO(id="other", amo_code="other", login_slug="other", name="Other"),
    ])
    actor = models.User(
        id="actor", amo_id="tenant", staff_code="ACTOR", email="actor@governance.invalid",
        first_name="Test", last_name="Actor", full_name="Test Actor", hashed_password="unused",
        role=models.AccountRole.TECHNICIAN, is_active=True, is_system_account=False, is_amo_admin=True,
    )
    db.add_all([
        actor,
        models.Department(id="dept", amo_id="tenant", code="QUALITY", name="Quality"),
        models.Department(id="other-dept", amo_id="other", code="QUALITY", name="Other Quality"),
    ])
    profile = models.AuthRoleDefinition(
        id="profile", code="TENANT:tenant:REVIEWER", amo_id="tenant", scope_type="TENANT",
        base_role_key="QUALITY_MANAGER", is_active=True,
    )
    capability = models.AuthCapabilityDefinition(id="cap", code="qms.car.close", module="quality")
    binding = models.AuthRoleCapabilityBinding(id="binding", role_id="profile", capability_id="cap", constraints_json={})
    now = datetime.now(timezone.utc)
    grant = models.AuthUserRoleAssignment(
        id="grant", amo_id="tenant", user_id="actor", role_id="profile", is_primary=False,
        valid_from=now - timedelta(days=1), valid_to=now + timedelta(days=1),
    )
    unit = org.WorkforceOrgUnit(id="unit", amo_id="tenant", code="Q", name="Quality", legacy_department_id="dept")
    position = org.WorkforcePosition(
        id="position", amo_id="tenant", code="QM", canonical_title="Reviewer", access_profile_id="profile",
    )
    appointment = org.WorkforcePersonPlacement(
        id="appointment", amo_id="tenant", user_id="actor", org_unit_id="unit", position_id="position",
        placement_type="PRIMARY", effective_from=today - timedelta(days=1), effective_to=today + timedelta(days=1),
    )
    db.add_all([profile, capability, binding, grant, unit, position, appointment])
    db.flush()
    return db, actor, profile, grant, binding, appointment


def decision(authority, **kwargs):
    db, actor, *_ = authority
    db.flush()
    return access_control.evaluate_capability(db, user=actor, capability_code="qms.car.close", **kwargs)


def test_secondary_grant_and_separate_admin_appointment_are_eligible(authority):
    result = decision(authority)
    assert result.allowed and result.assignment_ids == ("grant",)
    assert not authority[3].is_primary


def test_administrative_status_does_not_replace_an_appointment(authority):
    authority[-1].effective_to = date(2026, 11, 26)
    result = decision(authority)
    assert not result.allowed and result.code == "APPROVAL_AUTHORITY_MISSING"


def test_secondary_department_scope_never_becomes_global(authority):
    authority[3].department_id = "dept"
    assert decision(authority).code == "OUTSIDE_AUTHORISED_SCOPE"
    assert decision(authority, department_id="other-dept").code == "OUTSIDE_AUTHORISED_SCOPE"
    assert decision(authority, department_id="dept").allowed


@pytest.mark.parametrize("change", ["expired", "future", "inactive-profile", "foreign-profile", "unknown-constraint"])
def test_invalid_grants_fail_closed(authority, change):
    _, _, profile, grant, binding, _ = authority
    now = datetime.now(timezone.utc)
    if change == "expired":
        grant.valid_to = now - timedelta(seconds=1)
    elif change == "future":
        grant.valid_from = now + timedelta(days=1)
    elif change == "inactive-profile":
        profile.is_active = False
    elif change == "foreign-profile":
        profile.amo_id = "other"
    else:
        binding.constraints_json = {"unsupported_policy": True}
    assert not decision(authority).allowed


def test_undefined_capability_does_not_use_account_role(authority):
    db, actor, *_ = authority
    actor.role = models.AccountRole.QUALITY_MANAGER
    result = access_control.evaluate_capability(db, user=actor, capability_code="qms.undefined.approve")
    assert not result.allowed and result.code == "CAPABILITY_UNDEFINED"


def test_overlapping_primary_appointments_block_controlled_decisions(authority):
    db = authority[0]
    db.add(org.WorkforcePersonPlacement(
        id="conflicting", amo_id="tenant", user_id="actor", org_unit_id="unit", position_id="position",
        placement_type="PRIMARY", effective_from=date(2026, 11, 26), effective_to=date(2026, 12, 1),
    ))
    assert decision(authority).code == "APPOINTMENT_CONFLICT"


def test_inactive_identity_and_platform_context_are_denied(authority):
    authority[1].is_active = False
    assert decision(authority).code == "APPOINTMENT_INACTIVE"
    authority[1].is_active = True
    authority[1].is_platform_context = True
    assert decision(authority).code == "APPOINTMENT_INACTIVE"


def test_dependency_and_imperative_gates_have_same_protected_result(authority):
    db, actor, *_ = authority
    ctx = tenant_security.TenantContext("tenant", "tenant", "actor", False, admin_authority=True)
    assert tenant_security.has_quality_permission(db, ctx, "qms.car.close")
    assert tenant_security._enforce_quality_permission(ctx=ctx, current_user=actor, db=db, permission="qms.car.close") == ctx
    authority[-1].effective_to = date(2026, 11, 26)
    db.flush()
    assert not tenant_security.has_quality_permission(db, ctx, "qms.car.close")
    with pytest.raises(HTTPException) as exc:
        tenant_security._enforce_quality_permission(ctx=ctx, current_user=actor, db=db, permission="qms.car.close")
    assert exc.value.status_code == 403


def test_admin_support_session_cannot_make_protected_decisions(authority):
    db = authority[0]
    ctx = tenant_security.TenantContext("tenant", "tenant", "support", True, support_access_level="ADMIN")
    for capability in access_control.PROTECTED_DECISION_CAPABILITIES:
        assert not tenant_security.has_quality_permission(db, ctx, capability)
