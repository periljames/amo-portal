from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from amodb.apps.rostering import (
    consent_router,
    consent_service,
    exemption_service,
    extended_duty_validation_policy,
    shift_semantics_router,
)
from amodb.apps.rostering.consent_models import RosterConsentStatus, RosterSupervisorDecision
from amodb.apps.workforce import permissions as workforce_permissions

UTC = timezone.utc


def test_personnel_cannot_acknowledge_another_users_assignment():
    request = SimpleNamespace(
        id="consent-1",
        personnel_id="person-1",
        personnel_response=RosterConsentStatus.PENDING,
    )
    actor = SimpleNamespace(id="person-2")

    with pytest.raises(consent_service.RosterWorkflowError) as exc:
        consent_service.respond(
            object(),
            request=request,
            actor=actor,
            accept=True,
        )
    assert exc.value.code == "ROSTER_CONSENT_FORBIDDEN"


def test_stale_consent_is_invalidated_when_material_assignment_fingerprint_changes(monkeypatch):
    request = SimpleNamespace(
        id="consent-1",
        amo_id="amo-1",
        assignment_id="assignment-1",
        assignment_fingerprint="old-fingerprint",
    )
    assignment = SimpleNamespace(
        id="assignment-1",
        user_id="person-1",
        starts_at=datetime(2026, 8, 20, 6, tzinfo=UTC),
        ends_at=datetime(2026, 8, 20, 19, tzinfo=UTC),
        shift_template_id="shift-X",
        status="STANDBY",
        role_label="Line Maintenance",
    )
    invalidations: list[str] = []
    monkeypatch.setattr(
        consent_service.common,
        "get_assignment",
        lambda *args, **kwargs: assignment,
    )
    monkeypatch.setattr(
        consent_service,
        "_invalidate",
        lambda db, row, *, actor_user_id, reason: invalidations.append(reason),
    )

    with pytest.raises(consent_service.RosterWorkflowError) as exc:
        consent_service._assert_current_assignment(object(), request)
    assert exc.value.code == "ROSTER_CONSENT_STALE"
    assert invalidations == ["STALE_ASSIGNMENT_VERSION"]


def test_supervisor_cannot_approve_outside_authority_scope(monkeypatch):
    request = SimpleNamespace(
        id="consent-1",
        supervisor_required=True,
        personnel_response=RosterConsentStatus.ACCEPTED,
        supervisor_decision=RosterSupervisorDecision.PENDING,
    )
    assignment = SimpleNamespace(
        id="assignment-1",
        department_id="department-maintenance",
        base_station_id="base-nbo",
    )
    actor = SimpleNamespace(id="supervisor-outside-scope")
    monkeypatch.setattr(
        consent_service,
        "_assert_current_assignment",
        lambda db, row: assignment,
    )
    monkeypatch.setattr(
        consent_service.governance,
        "can_approve_scope",
        lambda *args, **kwargs: False,
    )

    with pytest.raises(consent_service.RosterWorkflowError) as exc:
        consent_service.supervisor_decide(
            object(),
            request=request,
            actor=actor,
            approve=True,
        )
    assert exc.value.code == "ROSTER_SUPERVISOR_SCOPE_FORBIDDEN"


def test_department_role_defaults_fail_closed_without_resource_scope():
    user = SimpleNamespace(
        id="supervisor-1",
        amo_id="amo-1",
        effective_amo_id="amo-1",
        role="DEPARTMENT_SUPERVISOR",
        department_id="department-a",
        is_system_account=False,
        is_superuser=False,
        is_amo_admin=False,
    )
    assert not workforce_permissions._default_scope_allows(
        object(),
        user=user,
        permission_code=workforce_permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT.value,
        department_id=None,
        base_station_id=None,
    )
    assert workforce_permissions._default_scope_allows(
        object(),
        user=user,
        permission_code=workforce_permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT.value,
        department_id="department-a",
        base_station_id=None,
    )
    assert not workforce_permissions._default_scope_allows(
        object(),
        user=user,
        permission_code=workforce_permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT.value,
        department_id="department-b",
        base_station_id=None,
    )


def test_free_text_job_title_does_not_create_roster_privilege():
    user = SimpleNamespace(
        role="USER",
        position_title="Department Head / Roster Planner",
        is_system_account=False,
        is_superuser=False,
        is_amo_admin=False,
    )
    permissions = workforce_permissions.default_permissions_for(user)
    assert workforce_permissions.PermissionCode.ROSTER_VIEW_OWN.value in permissions
    assert workforce_permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT.value not in permissions
    assert workforce_permissions.PermissionCode.ROSTER_EDIT.value not in permissions
    assert workforce_permissions.PermissionCode.ROSTER_APPROVE.value not in permissions


def test_version_consent_visibility_does_not_inherit_personal_roster_access(monkeypatch):
    request = SimpleNamespace(
        id="consent-1",
        personnel_id="person-a",
        assignment_id="assignment-1",
    )
    viewer = SimpleNamespace(id="person-b")
    monkeypatch.setattr(
        consent_router.workforce_permissions,
        "has_permission",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        consent_router.common,
        "get_assignment",
        lambda *args, **kwargs: SimpleNamespace(
            department_id="department-a",
            base_station_id="base-a",
        ),
    )
    monkeypatch.setattr(
        consent_router.governance,
        "can_approve_scope",
        lambda *args, **kwargs: False,
    )
    assert not consent_router._can_view_consent_request(
        object(),
        amo_id="amo-1",
        row=request,
        user=viewer,
    )


def test_shift_semantics_guard_uses_governed_permission(monkeypatch):
    observed: list[str] = []

    def capture(*args, permission, **kwargs):
        observed.append(permission.value if hasattr(permission, "value") else str(permission))

    monkeypatch.setattr(
        shift_semantics_router.workforce_permissions,
        "require_permission",
        capture,
    )
    shift_semantics_router._require_manage(object(), SimpleNamespace())
    assert observed == [workforce_permissions.PermissionCode.ROSTER_MANAGE_SHIFT_SEMANTICS.value]


def _exemption(**overrides):
    values = {
        "amo_id": "amo-1",
        "verified_at": datetime(2026, 8, 1, tzinfo=UTC),
        "is_revoked": False,
        "effective_date": date(2026, 8, 1),
        "expiry_date": date(2026, 8, 31),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_authority_exemption_rejects_cross_tenant_expired_revoked_and_unverified_records():
    on_date = date(2026, 8, 17)
    assert exemption_service.exemption_record_is_in_force(
        _exemption(),
        amo_id="amo-1",
        on_date=on_date,
    )
    assert not exemption_service.exemption_record_is_in_force(
        _exemption(amo_id="amo-2"),
        amo_id="amo-1",
        on_date=on_date,
    )
    assert not exemption_service.exemption_record_is_in_force(
        _exemption(expiry_date=date(2026, 8, 16)),
        amo_id="amo-1",
        on_date=on_date,
    )
    assert not exemption_service.exemption_record_is_in_force(
        _exemption(is_revoked=True),
        amo_id="amo-1",
        on_date=on_date,
    )
    assert not exemption_service.exemption_record_is_in_force(
        _exemption(verified_at=None),
        amo_id="amo-1",
        on_date=on_date,
    )


def test_recovery_rest_is_timestamp_based_and_one_minute_short_remains_a_blocker_condition():
    extended_end = datetime(2026, 8, 20, 18, tzinfo=UTC)
    required = 8 * 60
    exact = extended_duty_validation_policy.recovery_rest_minutes(
        extended_duty_end=extended_end,
        next_duty_start=extended_end + timedelta(minutes=required),
    )
    short = extended_duty_validation_policy.recovery_rest_minutes(
        extended_duty_end=extended_end,
        next_duty_start=extended_end + timedelta(minutes=required - 1),
    )
    assert exact == required
    assert short == required - 1
    assert short < required
    assert extended_duty_validation_policy.RECOVERY_REST_CODE == "ROSTER_RECOVERY_REST_REQUIRED"
