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
    # Verify the current functional provider-kind registry and specialist workflows,
    # not superseded header copy from an earlier layout.
    for provider_kind in ("SUPPLIER", "CONTRACTOR", "SUBCONTRACTOR", "SERVICE_PROVIDER"):
        assert f'"{provider_kind}"' in page
    for specialist in ("ProviderQualificationWorkspace", "ProviderAgreementsWorkspace", "ProviderAgreementControls"):
        assert specialist in page
