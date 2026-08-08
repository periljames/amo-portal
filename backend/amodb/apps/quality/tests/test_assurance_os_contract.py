from __future__ import annotations

from decimal import Decimal

from amodb.database import Base
from amodb.apps.quality import canonical_router
from amodb.apps.quality.audit_assignment_guard import _privilege_scope_matches
from amodb.apps.quality.intelligence_governance_router import _compare
from amodb.apps.quality.planner_assignment_guard_router import router as assignment_guard_router
from amodb.apps.quality.audit_preparation_router import router as preparation_router


def _methods(router):
    return {
        (str(route.path), method)
        for route in router.routes
        for method in (getattr(route, "methods", None) or set())
    }


def _matching(router, path: str, method: str):
    return [
        route
        for route in router.routes
        if str(route.path) == path and method in (getattr(route, "methods", None) or set())
    ]


def _catchall_index(router) -> int:
    return next(index for index, route in enumerate(router.routes) if str(route.path).endswith("/{module_path:path}"))


def test_assurance_operating_system_models_are_registered() -> None:
    expected = {
        "quality_privilege_rules",
        "quality_privileges",
        "quality_privilege_decisions",
        "quality_independence_declarations",
        "quality_assurance_cases",
        "quality_investigation_entries",
        "quality_effectiveness_plans",
        "quality_assurance_case_events",
        "quality_signal_rules",
        "quality_signal_observations",
        "quality_requirement_nodes",
        "quality_requirement_links",
        "quality_audit_preparation_revisions",
        "quality_audit_preparation_events",
    }
    assert expected.issubset(Base.metadata.tables)


def test_assignment_guard_exposes_preflight_and_authoritative_overrides() -> None:
    methods = _methods(assignment_guard_router)
    assert {
        ("/integrations/calendar/auditor-eligibility", "POST"),
        ("/integrations/calendar/audit-schedules", "POST"),
        ("/integrations/calendar/audit-schedules/{schedule_id}/resume", "POST"),
        ("/audit-programmes/{programme_id}/items/{item_id}/schedule", "POST"),
    }.issubset(methods)


def test_assignment_overrides_are_unique_and_promoted_before_catchall() -> None:
    for router, prefix in (
        (canonical_router.router, "/api/maintenance/{amo_code}/quality"),
        (canonical_router.legacy_router, "/api/maintenance/{amo_code}/qms"),
    ):
        cases = (
            (f"{prefix}/integrations/calendar/audit-schedules", "POST", "create_guarded_planner_audit_schedule"),
            (f"{prefix}/integrations/calendar/audit-schedules/{{schedule_id}}/resume", "POST", "resume_guarded_planner_audit_schedule"),
            (f"{prefix}/audit-programmes/{{programme_id}}/items/{{item_id}}/schedule", "POST", "schedule_guarded_programme_requirement"),
        )
        for path, method, endpoint_name in cases:
            matches = _matching(router, path, method)
            assert len(matches) == 1
            assert matches[0].endpoint.__name__ == endpoint_name
            assert router.routes.index(matches[0]) < _catchall_index(router)


def test_preparation_routes_are_governed_and_promoted() -> None:
    methods = _methods(preparation_router)
    assert {
        ("/audits/{audit_id}/preparation-revisions", "GET"),
        ("/audits/{audit_id}/preparation-revisions", "POST"),
        ("/audits/{audit_id}/preparation-revisions/{revision_id}/issue", "POST"),
    }.issubset(methods)

    for router, prefix in (
        (canonical_router.router, "/api/maintenance/{amo_code}/quality"),
        (canonical_router.legacy_router, "/api/maintenance/{amo_code}/qms"),
    ):
        path = f"{prefix}/audits/{{audit_id}}/preparation-revisions"
        matches = _matching(router, path, "POST")
        assert len(matches) == 1
        assert matches[0].endpoint.__name__ == "create_preparation_revision"
        assert router.routes.index(matches[0]) < _catchall_index(router)


def test_privilege_scope_contract_preserves_global_and_exact_scope_authority() -> None:
    assert _privilege_scope_matches("GLOBAL", "DEPT-QA") is True
    assert _privilege_scope_matches("*", "DEPT-QA") is True
    assert _privilege_scope_matches("DEPT-QA", "dept-qa") is True
    assert _privilege_scope_matches("DEPT-QA", "DEPT-MX") is False
    assert _privilege_scope_matches("DEPT-QA", None) is False


def test_signal_threshold_comparisons_are_deterministic() -> None:
    value = Decimal("10")
    assert _compare(value, "GT", Decimal("9")) is True
    assert _compare(value, "GTE", Decimal("10")) is True
    assert _compare(value, "LT", Decimal("11")) is True
    assert _compare(value, "LTE", Decimal("10")) is True
    assert _compare(value, "EQ", Decimal("10")) is True
    assert _compare(value, "GT", Decimal("10")) is False
