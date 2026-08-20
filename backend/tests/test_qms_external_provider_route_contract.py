from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "frontend" / "src" / "pages" / "qms" / "routes" / "qmsRouteRegistry.ts"
PAGE = ROOT / "frontend" / "src" / "pages" / "qms" / "QmsExternalProvidersPage.tsx"


def test_external_provider_frontend_is_a_first_class_qms_workspace() -> None:
    registry = REGISTRY.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")
    assert 'navigationLabel: "External Providers"' in registry
    assert 'defaultView: "register"' in registry
    assert 'componentType: "specialist"' in registry
    assert "suppliers, contractors, subcontractors and specialist service providers" in page
    assert "Quality owns approval, oversight, contracts and evidence" in page
