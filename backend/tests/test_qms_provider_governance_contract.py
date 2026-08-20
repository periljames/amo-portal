from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUALITY = ROOT / "amodb" / "apps" / "quality"
PROCUREMENT = ROOT / "amodb" / "apps" / "procurement"
MIGRATIONS = ROOT / "amodb" / "alembic" / "versions"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_quality_owns_provider_lifecycle_and_procurement_usage_gate() -> None:
    provider = _read(QUALITY / "provider_governance_router.py")
    procurement_router = _read(PROCUREMENT / "router.py")
    usage_gate = _read(PROCUREMENT / "supplier_quality_control.py")

    assert 'assert_quality_permission(db, ctx, "qms.supplier.manage")' in provider
    assert '"APPROVED": {"RESTRICTED", "SUSPENDED", "EXPIRED", "ARCHIVED"}' in provider
    assert 'This provider requires a current active contract before Quality approval.' in provider
    assert 'Define an approved scope or governed scope summary before Quality approval.' in provider

    assert 'def assert_supplier_usage_allowed(' in usage_gate
    assert 'service.assert_supplier_eligible(' in usage_gate
    assert 'QMS requires a current active contract before this external provider may be used.' in usage_gate

    # Re-evaluate the Quality decision at every point where a supplier becomes
    # operationally usable; do not rely on a stale earlier approval.
    assert 'payload.status == models.QuoteStatus.AWARDED' in procurement_router
    assert 'supplier_quality_control.assert_quote_award_allowed' in procurement_router
    assert procurement_router.count('supplier_quality_control.assert_purchase_order_allowed') >= 3
    assert 'supplier_quality_control.assert_supplier_usage_allowed' in procurement_router


def test_provider_governance_migration_joins_current_main_heads() -> None:
    migration = _read(MIGRATIONS / "quality_20260820_external_provider_governance.py")
    assert 'down_revision = ("quality_260820_wf_schema", "training_260820_record_updated")' in migration
    assert 'quality_external_provider_profiles' in migration
    assert 'quality_external_provider_contracts' in migration
    assert 'quality_external_provider_evidence' in migration
    assert 'ENABLE ROW LEVEL SECURITY' in migration
    assert 'FORCE ROW LEVEL SECURITY' in migration


def test_planner_uses_tenant_owned_timezone_resolution() -> None:
    timezone_service = _read(QUALITY / "tenant_timezone.py")
    planner = _read(QUALITY / "planner_calendar_router.py")
    enrichment = _read(QUALITY / "planner_calendar_enrichment_router.py")

    assert 'ZoneInfo' in timezone_service
    assert 'UTC' in timezone_service
    assert 'Nairobi' not in timezone_service
    assert 'tenant_timezone' in planner
    assert 'tenant_timezone' in enrichment
