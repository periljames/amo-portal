from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.rostering import consent_revalidation_policy, models, shift_scheduling_policy
from amodb.apps.rostering.application_router import router
from amodb.apps.rostering.code_registry_models import RosterDutySemantic, RosterShiftTemplatePolicy
from amodb.apps.rostering.consent_service import RosterWorkflowError
from amodb.apps.rostering.shift_semantics_router import _validate_semantics

MIGRATION = Path(__file__).resolve().parents[3] / "alembic" / "versions" / "rostering_20260817_shift_semantics.py"


def _routes():
    return {
        (method, route.path)
        for route in router.routes
        for method in (getattr(route, "methods", None) or set())
    }


def test_shift_operational_policy_schema_and_routes_are_tenant_governed():
    columns = set(RosterShiftTemplatePolicy.__table__.columns.keys())
    assert {
        "amo_id",
        "shift_template_id",
        "counts_as_rest",
        "on_site_availability",
        "scheduling_eligible",
        "requires_personnel_acknowledgement",
        "requires_supervisor_approval",
        "fatigue_weight",
        "pay_classification",
    }.issubset(columns)

    routes = _routes()
    assert ("GET", "/rostering/shift-operational-policies") in routes
    assert ("PATCH", "/rostering/shift-templates/{template_id}/operational-policy") in routes


def test_shift_semantics_reject_configurations_that_could_fake_rest():
    with pytest.raises(HTTPException) as duty_rest:
        _validate_semantics(
            counts_as_duty=True,
            counts_as_rest=True,
            on_site_availability=False,
            duty_semantic=RosterDutySemantic.DUTY,
        )
    assert duty_rest.value.detail["code"] == "ROSTER_SHIFT_SEMANTICS_CONFLICT"

    with pytest.raises(HTTPException) as onsite:
        _validate_semantics(
            counts_as_duty=False,
            counts_as_rest=False,
            on_site_availability=True,
            duty_semantic=RosterDutySemantic.STANDBY,
        )
    assert onsite.value.detail["code"] == "ROSTER_ONSITE_STANDBY_MUST_COUNT_AS_DUTY"

    with pytest.raises(HTTPException) as rest_duty:
        _validate_semantics(
            counts_as_duty=True,
            counts_as_rest=False,
            on_site_availability=False,
            duty_semantic=RosterDutySemantic.REST,
        )
    assert rest_duty.value.detail["code"] == "ROSTER_REST_SEMANTIC_COUNTS_AS_DUTY"

    # Valid configurable on-site standby: duty, not protected rest.
    _validate_semantics(
        counts_as_duty=True,
        counts_as_rest=False,
        on_site_availability=True,
        duty_semantic=RosterDutySemantic.STANDBY,
    )


def test_scheduling_disabled_template_is_rejected_server_side(monkeypatch):
    monkeypatch.setattr(
        shift_scheduling_policy,
        "_disabled_template_ids",
        lambda db, *, amo_id, template_ids: set(template_ids),
    )
    with pytest.raises(RosterWorkflowError) as exc:
        shift_scheduling_policy._require_eligible(
            object(),
            amo_id="amo-1",
            template_id="shift-retired",
        )
    assert exc.value.code == "ROSTER_SHIFT_NOT_SCHEDULABLE"
    assert exc.value.details["shift_template_id"] == "shift-retired"


def test_consent_decision_revalidates_before_ready_notification(monkeypatch):
    events: list[str] = []
    version = SimpleNamespace(
        id="version-1",
        amo_id="amo-1",
        period_id="period-1",
        created_by_user_id="planner-1",
        status=models.RosterVersionStatus.DRAFT,
        validation_fingerprint=None,
    )
    result = SimpleNamespace(
        blocker_count=0,
        warning_count=2,
        validation_fingerprint="validation-fingerprint-1",
    )

    monkeypatch.setattr(
        consent_revalidation_policy.common,
        "get_version",
        lambda db, *, amo_id, version_id, lock: version,
    )

    def validate(db, *, version, actor_user_id):
        events.append("validate")
        return result

    def assert_ready(db, *, version, actor_user_id):
        events.append("workflow-ready")

    monkeypatch.setattr(consent_revalidation_policy.validation, "run_validation", validate)
    monkeypatch.setattr(consent_revalidation_policy.consent_service, "assert_version_ready", assert_ready)
    monkeypatch.setattr(consent_revalidation_policy, "_planner_email", lambda *args, **kwargs: "planner@example.invalid")
    monkeypatch.setattr(
        consent_revalidation_policy.common,
        "audit",
        lambda *args, **kwargs: events.append("audit-ready"),
    )
    monkeypatch.setattr(
        consent_revalidation_policy.common,
        "notify_email",
        lambda *args, **kwargs: events.append("notify-ready"),
    )

    consent_revalidation_policy._revalidate_and_notify_if_ready(
        object(),
        amo_id="amo-1",
        version_id="version-1",
        actor_user_id="person-1",
    )
    assert events == ["validate", "workflow-ready", "audit-ready", "notify-ready"]


def test_statutory_block_prevents_ready_notification(monkeypatch):
    events: list[str] = []
    version = SimpleNamespace(
        id="version-1",
        amo_id="amo-1",
        period_id="period-1",
        created_by_user_id="planner-1",
        status=models.RosterVersionStatus.DRAFT,
        validation_fingerprint=None,
    )
    result = SimpleNamespace(
        blocker_count=1,
        warning_count=0,
        validation_fingerprint="blocked-fingerprint",
    )
    monkeypatch.setattr(
        consent_revalidation_policy.common,
        "get_version",
        lambda db, *, amo_id, version_id, lock: version,
    )
    monkeypatch.setattr(
        consent_revalidation_policy.validation,
        "run_validation",
        lambda *args, **kwargs: result,
    )
    monkeypatch.setattr(
        consent_revalidation_policy.consent_service,
        "assert_version_ready",
        lambda *args, **kwargs: events.append("workflow-ready"),
    )
    monkeypatch.setattr(
        consent_revalidation_policy.common,
        "notify_email",
        lambda *args, **kwargs: events.append("notify-ready"),
    )

    consent_revalidation_policy._revalidate_and_notify_if_ready(
        object(),
        amo_id="amo-1",
        version_id="version-1",
        actor_user_id="person-1",
    )
    assert events == []


def test_shift_semantics_migration_extends_the_single_rostering_chain():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "rostering_260817_shift_semantics"' in source
    assert 'down_revision = "rostering_260817_extension"' in source
    assert '"counts_as_rest"' in source
    assert '"on_site_availability"' in source
    assert '"scheduling_eligible"' in source
    # Migration derives defaults from controlled semantic values, not D/X/RD code names.
    assert "duty_semantic IN ('REST', 'OFF')" in source
    assert "duty_semantic = 'STANDBY'" in source
