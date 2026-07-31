from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from fastapi import HTTPException, UploadFile
from reportlab.pdfgen import canvas

from amodb.apps.doc_control import pdfium_service as engine
from amodb.apps.doc_control.knowledge_execution_scope import can_execute_profile
from amodb.apps.doc_control.pdf_provenance_overlay import reject_visual_overlays
from amodb.apps.manuals import pdf_reader_router as reader_router


def _plain_pdf(*, pages: int = 2, label: str = "Controlled page") -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output)
    for index in range(pages):
        document.drawString(72, 760, f"{label} {index + 1}")
        document.showPage()
    document.save()
    return output.getvalue()


def _acroform_pdf(*, label: str = "Aircraft registration") -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output)
    document.drawString(72, 760, label)
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


def _scripted_object_stream_pdf() -> bytes:
    document = pymupdf.open(stream=_plain_pdf(pages=1), filetype="pdf")
    try:
        document.xref_set_key(
            document.pdf_catalog(),
            "OpenAction",
            "<< /S /J#53 /JS (app.alert\\(1\\)) >>",
        )
        return document.tobytes(garbage=4, deflate=True, use_objstms=1)
    finally:
        document.close()


def _unsafe_action_pdf(subtype: str) -> bytes:
    document = pymupdf.open(stream=_plain_pdf(pages=1), filetype="pdf")
    try:
        action = document.get_new_xref()
        document.update_object(action, f"<< /Type /Action /S /{subtype} /F (external-payload) >>")
        document.xref_set_key(document.pdf_catalog(), "A", f"{action} 0 R")
        return document.tobytes(garbage=4, deflate=True, use_objstms=1)
    finally:
        document.close()


def _encrypted_pdf() -> bytes:
    document = pymupdf.open(stream=_plain_pdf(pages=1), filetype="pdf")
    try:
        return document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="owner-secret",
            user_pw="user-secret",
            permissions=0,
        )
    finally:
        document.close()


def _opaque_overlay_pdf(source: bytes, anchor_bbox: list[float]) -> bytes:
    document = pymupdf.open(stream=source, filetype="pdf")
    try:
        page = document[0]
        box = pymupdf.Rect(*anchor_bbox)
        shape = page.new_shape()
        shape.draw_rect(box)
        shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0.5)
        shape.commit(overlay=True)
        page.insert_text((box.x0, max(box.y0 + 8, box.y1 - 1)), "ALTERED", fontsize=8, overlay=True)
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


def _appearance_pdf(color: tuple[float, float, float]) -> bytes:
    document = pymupdf.open()
    try:
        page = document.new_page(width=595, height=842)
        page.insert_text(
            (72, 82),
            "Controlled appearance",
            fontname="helv",
            fontsize=12,
            color=color,
        )
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


def test_pdfium_inspects_plain_and_acroform_pdfs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")

    plain = engine.inspect_pdf_bytes(_plain_pdf(pages=2))
    form = engine.inspect_pdf_bytes(_acroform_pdf())

    assert plain.engine == "PDFium"
    assert plain.page_count == 2
    assert plain.has_acroform is False
    assert plain.can_flatten is True
    assert plain.template_fingerprint["total_anchors"] >= 2
    assert form.page_count == 1
    assert form.has_acroform is True
    assert form.is_dynamic_xfa is False
    assert form.has_javascript is False
    assert form.can_flatten is True
    assert form.template_fingerprint["pages"][0]["excluded_rects"]


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
    assert list((tmp_path / "work").iterdir()) == []


def test_pdfium_fails_closed_for_invalid_encrypted_and_parsed_scripted_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")

    with pytest.raises(engine.PdfEngineError, match="valid PDF") as invalid:
        engine.inspect_pdf_bytes(b"not-a-pdf")
    assert invalid.value.code == "PDF_INVALID"

    with pytest.raises(engine.PdfEngineError) as encrypted_error:
        engine.inspect_pdf_bytes(_encrypted_pdf())
    assert encrypted_error.value.code == "PDF_ENCRYPTED"

    scripted = _scripted_object_stream_pdf()
    assert b"/JavaScript" not in scripted
    with pytest.raises(engine.PdfEngineError) as scripted_error:
        engine.inspect_pdf_bytes(scripted)
    assert scripted_error.value.code == "PDF_SCRIPTED"


@pytest.mark.parametrize("subtype", ["Launch", "SubmitForm", "ImportData"])
def test_pdfium_rejects_non_javascript_action_dictionaries(
    subtype: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")
    artifact = _unsafe_action_pdf(subtype)
    assert b"/JavaScript" not in artifact

    with pytest.raises(engine.PdfEngineError) as blocked:
        engine.inspect_pdf_bytes(artifact)

    assert blocked.value.code == "PDF_SCRIPTED"
    assert blocked.value.status_code == 409


def test_template_provenance_accepts_same_template_and_rejects_unrelated_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")
    template = engine.inspect_pdf_bytes(_acroform_pdf())
    same_template = engine.inspect_pdf_bytes(_acroform_pdf())
    unrelated = engine.inspect_pdf_bytes(_acroform_pdf(label="Unrelated expense report"))

    evidence = engine.validate_template_provenance(template, same_template)
    assert evidence["verified"] is True
    assert evidence["template_source_sha256"] == template.source_sha256
    assert evidence["verified_anchors"] > 0

    with pytest.raises(engine.PdfEngineError) as mismatch:
        engine.validate_template_provenance(template, unrelated)
    assert mismatch.value.code == "PDF_TEMPLATE_MISMATCH"
    assert mismatch.value.status_code == 409


def test_controlled_text_appearance_is_part_of_template_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")
    template = engine.inspect_pdf_bytes(_appearance_pdf((0, 0, 0)))
    hidden_text = engine.inspect_pdf_bytes(_appearance_pdf((1, 1, 1)))
    source_word = template.template_fingerprint["pages"][0]["words"][0]
    candidate_word = hidden_text.template_fingerprint["pages"][0]["words"][0]

    assert source_word["text"] == candidate_word["text"]
    assert source_word["bbox"] == candidate_word["bbox"]
    assert source_word["appearance"] != candidate_word["appearance"]
    with pytest.raises(engine.PdfEngineError) as mismatch:
        engine.validate_template_provenance(template, hidden_text)
    assert mismatch.value.code == "PDF_TEMPLATE_MISMATCH"
    assert mismatch.value.status_code == 409


def test_visual_overlay_over_controlled_text_is_rejected_even_when_original_anchor_remains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")
    source = _acroform_pdf()
    template = engine.inspect_pdf_bytes(source)
    anchor = template.template_fingerprint["pages"][0]["words"][0]["bbox"]
    candidate = engine.inspect_pdf_bytes(_opaque_overlay_pdf(source, anchor))

    with pytest.raises(engine.PdfEngineError) as provenance:
        engine.validate_template_provenance(template, candidate)
    assert provenance.value.code == "PDF_TEMPLATE_MISMATCH"
    assert provenance.value.status_code == 409
    assert "controlled static page content" in provenance.value.message

    with pytest.raises(engine.PdfEngineError) as overlay:
        reject_visual_overlays(template, candidate)
    assert overlay.value.code == "PDF_TEMPLATE_VISUAL_OVERLAY"
    assert overlay.value.status_code == 409


def test_immutable_source_checksum_is_enforced_before_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")
    source = _plain_pdf(pages=1)
    path = tmp_path / "controlled.pdf"
    path.write_bytes(source)
    stat = path.stat()
    expected = hashlib.sha256(source).hexdigest()
    reader_router._inspect_source.cache_clear()

    inspection = reader_router._inspect_source(str(path), expected, stat.st_size, stat.st_mtime_ns)
    assert inspection.source_sha256 == expected

    reader_router._inspect_source.cache_clear()
    path.write_bytes(_plain_pdf(pages=1, label="Replaced content"))
    changed = path.stat()
    with pytest.raises(engine.PdfEngineError) as mismatch:
        reader_router._inspect_source(str(path), expected, changed.st_size, changed.st_mtime_ns)
    assert mismatch.value.code == "PDF_SOURCE_CHECKSUM_MISMATCH"
    assert mismatch.value.status_code == 409


def test_execution_scope_restricts_capabilities_and_submission_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reader_router, "serialize_execution_profile", lambda profile: {"access_scope": profile.access_scope_json})
    profile = SimpleNamespace(
        submission_mode="FILL_AND_SUBMIT",
        execution_type="PDF_ACROFORM",
        requires_signature=False,
        allow_save_draft=True,
        allow_download=True,
        access_scope_json={"roles": ["MECHANIC"], "departments": ["ENG"], "user_ids": ["named-user"]},
    )
    outsider = SimpleNamespace(
        id="ordinary-user",
        role="USER",
        department=SimpleNamespace(code="FIN"),
        is_superuser=False,
        is_amo_admin=False,
    )
    matching_role = SimpleNamespace(
        id="other-user",
        role="MECHANIC",
        department=SimpleNamespace(code="OPS"),
        is_superuser=False,
        is_amo_admin=False,
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

    assert can_execute_profile(outsider, profile) is False
    assert can_execute_profile(matching_role, profile) is True
    denied = reader_router._capability_payload(profile, inspection, execution_allowed=False)
    assert denied["can_fill"] is False
    assert denied["can_save_draft"] is False
    assert denied["can_flatten"] is False
    assert denied["can_submit"] is False
    assert denied["can_download_original"] is True
    assert "outside your execution scope" in denied["unsupported_reason"]


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
