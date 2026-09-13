from __future__ import annotations

from amodb.apps.quality import canonical_router
from amodb.apps.quality.assurance_cockpit_router import _metric_drilldowns, _user_scope
from amodb.apps.quality.tenant_security import TenantContext


def _route(path: str, method: str):
    matches = [
        route
        for route in canonical_router.router.routes
        if str(route.path) == path and method in (getattr(route, "methods", None) or set())
    ]
    assert len(matches) == 1
    return matches[0]


def test_assurance_cockpit_routes_are_canonical_and_unique() -> None:
    prefix = "/api/maintenance/{amo_code}/quality"
    assert _route(f"{prefix}/excellence/cockpit", "GET").endpoint.__name__ == "assurance_cockpit"
    assert _route(f"{prefix}/excellence/command-search", "GET").endpoint.__name__ == "command_search"
    assert _route(f"{prefix}/excellence/cockpit/unscheduled-requirements", "GET").endpoint.__name__ == "unscheduled_programme_requirements"


def test_personal_scope_is_derived_from_authenticated_actor() -> None:
    condition, params = _user_scope(
        {"lead_auditor_user_id", "auditee_user_id", "title"},
        user_id="user-123",
        candidates=("lead_auditor_user_id", "observer_auditor_user_id", "auditee_user_id"),
    )
    assert params == {"actor_user_id": "user-123"}
    assert "lead_auditor_user_id = :actor_user_id" in condition
    assert "auditee_user_id = :actor_user_id" in condition
    assert "observer_auditor_user_id" not in condition


def test_personal_scope_fails_closed_when_source_has_no_owner_columns() -> None:
    condition, params = _user_scope(
        {"id", "title"},
        user_id="user-123",
        candidates=("owner_user_id", "assigned_to_user_id"),
    )
    assert condition == "1 = 0"
    assert params == {"actor_user_id": "user-123"}


def test_dashboard_drilldowns_preserve_period_and_context() -> None:
    ctx = TenantContext(
        amo_id="amo-1",
        amo_code="SLK",
        user_id="user-1",
        is_superuser=False,
    )
    drilldowns = _metric_drilldowns(ctx, period=2026, view="mine")
    unscheduled = drilldowns["programme_requirements_unscheduled"]
    assert unscheduled["path"] == "/maintenance/SLK/quality/audits/program"
    assert unscheduled["query"]["period"] == "2026"
    assert unscheduled["query"]["view"] == "mine"
    assert unscheduled["drawer"] == "unscheduled-requirements"
