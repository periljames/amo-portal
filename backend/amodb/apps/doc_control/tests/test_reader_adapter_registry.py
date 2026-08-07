from __future__ import annotations

import pytest

from amodb.apps.doc_control.reader_adapter_registry import resolve_adapter, supported_format_catalogue


@pytest.mark.parametrize(
    ("source_type", "mime", "filename", "expected"),
    [
        ("PDF", "application/pdf", "manual.pdf", "PDF_CANONICAL"),
        ("DOCX", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "manual.docx", "OFFICE_DOCUMENT_DERIVATIVE"),
        ("ODT", "application/vnd.oasis.opendocument.text", "manual.odt", "OFFICE_DOCUMENT_DERIVATIVE"),
        ("XLSX", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "register.xlsx", "SPREADSHEET_DERIVATIVE"),
        ("ODS", "application/vnd.oasis.opendocument.spreadsheet", "register.ods", "SPREADSHEET_DERIVATIVE"),
        ("PPTX", "application/vnd.openxmlformats-officedocument.presentationml.presentation", "brief.pptx", "PRESENTATION_DERIVATIVE"),
        ("ODP", "application/vnd.oasis.opendocument.presentation", "brief.odp", "PRESENTATION_DERIVATIVE"),
        ("HTML", "text/html", "procedure.html", "MARKUP_TEXT_SEMANTIC"),
        ("MARKDOWN", "text/markdown", "procedure.md", "MARKUP_TEXT_SEMANTIC"),
        ("TIFF", "image/tiff", "scan.tiff", "IMAGE_DERIVATIVE"),
        ("PNG", "image/png", "drawing.png", "IMAGE_DERIVATIVE"),
        ("JPEG", "image/jpeg", "evidence.jpeg", "IMAGE_DERIVATIVE"),
    ],
)
def test_supported_formats_negotiate_a_bounded_adapter(source_type, mime, filename, expected) -> None:
    adapter = resolve_adapter(source_type=source_type, mime_type=mime, filename=filename)
    assert adapter.name == expected
    assert adapter.renderer != "DOWNLOAD_ONLY"


def test_unknown_format_fails_safe_to_download_only() -> None:
    adapter = resolve_adapter(source_type="BINARY", mime_type="application/octet-stream", filename="mystery.bin")
    assert adapter.name == "UNSUPPORTED_SAFE_FALLBACK"
    assert adapter.renderer == "DOWNLOAD_ONLY"
    assert adapter.selection_support == "NONE"


def test_ocr_is_only_an_aid_for_image_sources() -> None:
    image = resolve_adapter(source_type="TIFF", mime_type="image/tiff", filename="scan.tiff")
    assert image.ocr_mode == "AID_REQUIRED_FOR_TEXT"
    assert image.search == "OCR_AID_ONLY"


def test_catalogue_exposes_all_governed_adapter_families() -> None:
    names = {item["name"] for item in supported_format_catalogue()}
    assert {
        "PDF_CANONICAL",
        "OFFICE_DOCUMENT_DERIVATIVE",
        "SPREADSHEET_DERIVATIVE",
        "PRESENTATION_DERIVATIVE",
        "MARKUP_TEXT_SEMANTIC",
        "IMAGE_DERIVATIVE",
        "UNSUPPORTED_SAFE_FALLBACK",
    } <= names
