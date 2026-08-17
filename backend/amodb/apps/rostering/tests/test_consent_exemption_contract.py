from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from amodb.apps.rostering import compliance_policy, consent_service, models
from amodb.apps.rostering.application_router import router
from amodb.apps.rostering.code_registry_models import RosterShiftTemplatePolicy
from amodb.apps.rostering.consent_models import (
    RosterAssignmentConsent,
    RosterRegulatoryExemption,
)

UTC = timezone.utc
MIGRATION = Path(__file__).resolve().parents[3] / "alembic" / "versions" / "rostering_20260817_consent_exemptions.py"


def _routes():
    return {
        (method, route.path)
        for route in router.routes
        for method in (getattr(route, "methods", None) or set())
    }


def _assignment(**overrides):
    start = datetime(2026, 8, 20, 6, tzinfo=UTC)
    values = {
        "id": "assignment-1",
        "user_id": "person-1",
        "starts_at": start,
        "ends_at": start + timedelta(hours=12),
        "shift_template_id": "shift-X",
        "status": models.RosterAssignmentStatus.STANDBY,
        "role_label": "Line Maintenance",
        "task_note": "Work package A",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_consent_and_exemption_schema_is_tenant_owned_and_revision_bound():
    policy_columns = set(RosterShiftTemplatePolicy.__table__.columns.keys())
    assert {
        "requires_personnel_acknowledgement",
        "requires_supervisor_approval",
        "fatigue_weight",
        "pay_classification",
    }.issubset(policy_columns)

    consent_columns = set(RosterAssignmentConsent.__table__.columns.keys())
    assert {
        "amo_id",
        "version_id",
        "assignment_id",
        "assignment_revision",
        "assignment_fingerprint",
        "personnel_id",
        "personnel_response",
        "personnel_response_at",
        "supervisor_required",
        "supervisor_decision",
        "statutory_compliance_json",
        "fatigue_risk_json",
        "invalidated_at",
    }.issubset(consent_columns)

    exemption_columns = set(RosterRegulatoryExemption.__table__.columns.keys())
    assert {
        "amo_id",
        "authority",
        "exemption_reference",
        "regulation_provision",
        "scope",
        "conditions_json",
        "effective_date",
        "expiry_date",
        "supporting_document_id",
        "verified_by_user_id",
        "verified_at",
        "is_revoked",
    }.issubset(exemption_columns)


def test_assignment_fingerprint_changes_only_when_acknowledged_material_terms_change():
    base = _assignment()
    baseline = consent_service.assignment_fingerprint(base)

    assert consent_service.assignment_fingerprint(_assignment(task_note="Different internal note")) == baseline
    assert consent_service.assignment_fingerprint(_assignment(ends_at=base.ends_at + timedelta(hours=1))) != baseline
    assert consent_service.assignment_fingerprint(_assignment(starts_at=base.starts_at + timedelta(hours=1))) != baseline
    assert consent_service.assignment_fingerprint(_assignment(shift_template_id="shift-HA")) != baseline
    assert consent_service.assignment_fingerprint(_assignment(status=models.RosterAssignmentStatus.DUTY)) != baseline
    assert consent_service.assignment_fingerprint(_assignment(role_label="Certifying Engineer")) != baseline


def test_statutory_rest_and_total_hours_cannot_use_generic_manager_override():
    assert compliance_policy.statutory_rule_is_non_overridable("REST_DAY_24H_IN_7D")
    assert compliance_policy.statutory_rule_is_non_overridable("ROSTER_PROTECTED_REST_VIOLATION")
    assert compliance_policy.statutory_rule_is_non_overridable("MAX_DUTY_14D_116H")
    assert not compliance_policy.statutory_rule_is_non_overridable("MAX_CONSECUTIVE_DUTY_DAYS_6")


def test_consent_and_authority_exemption_routes_are_mounted_once():
    routes = _routes()
    required = {
        ("GET", "/rostering/consents/me"),
        ("GET", "/rostering/consents/supervisor/pending"),
        ("POST", "/rostering/consents/{consent_id}/respond"),
        ("POST", "/rostering/consents/{consent_id}/supervisor-decision"),
        ("GET", "/rostering/regulatory-exemptions"),
        ("POST", "/rostering/regulatory-exemptions"),
        ("POST", "/rostering/regulatory-exemptions/{exemption_id}/verify"),
        ("POST", "/rostering/regulatory-exemptions/{exemption_id}/revoke"),
    }
    assert required.issubset(routes)
    for item in required:
        assert sum(1 for route in routes if route == item) == 1


def test_consent_migration_descends_from_single_pay_policy_merge_head():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "rostering_260817_consent"' in source
    assert 'down_revision = "rostering_260817_pay_merge"' in source
    assert '"roster_assignment_consents"' in source
    assert '"roster_regulatory_exemptions"' in source
    assert 'sa.ForeignKey("amos.id", ondelete="CASCADE")' in source
    assert 'sa.ForeignKey("doc_control_documents.id", ondelete="RESTRICT")' in source
