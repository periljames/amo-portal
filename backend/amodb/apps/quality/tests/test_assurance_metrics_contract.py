from __future__ import annotations

from types import SimpleNamespace

from amodb.apps.quality import canonical_router
from amodb.apps.quality.assurance_metrics_router import SOURCE_REGISTRY
from amodb.apps.quality.tenant_security import _QUALITY_ROLE_PERMISSIONS, _has_role_permission


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


def test_quality_officer_and_accountable_executive_permissions_are_bounded() -> None:
    officer = _QUALITY_ROLE_PERMISSIONS["QUALITY_OFFICER"]
    assert "qms.audit.execute" in officer
    assert "qms.audit.manage" not in officer
    assert "qms.audit.notice.manage" in officer
    assert "qms.car.manage" in officer
    assert "qms.car.close" not in officer
    assert "qms.settings.manage" not in officer
    assert "qms.reports.view" in officer
    assert "qms.external.view" in officer

    accountable = _QUALITY_ROLE_PERMISSIONS["ACCOUNTABLE_EXECUTIVE"]
    assert "qms.external.view" in accountable
    assert "qms.reports.export" in accountable
    assert "qms.reports.attest_authority" in accountable
    assert "qms.audit.manage" not in accountable
    assert "qms.external.view" in _QUALITY_ROLE_PERMISSIONS["VIEW_ONLY"]
    assert "qms.reports.attest_authority" not in _QUALITY_ROLE_PERMISSIONS["VIEW_ONLY"]


def test_attestation_permission_ignores_qms_wildcard_roles() -> None:
    quality_manager = SimpleNamespace(role="QUALITY_MANAGER", is_superuser=False, is_platform_context=False)
    amo_admin = SimpleNamespace(role="AMO_ADMIN", is_superuser=False, is_platform_context=False)
    accountable = SimpleNamespace(role="ACCOUNTABLE_EXECUTIVE", is_superuser=False, is_platform_context=False)

    assert _has_role_permission(quality_manager, "qms.reports.attest_authority") is False
    assert _has_role_permission(amo_admin, "qms.reports.attest_authority") is False
    assert _has_role_permission(accountable, "qms.reports.attest_authority") is True
