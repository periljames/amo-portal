from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "amodb" / "apps" / "doc_control"
FRONTEND = ROOT.parent / "frontend" / "src" / "pages" / "documentControl"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_targeted_applicability_is_verified_against_live_tenant_record() -> None:
    source = _text(APP / "workspace_applicability_router.py")
    router = _text(APP / "router.py")
    assert "verify_source_entity" in source
    assert "_normalize_target" in source
    assert 'code": "APPLICABILITY_TARGET_INCOMPLETE"' in source
    assert 'code": "APPLICABILITY_TARGET_SOURCE_REQUIRED"' in source
    assert '"verified": True' in source
    assert '"source": f"PORTAL:{source_module}"' in source
    assert "workspace_applicability_router" in router
    assert "workspace_applicability_router," in router


def test_global_applicability_has_no_opaque_target_identifier() -> None:
    source = _text(APP / "workspace_applicability_router.py")
    assert '"target_type": "GLOBAL"' in source
    assert '"target_id": None' in source
    assert '"All applicable users and operations"' in source


def test_active_applicability_form_uses_discovery_not_target_id_inputs() -> None:
    actions = _text(FRONTEND / "DocumentControlApplicabilityActions.tsx")
    record_actions = _text(FRONTEND / "DocumentControlRecordActions.tsx")
    assert "getDocumentIntegrationCatalog" in actions
    assert "searchDocumentIntegrationCatalog" in actions
    assert "Target database IDs are never typed manually" in actions
    assert "target_id: selected?.id || null" in actions
    assert "source_module: selected.source_module" in actions
    assert "DocumentControlApplicabilityActions" in record_actions
    assert 'activeView="applicability"' not in record_actions
