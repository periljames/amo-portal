from __future__ import annotations

from amodb.database import Base
from amodb.apps.quality import canonical_router
from amodb.apps.quality.assurance_lifecycle_guard_router import _ALLOWED_APPROVAL_TRANSITIONS
from amodb.apps.quality.assurance_wiring_router import (
    SOURCE_REGISTRY,
    _readiness,
    router as wiring_router,
)


def _route_methods(router):
    return {
        (str(route.path), method)
        for route in router.routes
        for method in (getattr(route, "methods", None) or set())
    }


def _matching_routes(router, path: str, method: str):
    return [
        route
        for route in router.routes
        if str(route.path) == path and method in (getattr(route, "methods", None) or set())
    ]


def _catchall_index(router) -> int:
    return next(
        index
        for index, route in enumerate(router.routes)
        if str(route.path).endswith("/{module_path:path}")
    )


def test_wiring_router_exposes_lifecycle_source_event_and_review_contracts() -> None:
    methods = _route_methods(wiring_router)
    expected = {
        ("/excellence/overview/full", "GET"),
        ("/excellence/source-catalog", "GET"),
        ("/excellence/source-search", "GET"),
        ("/excellence/controls", "GET"),
        ("/excellence/controls", "POST"),
        ("/excellence/controls/{control_id}", "PATCH"),
        ("/excellence/controls/{control_id}/approval", "POST"),
        ("/excellence/controls/{control_id}/tests", "GET"),
        ("/excellence/controls/{control_id}/tests", "POST"),
        ("/excellence/controls/{control_id}/evidence", "POST"),
        ("/excellence/evidence/{evidence_id}", "PATCH"),
        ("/excellence/evidence-graph", "GET"),
        ("/excellence/reconcile", "POST"),
        ("/excellence/events", "GET"),
        ("/excellence/management-review-pack", "GET"),
    }
    assert expected.issubset(methods)


def test_latest_wiring_and_lifecycle_handlers_override_base_excellence_once() -> None:
    canonical_prefix = "/api/maintenance/{amo_code}/quality"
    cases = (
        ("/excellence/controls", "GET", "list_controls"),
        ("/excellence/controls", "POST", "create_draft_control"),
        ("/excellence/controls/{control_id}", "PATCH", "update_control"),
        ("/excellence/controls/{control_id}/approval", "POST", "transition_control_approval"),
        ("/excellence/controls/{control_id}/tests", "POST", "record_approved_control_test"),
        ("/excellence/controls/{control_id}/evidence", "POST", "link_validated_evidence"),
        ("/excellence/evidence-graph", "GET", "evidence_graph"),
    )
    for suffix, method, endpoint_name in cases:
        for router, prefix in (
            (canonical_router.router, canonical_prefix),
        ):
            full_path = f"{prefix}{suffix}"
            matches = _matching_routes(router, full_path, method)
            assert len(matches) == 1
            assert matches[0].endpoint.__name__ == endpoint_name
            assert router.routes.index(matches[0]) < _catchall_index(router)


def test_control_approval_transitions_cannot_skip_governed_states() -> None:
    assert _ALLOWED_APPROVAL_TRANSITIONS == {
        "DRAFT": {"PENDING_APPROVAL"},
        "REJECTED": {"PENDING_APPROVAL", "RETIRED"},
        "PENDING_APPROVAL": {"APPROVED", "REJECTED"},
        "APPROVED": {"RETIRED"},
        "RETIRED": set(),
    }
    assert "APPROVED" not in _ALLOWED_APPROVAL_TRANSITIONS["DRAFT"]
    assert "DRAFT" not in _ALLOWED_APPROVAL_TRANSITIONS["APPROVED"]


def test_assurance_source_registry_covers_enterprise_qms_records() -> None:
    assert {
        "AUDIT",
        "AUDIT_SCHEDULE",
        "FINDING",
        "CAR",
        "DOCUMENT",
        "TRAINING",
        "SUPPLIER",
        "SUPPLIER_APPROVAL",
        "CALIBRATION",
        "CALIBRATION_CERTIFICATE",
        "EQUIPMENT",
        "RISK",
        "CHANGE",
        "MANAGEMENT_REVIEW_ACTION",
        "REGULATOR_FINDING",
        "EXTERNAL_COMMITMENT",
        "REPORT",
    }.issubset(SOURCE_REGISTRY)
    assert all(spec.table and spec.route_template and spec.identity_fields for spec in SOURCE_REGISTRY.values())


def test_wired_models_are_registered_in_shared_metadata() -> None:
    assert "quality_assurance_controls" in Base.metadata.tables
    assert "quality_assurance_evidence_links" in Base.metadata.tables
    assert "quality_control_tests" in Base.metadata.tables
    assert "quality_assurance_events" in Base.metadata.tables
    assert "quality_intelligence_reviews" in Base.metadata.tables


def test_cross_module_readiness_is_bounded_and_pressure_sensitive() -> None:
    clean = {
        "active_documents": 30,
        "draft_documents": 0,
        "active_controls": 10,
        "approved_controls": 10,
        "verified_controls": 10,
    }
    pressured = {
        **clean,
        "overdue_audits": 3,
        "audits_due_30": 5,
        "open_cars": 12,
        "overdue_cars": 4,
        "open_findings": 15,
        "draft_documents": 8,
        "expired_training": 6,
        "expired_supplier_approvals": 3,
        "overdue_calibrations": 4,
        "out_of_tolerance": 2,
        "critical_risks": 2,
        "high_risks": 5,
        "pending_changes": 8,
        "controls_due": 7,
        "verified_controls": 4,
        "failed_control_tests": 2,
        "open_regulator_findings": 3,
        "overdue_external_commitments": 2,
        "overdue_review_actions": 4,
    }
    clean_result = _readiness(clean)
    pressured_result = _readiness(pressured)
    assert 0 <= pressured_result["score"] < clean_result["score"] <= 100
    assert len(clean_result["dimensions"]) == 10
    assert clean_result["method"] == "cross_module_continuous_assurance_v2"
    assert "not a regulatory compliance declaration" in clean_result["disclaimer"].lower()
