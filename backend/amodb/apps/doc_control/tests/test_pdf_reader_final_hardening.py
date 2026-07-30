from __future__ import annotations

import hashlib
import os
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from reportlab.pdfgen import canvas

from amodb.apps.doc_control import pdfium_service as engine
from amodb.apps.manuals import pdf_reader_router as reader_router


ROOT = Path(__file__).resolve().parents[5]


def _plain_pdf() -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output)
    document.drawString(72, 760, "Immutable controlled source")
    document.showPage()
    document.save()
    return output.getvalue()


def test_source_custody_rehashes_when_path_size_and_mtime_are_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _plain_pdf()
    expected_sha256 = hashlib.sha256(source).hexdigest()
    path = tmp_path / "controlled.pdf"
    path.write_bytes(source)
    original_stat = path.stat()
    inspected: list[bytes] = []

    def fake_inspect(content: bytes) -> SimpleNamespace:
        inspected.append(content)
        return SimpleNamespace(source_sha256=hashlib.sha256(content).hexdigest())

    monkeypatch.setattr(reader_router, "inspect_pdf_bytes", fake_inspect)
    reader_router._inspect_source.cache_clear()

    first = reader_router._inspect_source(
        str(path),
        expected_sha256,
        original_stat.st_size,
        original_stat.st_mtime_ns,
    )
    assert first.source_sha256 == expected_sha256
    assert inspected == [source]

    tampered = bytearray(source)
    tampered[len(tampered) // 2] ^= 0x01
    path.write_bytes(bytes(tampered))
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    replaced_stat = path.stat()
    assert replaced_stat.st_size == original_stat.st_size
    assert replaced_stat.st_mtime_ns == original_stat.st_mtime_ns

    with pytest.raises(engine.PdfEngineError) as mismatch:
        reader_router._inspect_source(
            str(path),
            expected_sha256,
            original_stat.st_size,
            original_stat.st_mtime_ns,
        )
    assert mismatch.value.code == "PDF_SOURCE_CHECKSUM_MISMATCH"
    assert mismatch.value.status_code == 409
    # The changed bytes are rejected before a second processor invocation.
    assert inspected == [source]


def test_vector_path_geometry_is_part_of_controlled_drawing_provenance() -> None:
    rectangle = pymupdf.Rect(0, 0, 100, 100)
    first_drawing = {
        "type": "s",
        "rect": rectangle,
        "items": [("l", pymupdf.Point(0, 0), pymupdf.Point(100, 100))],
        "color": (0, 0, 0),
        "fill": None,
        "width": 1,
    }
    altered_drawing = {
        **first_drawing,
        "items": [("l", pymupdf.Point(0, 100), pymupdf.Point(100, 0))],
    }

    source_signature = engine._drawing_signature(first_drawing)
    altered_signature = engine._drawing_signature(altered_drawing)
    assert source_signature != altered_signature

    source_page = {
        "width": 100.0,
        "height": 100.0,
        "excluded_rects": [],
        "words": [],
        "images": [],
        "drawings": [{"signature": source_signature, "bbox": [0.0, 0.0, 100.0, 100.0]}],
    }
    altered_page = {
        **source_page,
        "drawings": [{"signature": altered_signature, "bbox": [0.0, 0.0, 100.0, 100.0]}],
    }
    expected = SimpleNamespace(
        page_count=1,
        source_sha256="source",
        template_fingerprint={"version": 3, "total_anchors": 1, "pages": [source_page]},
    )
    candidate = SimpleNamespace(
        page_count=1,
        source_sha256="candidate",
        template_fingerprint={"version": 3, "total_anchors": 1, "pages": [altered_page]},
    )

    with pytest.raises(engine.PdfEngineError) as mismatch:
        engine.validate_template_provenance(expected, candidate)
    assert mismatch.value.code == "PDF_TEMPLATE_MISMATCH"
    assert mismatch.value.status_code == 409


def test_dedicated_reader_workflows_trigger_for_authority_service_changes() -> None:
    authority_path = 'frontend/src/services/pdfWorkingCopyAuthority.ts'
    workflows = (
        ROOT / ".github/workflows/publications-reader-ci.yml",
        ROOT / ".github/workflows/document-control-domain-ci.yml",
    )
    for workflow in workflows:
        content = workflow.read_text(encoding="utf-8")
        assert authority_path in content, workflow
        assert "test_pdf_reader_final_hardening.py" in content, workflow
