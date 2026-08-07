from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4, landscape, letter
from reportlab.pdfgen import canvas

from amodb.apps.doc_control import pdfium_service as engine


def _large_supported_pdf(*, pages: int = 250) -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=A4)
    for page_number in range(1, pages + 1):
        document.setFont("Helvetica-Bold", 11)
        document.drawString(48, 800, f"CONTROLLED MAINTENANCE PUBLICATION · PAGE {page_number}")
        document.setFont("Helvetica", 8)
        for row in range(12):
            document.drawString(
                48,
                770 - row * 24,
                f"ATA {20 + (page_number % 10):02d} · Task {page_number:04d}-{row + 1:02d} · retained controlled text",
            )
        document.showPage()
    document.save()
    return output.getvalue()


def _mixed_orientation_pdf() -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=letter)

    document.setPageSize(letter)
    document.drawString(72, 740, "PORTRAIT CONTROLLED PAGE")
    document.rect(72, 560, 360, 120)
    document.showPage()

    document.setPageSize(landscape(letter))
    document.drawString(72, 540, "LANDSCAPE CONTROLLED PAGE")
    for column in range(5):
        document.line(72 + column * 100, 380, 72 + column * 100, 500)
    document.showPage()

    document.setPageSize(A4)
    document.drawString(72, 780, "A4 CONTROLLED ANNEX")
    document.circle(180, 620, 36)
    document.showPage()

    document.save()
    return output.getvalue()


def test_supported_large_pdf_is_fully_inspected_without_source_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")
    source = _large_supported_pdf(pages=250)
    original = bytes(source)

    inspection = engine.inspect_pdf_bytes(source)

    assert source == original
    assert len(source) < engine.MAX_PDF_BYTES
    assert inspection.page_count == 250
    assert inspection.source_sha256 == hashlib.sha256(source).hexdigest()
    assert inspection.template_fingerprint is not None
    assert len(inspection.template_fingerprint["pages"]) == 250
    assert inspection.template_fingerprint["total_anchors"] >= 250


def test_structurally_different_mixed_orientation_pdf_preserves_page_geometry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")
    inspection = engine.inspect_pdf_bytes(_mixed_orientation_pdf())

    assert inspection.page_count == 3
    pages = inspection.template_fingerprint["pages"]
    assert pages[0]["width"] < pages[0]["height"]
    assert pages[1]["width"] > pages[1]["height"]
    assert pages[2]["width"] < pages[2]["height"]
    assert len({(page["width"], page["height"]) for page in pages}) >= 2
    assert all(page["content_sha256"] for page in pages)
