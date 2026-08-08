from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from amodb.apps.doc_control import knowledge_service
from amodb.apps.doc_control.knowledge_indexer import index_revision_background, index_revision_references
from amodb.apps.doc_control.knowledge_records_router import _integrity
from amodb.main import app


def test_exact_page_indexer_is_bound_to_stable_service_contract() -> None:
    assert knowledge_service.index_revision_references is index_revision_references
    assert knowledge_service.index_revision_background is index_revision_background


def test_generated_record_integrity_reports_missing_artifact() -> None:
    payload = _integrity(
        SimpleNamespace(
            artifact_storage_path="/definitely/not/present/record.pdf",
            artifact_sha256="0" * 64,
        )
    )
    assert payload == {
        "status": "MISSING",
        "expected_sha256": "0" * 64,
        "actual_sha256": None,
    }


def test_generated_record_routes_are_registered() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}
    required = {
        "/doc-control/workspace/t/{tenant_slug}/knowledge/records",
        "/doc-control/workspace/t/{tenant_slug}/knowledge/records/{record_id}",
        "/doc-control/workspace/t/{tenant_slug}/knowledge/records/{record_id}/review",
        "/manuals/t/{tenant_slug}/records/{record_id}/artifact.pdf",
    }
    assert required.issubset(paths)


def test_frontend_has_generated_record_register_and_review_surface() -> None:
    root = Path(__file__).resolve().parents[5]
    page = (root / "frontend/src/pages/documentControl/DocumentControlRecordsPage.tsx").read_text(encoding="utf-8")
    service = (root / "frontend/src/services/documentationRecords.ts").read_text(encoding="utf-8")
    shell = (root / "frontend/src/pages/documentControl/DocumentControlShell.tsx").read_text(encoding="utf-8")
    router = (root / "frontend/src/router.tsx").read_text(encoding="utf-8")
    assert "Generated records" in page
    assert "reviewGeneratedDocumentationRecord" in page
    assert "integrity" in service
    # Generated records remain deep-linkable during migration, but they are a
    # retained-record/library concern rather than permanent daily DMS navigation.
    assert '/maintenance/:amoCode/document-control/records' in router
    assert 'path: "/records"' not in shell
