from __future__ import annotations

from pathlib import Path

from amodb.apps.doc_control.workspace_document_lifecycle_router import (
    DOCUMENT_TYPES,
    STRUCTURAL_STORAGE_VALUES,
    TYPE_STORAGE_VALUE,
)


def test_document_type_choices_have_reconciliation_safe_storage_tokens() -> None:
    assert DOCUMENT_TYPES == {
        "MANUAL",
        "POLICY",
        "PROCEDURE",
        "WORK_INSTRUCTION",
        "FORM",
        "CHECKLIST",
        "REGISTER",
        "EXTERNAL_DOCUMENT",
    }
    assert set(TYPE_STORAGE_VALUE) == DOCUMENT_TYPES
    assert TYPE_STORAGE_VALUE["WORK_INSTRUCTION"] == "WORK INSTRUCTION"
    assert TYPE_STORAGE_VALUE["PROCEDURE"] == "PROCEDURE"
    assert TYPE_STORAGE_VALUE["FORM"] == "FORM"
    assert TYPE_STORAGE_VALUE["CHECKLIST"] == "CHECKLIST"
    assert TYPE_STORAGE_VALUE["REGISTER"] == "REGISTER"
    assert TYPE_STORAGE_VALUE["POLICY"] == "POLICY"
    assert STRUCTURAL_STORAGE_VALUES == set(TYPE_STORAGE_VALUE.values())


def test_lifecycle_router_protects_controlled_history_from_hard_delete() -> None:
    root = Path(__file__).resolve().parents[5]
    source = (root / "backend/amodb/apps/doc_control/workspace_document_lifecycle_router.py").read_text(encoding="utf-8")
    assert '@router.delete("/t/{tenant_slug}/documents/{manual_id}")' in source
    assert 'protected_statuses = {"PUBLISHED", "SUPERSEDED", "ARCHIVED"}' in source
    assert "Published controlled documents cannot be permanently deleted" in source
    assert "DocumentationRecord.template_manual_id == manual.id" in source
    assert 'audit(db, tenant, request, "document.deleted"' in source


def test_daily_use_shell_exposes_primary_document_lifecycle_actions() -> None:
    root = Path(__file__).resolve().parents[5]
    shell = (root / "frontend/src/pages/documentControl/DocumentControlShell.tsx").read_text(encoding="utf-8")
    actions = (root / "frontend/src/pages/documentControl/DocumentLifecycleHeaderActions.tsx").read_text(encoding="utf-8")
    assert "DocumentLifecycleHeaderActions" in shell
    assert "Add document" in actions
    assert "Change type" in actions
    assert "Delete document" in actions
    assert "previewPublicationUpload" in actions
    assert "updateDocumentType" in actions
    assert "Detected as" in actions
    assert "Your selection below is authoritative" in actions
    assert "Archive document" in actions


def test_add_document_flow_separates_publication_family_from_structural_type() -> None:
    root = Path(__file__).resolve().parents[5]
    actions = (root / "frontend/src/pages/documentControl/DocumentLifecycleHeaderActions.tsx").read_text(encoding="utf-8")
    lifecycle = (root / "backend/amodb/apps/doc_control/workspace_document_lifecycle_router.py").read_text(encoding="utf-8")
    assert 'manual_type: preview.metadata.manual_type || "GENERAL"' in actions
    assert "await updateDocumentType(tenant, uploaded.manual_id, documentType)" in actions
    assert 'metadata["publication_family"] = previous_manual_type' in lifecycle
    assert 'metadata["document_type_override"] = document_type' in lifecycle
