from __future__ import annotations

import pymupdf

from amodb.apps.doc_control import pdf_capability_service as capability_service
from amodb.apps.doc_control.pdf_capability_service import inspect_pdf_capabilities_bytes
from amodb.apps.doc_control.pdf_safe_processing_service import (
    inspect_script_disabled_pdf_bytes,
    sanitize_pdf_javascript_bytes,
)


def _acroform_pdf_bytes(*, scripted: bool = False) -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 72), "Capability inspection fixture")
    widget = pymupdf.Widget()
    widget.field_name = "requester_name"
    widget.field_label = "Requester name"
    widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    widget.rect = pymupdf.Rect(72, 96, 320, 122)
    page.add_widget(widget)
    content = document.tobytes(garbage=4, deflate=True, clean=True)
    document.close()
    if not scripted:
        return content

    scripted_document = pymupdf.open(stream=content, filetype="pdf")
    scripted_widget = list(scripted_document[0].widgets() or [])[0]
    scripted_document.xref_set_key(
        scripted_widget.xref,
        "AA",
        '<< /K << /S /JavaScript /JS (AFNumber_Keystroke\\(0,0,0,0,"",true\\);) >> >>',
    )
    scripted_content = scripted_document.tobytes(garbage=4, deflate=True, clean=True)
    scripted_document.close()
    return scripted_content


def _widget_count(content: bytes) -> int:
    document = pymupdf.open(stream=content, filetype="pdf")
    try:
        return sum(len(list(page.widgets() or [])) for page in document)
    finally:
        document.close()


def test_lightweight_capability_inspection_detects_standard_acroform() -> None:
    inspection = inspect_pdf_capabilities_bytes(_acroform_pdf_bytes())

    assert inspection.page_count == 1
    assert inspection.has_acroform is True
    assert inspection.has_javascript is False
    assert inspection.is_dynamic_xfa is False
    assert inspection.encrypted is False
    assert inspection.can_flatten is True
    assert inspection.template_fingerprint is None
    assert len(inspection.source_sha256) == 64


def test_scripted_acroform_is_detected_without_being_misclassified_as_unreadable() -> None:
    inspection = inspect_pdf_capabilities_bytes(_acroform_pdf_bytes(scripted=True))

    assert inspection.has_acroform is True
    assert inspection.has_javascript is True
    assert inspection.can_flatten is True
    assert inspection.unsupported_reason is None


def test_script_disabled_derivative_preserves_fields_and_passes_full_inspection() -> None:
    source = _acroform_pdf_bytes(scripted=True)
    sanitized = sanitize_pdf_javascript_bytes(source)
    inspection = inspect_script_disabled_pdf_bytes(source)

    assert sanitized.startswith(b"%PDF")
    assert _widget_count(sanitized) == _widget_count(source) == 1
    assert inspection.has_acroform is True
    assert inspection.has_javascript is False
    assert inspection.can_flatten is True
    assert inspection.template_fingerprint is not None


def test_capability_inspection_reuses_the_checksum_cache(tmp_path, monkeypatch) -> None:
    source = _acroform_pdf_bytes(scripted=True)
    monkeypatch.setattr(capability_service, "CAPABILITY_CACHE_ROOT", tmp_path)

    first = inspect_pdf_capabilities_bytes(source)
    cached_files = list(tmp_path.glob("*.json"))
    assert len(cached_files) == 1

    def fail_if_worker_runs(*_args, **_kwargs):
        raise AssertionError("The PDF capability subprocess must not run for a cached immutable source")

    monkeypatch.setattr(capability_service.subprocess, "run", fail_if_worker_runs)
    second = inspect_pdf_capabilities_bytes(source)

    assert second == first
    assert second.source_sha256 == first.source_sha256
