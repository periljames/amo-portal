from __future__ import annotations

from decimal import Decimal

from amodb.database import Base
from amodb.apps.quality import canonical_router
from amodb.apps.quality.assurance_case_router import router as assurance_case_router
from amodb.apps.quality.audit_checklist_template_router import router as audit_checklist_template_router
from amodb.apps.quality.audit_closure_router import router as audit_closure_router
from amodb.apps.quality.audit_deferral_router import router as audit_deferral_router
from amodb.apps.quality.audit_notice_router import router as audit_notice_router
from amodb.apps.quality.audit_preparation_router import router as audit_preparation_router
from amodb.apps.quality.audit_report_governance_router import router as audit_report_governance_router
from amodb.apps.quality.audit_source_handoff_router import router as audit_source_handoff_router
from amodb.apps.quality.intelligence_governance_router import _compare, _percent, router as intelligence_governance_router
from amodb.apps.quality.intelligence_router import router as intelligence_router
from amodb.apps.quality.people_router import router as people_router


def _methods(router):
    return {
        (str(route.path), method)
        for route in router.routes
        for method in (getattr(route, "methods", None) or set())
    }


def _catchall_index(router) -> int:
    return next(
        index
        for index, route in enumerate(router.routes)
        if str(route.path).endswith("/{module_path:path}")
    )


def _matching(router, path: str, method: str):
    return [
        route
        for route in router.routes
        if str(route.path) == path and method in (getattr(route, "methods", None) or set())
    ]


def test_people_router_exposes_governed_privilege_and_independence_contract() -> None:
    assert {
        ("/people/summary", "GET"),
        ("/people/rules", "GET"),
        ("/people/rules", "POST"),
        ("/people/privileges", "GET"),
        ("/people/privileges", "POST"),
        ("/people/eligibility", "GET"),
        ("/people/privileges/{privilege_id}/decisions", "POST"),
        ("/people/independence", "POST"),
    }.issubset(_methods(people_router))


def test_assurance_case_router_exposes_investigation_and_effectiveness_contract() -> None:
    assert {
        ("/assurance-cases", "GET"),
        ("/assurance-cases", "POST"),
        ("/assurance-cases/{case_id}", "GET"),
        ("/assurance-cases/{case_id}/transitions", "POST"),
        ("/assurance-cases/{case_id}/investigation", "POST"),
        ("/assurance-cases/{case_id}/effectiveness-plans", "POST"),
        ("/assurance-cases/{case_id}/effectiveness-plans/{plan_id}/conclusion", "POST"),
    }.issubset(_methods(assurance_case_router))


def test_intelligence_contract_is_deterministic_and_source_explainable() -> None:
    assert ("/intelligence/overview", "GET") in _methods(intelligence_router)
    assert {
        ("/intelligence/signal-rules", "GET"),
        ("/intelligence/signal-rules", "POST"),
        ("/intelligence/signal-rules/defaults", "POST"),
        ("/intelligence/signals/evaluate", "POST"),
        ("/intelligence/signals", "GET"),
        ("/intelligence/approval-graph", "GET"),
        ("/intelligence/approval-graph/nodes", "POST"),
        ("/intelligence/approval-graph/links", "POST"),
        ("/intelligence/approval-digital-twin", "GET"),
    }.issubset(_methods(intelligence_governance_router))
    assert _percent(8, 10) == Decimal("80.000000")
    assert _percent(0, 0) == Decimal("0.000000")
    assert _compare(Decimal("80"), "LT", Decimal("81")) is True
    assert _compare(Decimal("10"), "GT", Decimal("10")) is False
    assert _compare(Decimal("10"), "GTE", Decimal("10")) is True


def test_full_audit_governance_contract() -> None:
    assert {
        ("/audits/{audit_id}/preparation-revisions", "GET"),
        ("/audits/{audit_id}/preparation-revisions", "POST"),
        ("/audits/{audit_id}/preparation-revisions/{revision_id}/issue", "POST"),
    }.issubset(_methods(audit_preparation_router))
    assert {
        ("/audit-notice-policies", "GET"),
        ("/audit-notice-policies", "POST"),
        ("/audit-notice-policies/{policy_id}", "PATCH"),
        ("/audits/{audit_id}/notices", "GET"),
        ("/audits/{audit_id}/notices", "POST"),
        ("/audits/{audit_id}/notices/{notice_id}/revisions", "POST"),
        ("/audits/{audit_id}/notices/{notice_id}/transitions", "POST"),
    }.issubset(_methods(audit_notice_router))
    assert {
        ("/audit-checklist-templates", "GET"),
        ("/audit-checklist-templates", "POST"),
        ("/audit-checklist-templates/{template_id}", "GET"),
        ("/audit-checklist-templates/{template_id}/revisions", "POST"),
        ("/audit-checklist-templates/{template_id}/revisions/{revision_id}/issue", "POST"),
        ("/audits/{audit_id}/checklist-bindings", "GET"),
        ("/audits/{audit_id}/checklist-bindings", "POST"),
    }.issubset(_methods(audit_checklist_template_router))
    assert {
        ("/audits/{audit_id}/report-revisions", "GET"),
        ("/audits/{audit_id}/report-revisions/adopt-current", "POST"),
        ("/audits/{audit_id}/report-revisions/{revision_id}/transitions", "POST"),
    }.issubset(_methods(audit_report_governance_router))
    assert {
        ("/audits/{audit_id}/closure-state", "GET"),
        ("/audits/{audit_id}/closure-state/execution-close", "POST"),
        ("/audits/{audit_id}/closure-state/follow-up-complete", "POST"),
        ("/audits/{audit_id}/closure-state/reopen-follow-up", "POST"),
    }.issubset(_methods(audit_closure_router))
    assert {
        ("/audit-deferrals", "GET"),
        ("/audit-deferrals", "POST"),
        ("/audit-deferrals/{deferral_id}/decision", "POST"),
        ("/audit-deferrals/{deferral_id}/apply", "POST"),
    }.issubset(_methods(audit_deferral_router))
    assert {
        ("/audit-source-links", "GET"),
        ("/missions/{mission_id}/audit-handoffs", "POST"),
        ("/intelligence/signals/{signal_id}/audit-handoffs", "POST"),
    }.issubset(_methods(audit_source_handoff_router))


def test_new_operating_system_models_are_registered_in_shared_metadata() -> None:
    required_tables = {
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
        "quality_audit_notice_policies",
        "quality_audit_notices",
        "quality_audit_notice_events",
        "quality_audit_checklist_templates",
        "quality_audit_checklist_template_revisions",
        "quality_audit_checklist_bindings",
        "quality_audit_report_revisions",
        "quality_audit_report_events",
        "quality_audit_closure_states",
        "quality_audit_closure_events",
        "quality_audit_deferrals",
        "quality_audit_deferral_events",
        "quality_audit_source_links",
    }
    assert required_tables.issubset(Base.metadata.tables)


def test_people_assurance_intelligence_and_audit_governance_routes_precede_generic_catchall() -> None:
    cases = (
        (canonical_router.router, "/api/maintenance/{amo_code}/quality"),
        (canonical_router.legacy_router, "/api/maintenance/{amo_code}/qms"),
    )
    route_checks = (
        ("/people/summary", "GET", "people_summary"),
        ("/people/eligibility", "GET", "get_eligibility"),
        ("/assurance-cases", "GET", "list_cases"),
        ("/assurance-cases/{case_id}/investigation", "POST", "add_investigation_entry"),
        ("/intelligence/overview", "GET", "intelligence_overview"),
        ("/intelligence/signals/evaluate", "POST", "evaluate_signals"),
        ("/intelligence/approval-digital-twin", "GET", "approval_digital_twin"),
        ("/audits/{audit_id}/preparation-revisions", "GET", "list_preparation_revisions"),
        ("/audit-notice-policies", "GET", "list_notice_policies"),
        ("/audits/{audit_id}/notices", "GET", "list_audit_notices"),
        ("/audit-checklist-templates", "GET", "list_checklist_templates"),
        ("/audits/{audit_id}/checklist-bindings", "POST", "apply_checklist_revision"),
        ("/audits/{audit_id}/report-revisions", "GET", "list_report_revisions"),
        ("/audits/{audit_id}/closure-state", "GET", "get_audit_closure_state"),
        ("/audit-deferrals", "POST", "request_deferral"),
        ("/audit-source-links", "GET", "list_audit_source_links"),
        ("/missions/{mission_id}/audit-handoffs", "POST", "create_mission_audit_handoff"),
        ("/intelligence/signals/{signal_id}/audit-handoffs", "POST", "create_signal_audit_handoff"),
    )
    for api_router, prefix in cases:
        catchall_index = _catchall_index(api_router)
        for suffix, method, endpoint_name in route_checks:
            matches = _matching(api_router, f"{prefix}{suffix}", method)
            assert len(matches) == 1, (prefix, suffix, method, [route.endpoint.__name__ for route in matches])
            assert matches[0].endpoint.__name__ == endpoint_name
            assert api_router.routes.index(matches[0]) < catchall_index
