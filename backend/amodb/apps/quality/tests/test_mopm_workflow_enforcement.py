from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from amodb.apps.procurement import external_auth_router as auth
from amodb.apps.procurement import external_contracted_work_router as contracted
from amodb.apps.doc_control import workspace_retention_router as retention
from amodb.apps.doc_control import workspace_retention_accountability_router as accountable
from amodb.apps.rostering import models
from amodb.apps.rostering.mopm_duty_policy import duty_findings
from amodb.apps.rostering.compliance_policy import statutory_rule_is_non_overridable


def test_live_supplier_search_keeps_sql_argument_separate_from_bind_parameters(monkeypatch):
    monkeypatch.setattr(auth, "_authorized_quality", lambda *args: "tenant-a")
    calls = []
    # Preserve the real helper's signature: a mock accepting **kwargs hides the
    # duplicate 'query' keyword that caused the authenticated production 500.
    def many(query, db, **params):
        calls.append((query, params))
        return []
    monkeypatch.setattr(auth.core, "many", many)
    result = auth.eligible_supplier_search("tenant-a", "  Vendor  ", 500, -1, MagicMock(), SimpleNamespace())
    assert result["limit"] == 50 and result["offset"] == 0
    assert calls[0][1] == {"amo": "tenant-a", "search_term": "%vendor%", "limit": 50, "offset": 0}


def test_contracted_functions_require_own_scope_and_authority_access():
    work = {key: "Reference" for key in ("function", "scope_text", "site_code", "contract_id", "internal_work_reference", "data_reference", "data_revision", "required_release", "defect", "technical_coordinator_id")}
    work.update(inspections_json=["Inspection"], requirements_json={})
    with pytest.raises(HTTPException) as error:
        contracted._technical_requirements(work)
    assert {"own_approved_scope_reference", "authority_access_reference"} <= set(error.value.detail["missing"])
    work["requirements_json"] = {"own_approved_scope_reference": "AMO capability 12", "authority_access_reference": "Agreement clause 8", "defined_function_only": True}
    contracted._technical_requirements(work)
    work["requirements_json"]["further_subcontracting_requested"] = True
    with pytest.raises(HTTPException):
        contracted._technical_requirements(work)
    work["requirements_json"]["prior_written_acceptance_reference"] = "Written acceptance 99"
    contracted._technical_requirements(work)
    work["requirements_json"]["complete_type_certificated_product"] = True
    with pytest.raises(HTTPException) as error:
        contracted._technical_requirements(work)
    assert "complete type-certificated product" in error.value.detail


@pytest.mark.parametrize("router,operation", [(retention, "request_disposition"), (accountable, "request_disposition_accountable")])
def test_both_disposition_request_routes_block_early_records_before_mutation(monkeypatch, router, operation):
    row = SimpleNamespace(status="ACTIVE", legal_hold=False, retention_class="MAINTENANCE_RECORDS",
        retention_until=None, metadata_json={"compliance_retention": {"events": {"release_signed_at": datetime.now(timezone.utc).isoformat()}}})
    monkeypatch.setattr(router, "require_control_user", lambda user: None)
    monkeypatch.setattr(router, "resolve_tenant", lambda *args: SimpleNamespace(amo_id="tenant-a"))
    monkeypatch.setattr(router, "_row", lambda *args, **kwargs: row)
    monkeypatch.setattr(router, "tenant_retention_extensions", lambda *args: {})
    db = MagicMock()
    payload = SimpleNamespace(justification="Approved destruction", approver_user_id="approver")
    with pytest.raises(HTTPException) as error:
        getattr(router, operation)("tenant-a", "record", payload, MagicMock(), db, SimpleNamespace(id="admin"))
    assert error.value.status_code == 409
    assert row.status == "ACTIVE" and not db.commit.called


def duty(key, start, hours, version_id="current"):
    return SimpleNamespace(id=key, user_id="engineer", version_id=version_id, deleted_at=None,
        starts_at=start, ends_at=start + timedelta(hours=hours), shift_template=None,
        status=models.RosterAssignmentStatus.DUTY)


def test_mopm_limits_apply_without_a_tenant_rule_set_and_across_roster_boundary():
    start = datetime(2026, 1, 1, 6, tzinfo=timezone.utc)
    prior = [duty(str(day), start + timedelta(days=day), 12, "previous") for day in range(6)]
    current = duty("current", start + timedelta(days=6), 12)
    version = SimpleNamespace(assignments=[current])
    findings = duty_findings(version, [*prior, current])
    assert any(row.code == "MOPM_DUTY_WEEK_LIMIT" and row.details["duty_minutes"] == 5040 for row in findings)
    assert all(not row.overridable and statutory_rule_is_non_overridable(row.code) for row in findings)


def test_planned_extensions_and_short_rest_are_blocked_but_actual_extension_is_reported():
    start = datetime(2026, 1, 1, 6, tzinfo=timezone.utc)
    first = duty("first", start, 13)
    second = duty("second", start + timedelta(hours=23), 8)
    version = SimpleNamespace(assignments=[first, second])
    codes = {row.code for row in duty_findings(version, [first, second])}
    assert {"MOPM_DUTY_SHIFT_LIMIT", "MOPM_DUTY_REST_LIMIT"} <= codes
    findings = duty_findings(SimpleNamespace(assignments=[first]), [first], actual_by_assignment={"first": (first.starts_at, first.ends_at)})
    assert [row.code for row in findings] == ["MOPM_DUTY_UNSCHEDULED_REVIEW"]
    assert findings[0].severity == models.RosterValidationSeverity.WARNING
