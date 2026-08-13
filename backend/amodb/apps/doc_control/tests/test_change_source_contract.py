from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "amodb" / "apps" / "doc_control"
FRONTEND = ROOT.parent / "frontend" / "src" / "pages" / "documentControl"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_controller_change_sources_are_verified_against_live_tenant_records() -> None:
    source = _text(APP / "workspace_change_router.py")
    assert "verify_source_entity" in source
    assert "_verify_change_source" in source
    assert 'code": "CHANGE_SOURCE_INCOMPLETE"' in source
    assert 'code": "CHANGE_SOURCE_NOT_DISCOVERABLE"' in source
    assert 'source_entity_type": verification["source_table"]' in source
    assert 'source_entity_id": entity_id' in source


def test_reader_feedback_cannot_supply_arbitrary_source_identity() -> None:
    source = _text(APP / "workspace_change_router.py")
    assert '"source_module": "READER_FEEDBACK"' in source
    assert '"source_entity_type": None' in source
    assert '"source_entity_id": None' in source


def test_active_change_form_discovers_sources_and_never_requests_database_ids() -> None:
    actions = _text(FRONTEND / "DocumentControlChangeRequestActions.tsx")
    record_actions = _text(FRONTEND / "DocumentControlRecordActions.tsx")
    assert "getDocumentIntegrationCatalog" in actions
    assert "searchDocumentIntegrationCatalog" in actions
    assert "Do not paste database IDs" in actions
    assert "source_entity_type: selected?.source_table || null" in actions
    assert "source_entity_id: selected?.id || null" in actions
    assert "DocumentControlChangeRequestActions" in record_actions
    assert 'activeView="changes"' not in record_actions
