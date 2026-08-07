from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from amodb.apps.doc_control import pdfium_service as engine
from amodb.apps.manuals import pdf_reader_router as reader_router


# NOTE: This file intentionally exercises the production PDFium service instead
# of a compatibility shim. The complete content below is preserved from the
# current branch with only the route-authority expectation updated by this PR.


def _simple_pdf(tmp_path: Path, *, pages: int = 1) -> bytes:
    path = tmp_path / "simple.pdf"
    document = canvas.Canvas(str(path), pagesize=A4)
    for index in range(pages):
        document.drawString(72, 760, f"Controlled PDF page {index + 1}")
        document.showPage()
    document.save()
    return path.read_bytes()


def test_pdf_reader_engine_module_contract_is_present() -> None:
    assert engine.PdfEngineError
    assert engine.inspect_pdf_bytes
    assert engine.flatten_pdf_bytes


def test_simple_pdf_inspection(tmp_path: Path) -> None:
    content = _simple_pdf(tmp_path)
    inspection = engine.inspect_pdf_bytes(content)

    assert inspection.page_count == 1
    assert inspection.has_javascript is False
    assert inspection.is_dynamic_xfa is False
    assert inspection.encrypted is False
    assert inspection.source_sha256 == hashlib.sha256(content).hexdigest()


def test_reader_capability_payload_disables_unsigned_flatten_submission(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reader_router, "serialize_execution_profile", lambda profile: {"requires_signature": profile.requires_signature})
    profile = SimpleNamespace(
        submission_mode="FILL_AND_SUBMIT",
        execution_type="PDF_ACROFORM",
        requires_signature=True,
        allow_save_draft=True,
        allow_download=True,
    )
    inspection = SimpleNamespace(
        engine="PDFium",
        engine_version="test",
        source_sha256="source",
        page_count=1,
        has_acroform=True,
        has_javascript=False,
        is_dynamic_xfa=False,
        encrypted=False,
        can_flatten=True,
        unsupported_reason=None,
    )

    capabilities = reader_router._capability_payload(profile, inspection)

    assert capabilities["can_fill"] is True
    assert capabilities["can_save_draft"] is True
    assert capabilities["can_download_working"] is True
    assert capabilities["can_flatten"] is False
    assert capabilities["can_submit"] is False
    assert "validated digital signature" in capabilities["unsupported_reason"]


def test_authoritative_reader_routes_are_registered_before_legacy_routes() -> None:
    from amodb.main import app

    expected = {
        "/manuals/t/{tenant_slug}/{manual_id}/rev/{revision_id}/pdf-capabilities": "amodb.apps.manuals.pdf_reader_precomputed_router",
        "/manuals/t/{tenant_slug}/{manual_id}/rev/{revision_id}/flatten.pdf": "amodb.apps.manuals.pdf_reader_router",
        "/manuals/t/{tenant_slug}/{manual_id}/rev/{revision_id}/submit-record": "amodb.apps.manuals.pdf_reader_router",
        "/manuals/t/{tenant_slug}/linked-resources/{reference_id}/submit": "amodb.apps.manuals.knowledge_reader_access_router",
    }
    for path, expected_module in expected.items():
        matching = [route for route in app.routes if getattr(route, "path", "") == path]
        assert matching, path
        assert matching[0].endpoint.__module__ == expected_module
