from __future__ import annotations

from amodb.apps.quality import canonical_router
from amodb.apps.quality.assurance_metrics_router import SOURCE_REGISTRY
from amodb.apps.quality.tenant_security import _QUALITY_ROLE_PERMISSIONS


def _route(router, path: str, method: str):
    matches = [
        route
        for route in router.routes
        if str(route.path) == path and method in (getattr(route, "methods", None) or set())
    ]
    assert len(matches) == 1
    return matches[0]


def test_schema_aware_overview_and_management_pack_are_canonical() -> None:
    for router, prefix in (
        (canonical_router.router, "/api/maintenance/{amo_code}/quality"),
    ):
        overview = _route(router, f"{prefix}/excellence/overview/full", "GET")
        management_pack = _route(router, f"{prefix}/excellence/management-review-pack", "GET")
        assert overview.endpoint.__name__ == "schema_aware_assurance_overview"
        assert management_pack.endpoint.__name__ == "schema_aware_management_review_pack"


def test_canonical_due_date_is_available_to_shared_validity_sources() -> None:
    for source_type in ("SUPPLIER", "SUPPLIER_APPROVAL", "CALIBRATION_CERTIFICATE", "REPORT"):
        assert "due_date" in SOURCE_REGISTRY[source_type].valid_until_fields


def test_inspectors_and_auditors_can_read_cross_module_assurance_without_management_rights() -> None:
    for role in ("QUALITY_INSPECTOR", "AUDITOR"):
        permissions = _QUALITY_ROLE_PERMISSIONS[role]
        assert "qms.management_review.view" in permissions
        assert "qms.supplier.view" in permissions
        assert "qms.equipment.view" in permissions
        assert "qms.risk.view" in permissions
        assert "qms.change.view" in permissions
        assert "qms.settings.manage" not in permissions
