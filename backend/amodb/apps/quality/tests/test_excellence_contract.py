from __future__ import annotations

from datetime import date

from amodb.database import Base
from amodb.apps.quality import canonical_router
from amodb.apps.quality.excellence_router import (
    _rule_candidates,
    _score_readiness,
    router as excellence_router,
)


def _route_methods(router):
    return {
        (str(route.path), method)
        for route in router.routes
        for method in (getattr(route, "methods", None) or set())
    }


def _route_index(router, path: str) -> int:
    return next(index for index, route in enumerate(router.routes) if str(route.path) == path)


def _catchall_index(router) -> int:
    return next(
        index
        for index, route in enumerate(router.routes)
        if str(route.path).endswith("/{module_path:path}")
    )


def test_excellence_routes_cover_readiness_controls_evidence_and_governance() -> None:
    methods = _route_methods(excellence_router)
    expected = {
        ("/excellence/overview", "GET"),
        ("/excellence/controls", "GET"),
        ("/excellence/controls", "POST"),
        ("/excellence/controls/{control_id}", "PATCH"),
        ("/excellence/controls/{control_id}/evidence", "POST"),
        ("/excellence/evidence-graph", "GET"),
        ("/excellence/insights", "GET"),
        ("/excellence/insights", "POST"),
        ("/excellence/insights/rebuild", "POST"),
        ("/excellence/insights/{insight_id}", "PATCH"),
    }
    assert expected.issubset(methods)


def test_excellence_routes_are_mounted_on_canonical_tenant_router() -> None:
    canonical_paths = {str(route.path) for route in canonical_router.router.routes}
    assert "/api/maintenance/{amo_code}/quality/excellence/overview" in canonical_paths
    assert "/api/maintenance/{amo_code}/quality/excellence/controls" in canonical_paths


def test_excellence_routes_precede_the_generic_qms_catchall() -> None:
    canonical_overview = "/api/maintenance/{amo_code}/quality/excellence/overview"
    assert _route_index(canonical_router.router, canonical_overview) < _catchall_index(canonical_router.router)


def test_excellence_models_are_registered_in_shared_metadata() -> None:
    assert "quality_assurance_controls" in Base.metadata.tables
    assert "quality_assurance_evidence_links" in Base.metadata.tables
    assert "quality_intelligence_reviews" in Base.metadata.tables


def test_readiness_score_is_bounded_explainable_and_pressure_sensitive() -> None:
    clean_metrics = {
        "overdue_audits": 0,
        "audits_due_30": 1,
        "open_cars": 0,
        "overdue_cars": 0,
        "open_findings": 0,
        "active_documents": 20,
        "draft_documents": 0,
        "expired_training": 0,
        "active_controls": 10,
        "verified_controls": 10,
        "controls_due": 0,
    }
    pressured_metrics = {
        **clean_metrics,
        "overdue_audits": 4,
        "open_cars": 12,
        "overdue_cars": 5,
        "open_findings": 14,
        "draft_documents": 8,
        "expired_training": 7,
        "verified_controls": 3,
        "controls_due": 6,
    }

    clean = _score_readiness(clean_metrics)
    pressured = _score_readiness(pressured_metrics)

    assert 0 <= clean["score"] <= 100
    assert 0 <= pressured["score"] <= 100
    assert clean["score"] > pressured["score"]
    assert len(clean["dimensions"]) == 6
    assert clean["method"] == "transparent_weighted_operational_pressure_v1"
    assert "not a regulatory compliance declaration" in clean["disclaimer"].lower()


def test_rule_candidates_remain_advisory_and_source_fingerprinted() -> None:
    metrics = {
        "overdue_cars": 3,
        "overdue_audits": 2,
        "expired_training": 4,
        "active_controls": 0,
        "controls_due": 0,
    }
    candidates = _rule_candidates(metrics, date(2026, 8, 4))
    types = {item["type"] for item in candidates}

    assert {"CAPA_ESCALATION", "AUDIT_PROGRAMME_DRIFT", "COMPETENCE_RISK", "CONTROL_LIBRARY_GAP"}.issubset(types)
    assert all(item["fingerprint"].startswith("rule:") for item in candidates)
    assert all(item["recommendation"] for item in candidates)
    assert all(item["risk"] in {"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"} for item in candidates)
