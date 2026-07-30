from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import configure_mappers

from amodb.apps.doc_control import knowledge_models  # noqa: F401
from amodb.apps.doc_control.knowledge_service import (
    ALLOWED_CHILDREN,
    CODE_CANDIDATE,
    CONTENT_NODE_TYPES,
    EXECUTABLE_NODE_TYPES,
    NODE_TYPES,
    create_documentation_record,
    normalize_code,
)
from amodb.apps.manuals import models as manual_models
from amodb.main import app


def test_documentation_models_configure_with_canonical_manual_models() -> None:
    configure_mappers()
    table_names = {
        "documentation_nodes",
        "documentation_execution_profiles",
        "documentation_references",
        "documentation_index_jobs",
        "documentation_records",
    }
    assert table_names.issubset(set(manual_models.Base.metadata.tables))


def test_hierarchy_contract_covers_iso_documented_information_levels() -> None:
    expected = {
        "ROOT",
        "MANAGEMENT_SYSTEM",
        "MANUAL",
        "POLICY",
        "PROCEDURE",
        "WORK_INSTRUCTION",
        "FORM",
        "CHECKLIST",
        "REGISTER",
        "EXTERNAL_DOCUMENT",
        "RECORD_SERIES",
    }
    assert expected == NODE_TYPES
    assert CONTENT_NODE_TYPES.isdisjoint({"ROOT", "MANAGEMENT_SYSTEM", "RECORD_SERIES"})
    assert EXECUTABLE_NODE_TYPES == {"FORM", "CHECKLIST", "REGISTER"}
    assert "PROCEDURE" in ALLOWED_CHILDREN["MANUAL"]
    assert "WORK_INSTRUCTION" in ALLOWED_CHILDREN["PROCEDURE"]
    assert {"FORM", "CHECKLIST", "REGISTER"}.issubset(ALLOWED_CHILDREN["WORK_INSTRUCTION"])
    assert ALLOWED_CHILDREN["RECORD_SERIES"] == set()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("QAM 51", "QAM51"),
        ("QAM-051", "QAM051"),
        ("EASA Form 1", "EASAFORM1"),
        ("  qwi/eng/004 ", "QWIENG004"),
    ],
)
def test_reference_code_normalization_is_format_tolerant(value: str, expected: str) -> None:
    assert normalize_code(value) == expected


def test_reference_candidate_detection_finds_form_codes_without_linking_prose() -> None:
    text = "Complete QAM 51 before release, then attach ENG-FRM-004 to the work pack."
    candidates = [match.group(1) for match in CODE_CANDIDATE.finditer(text)]
    assert "QAM 51" in candidates
    assert "ENG-FRM-004" not in candidates  # exact aliases handle multi-alpha segments; candidate fallback stays conservative


def test_non_pdf_completed_record_is_rejected_before_storage() -> None:
    with pytest.raises(HTTPException) as caught:
        create_documentation_record(
            SimpleNamespace(),
            manual_tenant=SimpleNamespace(amo_id="amo", slug="tenant"),
            template=SimpleNamespace(id="manual", code="QAM 51"),
            revision=SimpleNamespace(id="revision"),
            profile=SimpleNamespace(),
            actor_id="user",
            filename="completed.txt",
            content=b"not a pdf",
            source_reference_id=None,
            payload={},
        )
    assert caught.value.status_code == 422


def test_knowledge_routes_are_registered_before_generic_compatibility_routes() -> None:
    routes = [route for route in app.routes if getattr(route, "path", "")]
    paths = [route.path for route in routes]
    required = {
        "/doc-control/workspace/t/{tenant_slug}/knowledge/tree",
        "/doc-control/workspace/t/{tenant_slug}/knowledge/reference-monitor",
        "/manuals/t/{tenant_slug}/{manual_id}/rev/{revision_id}/references",
        "/manuals/t/{tenant_slug}/linked-resources/{reference_id}",
        "/manuals/t/{tenant_slug}/linked-resources/{reference_id}/submit",
    }
    assert required.issubset(set(paths))
    knowledge_index = paths.index("/doc-control/workspace/t/{tenant_slug}/knowledge/tree")
    generic_dashboard_index = paths.index("/doc-control/workspace/t/{tenant_slug}/dashboard")
    assert knowledge_index > generic_dashboard_index


def test_frontend_reader_and_structure_surface_the_graph() -> None:
    root = Path(__file__).resolve().parents[5]
    pdf_viewer = (root / "frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx").read_text(encoding="utf-8")
    reader_core = (root / "frontend/src/pages/manuals/PdfReaderCore.tsx").read_text(encoding="utf-8")
    linked_panel = (root / "frontend/src/pages/manuals/LinkedDocumentationPanel.tsx").read_text(encoding="utf-8")
    structure = (root / "frontend/src/pages/documentControl/DocumentControlStructurePage.tsx").read_text(encoding="utf-8")
    assert "publication-reference-hotspot" in pdf_viewer
    assert "getPublicationReferences" in pdf_viewer
    assert "PdfReaderCore" in pdf_viewer
    assert "renderForms={fillMode && canFill}" in reader_core
    assert "onSubmitWorkingCopy={canFill ?" in linked_panel
    assert "submitLinkedPdfResource" in linked_panel
    assert "Reference monitor" in structure
    assert "RECORD_SERIES" in structure
