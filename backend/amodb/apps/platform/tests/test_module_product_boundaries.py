from __future__ import annotations

from pathlib import Path

from amodb import entitlements
from amodb.apps.platform import module_commerce


ROOT = Path(__file__).resolve().parents[5]
BACKEND = ROOT / "backend" / "amodb" / "apps"
FRONTEND = ROOT / "frontend" / "src"


def test_document_control_is_a_standalone_enforceable_product() -> None:
    item = module_commerce.FIRST_PARTY_MODULES["document_control"]
    assert item["kind"] == "STANDALONE"
    assert item["implemented"] is True
    assert item["customer_selectable"] is True
    assert item["hard_requires"] == []
    assert "document_control_legacy" not in module_commerce.FIRST_PARTY_MODULES["quality"]["embedded_capabilities"]
    assert entitlements._module_aliases("document_control") == ("document_control", "quality")

    router_source = (BACKEND / "doc_control" / "router.py").read_text(encoding="utf-8")
    assert 'require_module("document_control")' in router_source


def test_compliance_bundle_contains_quality_training_and_document_control() -> None:
    suite = module_commerce.FIRST_PARTY_MODULES["compliance_suite"]
    assert suite["kind"] == "BUNDLE"
    assert set(suite["included_modules"]) == {"quality", "training", "document_control"}
    assert suite["customer_selectable"] is True


def test_technical_records_remains_inside_maintenance_operations() -> None:
    work = module_commerce.FIRST_PARTY_MODULES["work"]
    assert "technical_records" in work["embedded_capabilities"]
    source = (BACKEND / "technical_records" / "router.py").read_text(encoding="utf-8")
    assert "work_models" in source
    assert "fleet_models" in source
    assert "require_module(" not in source


def test_unenforceable_department_surfaces_are_not_sellable() -> None:
    for code in ("safety", "workshops", "rostering"):
        item = module_commerce.FIRST_PARTY_MODULES[code]
        assert item["kind"] == "PLATFORM_INCLUDED"
        assert item["customer_selectable"] is False


def test_frontend_routes_document_control_through_its_own_commercial_key() -> None:
    source = (FRONTEND / "app" / "PortalRouteSurface.tsx").read_text(encoding="utf-8")
    assert '["document-control", "documents", "publications", "manuals"].includes(section)' in source
    assert 'return "document_control"' in source
