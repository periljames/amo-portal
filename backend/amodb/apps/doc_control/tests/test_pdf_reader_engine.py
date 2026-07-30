from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from reportlab.pdfgen import canvas

from amodb.apps.doc_control import pdfium_service as engine
from amodb.apps.manuals import pdf_reader_router as reader_router


def _plain_pdf(*, pages: int = 2) -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output)
    for index in range(pages):
        document.drawString(72, 760, f"Controlled page {index + 1}")
        document.showPage()
    document.save()
    return output.getvalue()


def _acroform_pdf() -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output)
    document.drawString(72, 760, "Aircraft registration")
    document.acroForm.textfield(
        name="registration",
        value="5Y-ABC",
        x=72,
        y=700,
        width=180,
        height=24,
        borderWidth=1,
    )
    document.acroForm.checkbox(name="serviceable", checked=True, x=72, y=650, size=18)
    document.showPage()
    document.save()
    return output.getvalue()


def test_pdfium_inspects_plain_and_acroform_pdfs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")

    plain = engine.inspect_pdf_bytes(_plain_pdf(pages=2))
    form = engine.inspect_pdf_bytes(_acroform_pdf())

    assert plain.engine == "PDFium"
    assert plain.page_count == 2
    assert plain.has_acroform is False
    assert plain.can_flatten is True
    assert form.page_count == 1
    assert form.has_acroform is True
    assert form.is_dynamic_xfa is False
    assert form.has_javascript is False
    assert form.can_flatten is True


def test_pdfium_flattens_and_reopens_without_mutating_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")
    source = _acroform_pdf()
    original = bytes(source)

    result = engine.flatten_pdf_bytes(source)

    assert source == original
    assert result.content.startswith(b"%PDF")
    assert result.page_count == 1
    assert result.flattened_pages + result.unchanged_pages == 1
    assert result.source_sha256 == hashlib.sha256(original).hexdigest()
    assert result.output_sha256 == hashlib.sha256(result.content).hexdigest()
    assert engine.inspect_pdf_bytes(result.content).page_count == result.page_count
    assert list((tmp_path / "work").iterdir()) == []


def test_pdfium_fails_closed_for_invalid_encrypted_and_scripted_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")

    with pytest.raises(engine.PdfEngineError, match="valid PDF") as invalid:
        engine.inspect_pdf_bytes(b"not-a-pdf")
    assert invalid.value.code == "PDF_INVALID"

    encrypted = _plain_pdf() + b"\n/Encrypt 1 0 R\n"
    with pytest.raises(engine.PdfEngineError) as encrypted_error:
        engine.inspect_pdf_bytes(encrypted)
    assert encrypted_error.value.code == "PDF_ENCRYPTED"

    scripted = _plain_pdf() + b"\n/JavaScript /JS /OpenAction\n"
    with pytest.raises(engine.PdfEngineError) as scripted_error:
        engine.inspect_pdf_bytes(scripted)
    assert scripted_error.value.code == "PDF_SCRIPTED"


def test_pdfium_enforces_input_and_page_limits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")
    monkeypatch.setattr(engine, "MAX_PDF_BYTES", 32)
    with pytest.raises(engine.PdfEngineError) as too_large:
        engine.inspect_pdf_bytes(_plain_pdf())
    assert too_large.value.code == "PDF_TOO_LARGE"
    assert too_large.value.status_code == 413

    monkeypatch.setattr(engine, "MAX_PDF_BYTES", 100 * 1024 * 1024)
    monkeypatch.setenv("PDFIUM_MAX_PAGES", "1")
    monkeypatch.setattr(engine, "MAX_PDF_PAGES", 1)
    # Worker limits are inherited from the environment rather than mutable parent globals.
    with pytest.raises(engine.PdfEngineError) as too_many_pages:
        engine.inspect_pdf_bytes(_plain_pdf(pages=2))
    assert too_many_pages.value.code == "PDF_PAGE_LIMIT"


def test_upload_reader_enforces_declared_and_streamed_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reader_router, "MAX_PDF_BYTES", 8)
    monkeypatch.setattr(reader_router, "_UPLOAD_CHUNK_BYTES", 3)

    declared = UploadFile(file=BytesIO(b"%PDF-12345"), filename="large.pdf", size=10)
    with pytest.raises(HTTPException) as declared_error:
        asyncio.run(reader_router.read_bounded_pdf_upload(declared))
    assert declared_error.value.status_code == 413
    assert declared_error.value.detail["code"] == "PDF_TOO_LARGE"

    streamed = UploadFile(file=BytesIO(b"%PDF-12345"), filename="unknown.pdf", size=None)
    with pytest.raises(HTTPException) as streamed_error:
        asyncio.run(reader_router.read_bounded_pdf_upload(streamed))
    assert streamed_error.value.status_code == 413
    assert streamed_error.value.detail["code"] == "PDF_TOO_LARGE"

    allowed = UploadFile(file=BytesIO(b"%PDF-1"), filename="allowed.pdf", size=None)
    assert asyncio.run(reader_router.read_bounded_pdf_upload(allowed)) == b"%PDF-1"


def test_signature_required_profiles_disable_flatten_and_submit(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_reader_routes_are_registered_before_legacy_routes() -> None:
    from amodb.main import app

    expected = {
        "/manuals/t/{tenant_slug}/{manual_id}/rev/{revision_id}/pdf-capabilities": "amodb.apps.manuals.pdf_reader_router",
        "/manuals/t/{tenant_slug}/{manual_id}/rev/{revision_id}/flatten.pdf": "amodb.apps.manuals.pdf_reader_router",
        "/manuals/t/{tenant_slug}/{manual_id}/rev/{revision_id}/submit-record": "amodb.apps.manuals.pdf_reader_router",
        "/manuals/t/{tenant_slug}/linked-resources/{reference_id}/submit": "amodb.apps.manuals.knowledge_reader_access_router",
    }
    for path, expected_module in expected.items():
        matching = [route for route in app.routes if getattr(route, "path", "") == path]
        assert matching, path
        assert matching[0].endpoint.__module__ == expected_module
