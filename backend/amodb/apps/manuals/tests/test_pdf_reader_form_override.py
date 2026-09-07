from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pymupdf

from amodb.apps.doc_control.pdfium_service import PdfFlattenResult, PdfInspection
from amodb.apps.manuals.pdf_reader_form_override_router import (
    _extract_completed_pages,
    _parse_requested_pages,
    _reader_source_metadata,
    _safe_form_capabilities,
)


def _inspection(*, pages: int = 3, has_form: bool = True) -> PdfInspection:
    return PdfInspection(
        engine="PDFium",
        engine_version="test",
        source_sha256="a" * 64,
        page_count=pages,
        form_type=1 if has_form else 0,
        has_acroform=has_form,
        has_javascript=False,
        is_dynamic_xfa=False,
        encrypted=False,
        can_flatten=True,
        unsupported_reason=None,
        template_fingerprint={},
    )


def test_safe_acroform_is_enabled_without_manual_execution_profile() -> None:
    payload = _safe_form_capabilities(None, _inspection(), execution_allowed=True)

    assert payload["can_fill"] is True
    assert payload["can_save_draft"] is True
    assert payload["can_download_working"] is True
    assert payload["can_flatten"] is True
    assert payload["automatic_form_execution"] is True
    assert payload["form_download_mode"] == "CHANGED_FORM_PAGES"


def test_completed_page_parser_deduplicates_and_sorts() -> None:
    assert _parse_requested_pages("[3, 1, 3, 2]", 3) == [1, 2, 3]


def test_completed_page_output_contains_only_selected_pages() -> None:
    source = pymupdf.open()
    for index in range(3):
        page = source.new_page()
        page.insert_text((72, 72), f"PAGE {index + 1}")
    content = source.tobytes()
    source.close()

    result = PdfFlattenResult(
        content=content,
        engine="PDFium",
        engine_version="test",
        source_sha256="a" * 64,
        output_sha256="b" * 64,
        page_count=3,
        form_type=1,
        flattened_pages=3,
        unchanged_pages=0,
    )

    selected = _extract_completed_pages(result, [2])
    output = pymupdf.open(stream=selected.content, filetype="pdf")
    try:
        assert output.page_count == 1
        assert "PAGE 2" in output[0].get_text()
        assert "PAGE 1" not in output[0].get_text()
        assert "PAGE 3" not in output[0].get_text()
    finally:
        output.close()


def test_reader_source_metadata_identifies_the_exact_sanitized_bytes(tmp_path, monkeypatch) -> None:
    reader_path = tmp_path / "safe-reader.pdf"
    reader_bytes = b"%PDF-1.7\nscript-disabled-reader\n%%EOF"
    reader_path.write_bytes(reader_bytes)
    revision = SimpleNamespace(source_storage_path=str(reader_path))
    inspection = PdfInspection(
        engine="PDFium",
        engine_version="test",
        source_sha256="a" * 64,
        page_count=1,
        form_type=0,
        has_acroform=False,
        has_javascript=True,
        is_dynamic_xfa=False,
        encrypted=False,
        can_flatten=True,
        unsupported_reason=None,
        template_fingerprint={},
    )
    monkeypatch.setattr(
        "amodb.apps.manuals.pdf_reader_form_override_router._safe_reader_cache_path",
        lambda _revision, _sha256: reader_path,
    )

    checksum, size = _reader_source_metadata(revision, inspection)

    assert checksum == hashlib.sha256(reader_bytes).hexdigest()
    assert size == len(reader_bytes)
    assert reader_path.with_suffix(".metadata.json").is_file()
