from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from amodb.apps.rostering import consent_service, exemption_service, extended_duty_validation_policy
from amodb.apps.rostering.consent_models import RosterConsentStatus, RosterSupervisorDecision

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
