from __future__ import annotations

import pymupdf

from amodb.apps.doc_control.pdf_capability_service import inspect_pdf_capabilities_bytes


def _acroform_pdf_bytes() -> bytes:
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
    return content


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
