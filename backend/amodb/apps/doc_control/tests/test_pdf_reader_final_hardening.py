from __future__ import annotations

import binascii
import hashlib
import os
import struct
import zlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from amodb.apps.doc_control import pdfium_service as engine
from amodb.apps.manuals import pdf_reader_router as reader_router


ROOT = Path(__file__).resolve().parents[5]


def _plain_pdf(*, label: str = "Immutable controlled source", font: str = "Helvetica") -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output)
    document.setFont(font, 12)
    document.drawString(72, 760, label)
    document.showPage()
    document.save()
    return output.getvalue()


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = binascii.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def _red_png() -> bytes:
    width = height = 2
    scanlines = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(scanlines))
        + _png_chunk(b"IEND", b"")
    )


def _image_pdf() -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output)
    document.drawImage(ImageReader(BytesIO(_red_png())), 72, 600, width=100, height=100)
    document.showPage()
    document.save()
    return output.getvalue()


def _pdf_with_added_static_text(source: bytes, text: str) -> bytes:
    document = pymupdf.open(stream=source, filetype="pdf")
    try:
        document[0].insert_text((72, 700), text, fontsize=12, overlay=True)
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


def _rotated_pdf(source: bytes, rotation: int = 180) -> bytes:
    document = pymupdf.open(stream=source, filetype="pdf")
    try:
        document[0].set_rotation(rotation)
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


def _faded_image_pdf(source: bytes) -> bytes:
    document = pymupdf.open(stream=source, filetype="pdf")
    try:
        page = document[0]
        graphics_state_xref = document.get_new_xref()
        document.update_object(graphics_state_xref, "<< /Type /ExtGState /ca 0.5 /CA 0.5 >>")
        document.xref_set_key(
            page.xref,
            "Resources/ExtGState",
            f"<< /GSfade {graphics_state_xref} 0 R >>",
        )

        original_contents = list(page.get_contents() or [])
        prefix_xref = document.get_new_xref()
        document.update_object(prefix_xref, "<<>>")
        document.update_stream(prefix_xref, b"q /GSfade gs\n")
        suffix_xref = document.get_new_xref()
        document.update_object(suffix_xref, "<<>>")
        document.update_stream(suffix_xref, b"\nQ")
        content_refs = " ".join(f"{xref} 0 R" for xref in original_contents)
        document.xref_set_key(
            page.xref,
            "Contents",
            f"[ {prefix_xref} 0 R {content_refs} {suffix_xref} 0 R ]",
        )
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


def _controlled_form_with_navigation() -> bytes:
    document = pymupdf.open()
    first = document.new_page()
    first.insert_text((72, 72), "CONTROLLED FORM PAGE ONE")
    second = document.new_page()
    second.insert_text((72, 72), "CONTROLLED FORM PAGE TWO")
    first = document[0]
    widget = pymupdf.Widget()
    widget.field_name = "release_code"
    widget.field_label = "Release code"
    widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    widget.field_flags = 0
    widget.text_maxlen = 12
    widget.rect = pymupdf.Rect(72, 110, 220, 136)
    first.add_widget(widget)
    first.insert_link({
        "kind": pymupdf.LINK_GOTO,
        "from": pymupdf.Rect(72, 160, 220, 184),
        "page": 1,
        "to": pymupdf.Point(0, 0),
        "zoom": 0,
    })
    document.set_toc([[1, "Controlled overview", 1], [2, "Execution page", 2]])
    try:
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


def _relocate_filled_widget(source: bytes) -> bytes:
    document = pymupdf.open(stream=source, filetype="pdf")
    try:
        widget = next(iter(document[0].widgets() or []))
        document.xref_set_key(widget.xref, "V", "(APPROVED)")
        document.xref_set_key(widget.xref, "Rect", "[300 300 448 326]")
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


def _change_outline_destination(source: bytes) -> bytes:
    document = pymupdf.open(stream=source, filetype="pdf")
    try:
        document.set_toc([[1, "Controlled overview", 2], [2, "Execution page", 2]])
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


def _change_internal_link_destination(source: bytes) -> bytes:
    document = pymupdf.open(stream=source, filetype="pdf")
    try:
        page = document[0]
        link = page.get_links()[0]
        page.delete_link(link)
        page.insert_link({"kind": pymupdf.LINK_GOTO, "from": link["from"], "page": 0, "to": pymupdf.Point(0, 0), "zoom": 0})
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


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
        "rotation": 0,
        "content_sha256": "content",
        "resources_sha256": "resources",
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
        template_fingerprint={"version": 5, "total_anchors": 1, "pages": [source_page]},
    )
    candidate = SimpleNamespace(
        page_count=1,
        source_sha256="candidate",
        template_fingerprint={"version": 5, "total_anchors": 1, "pages": [altered_page]},
    )

    with pytest.raises(engine.PdfEngineError) as mismatch:
        engine.validate_template_provenance(expected, candidate)
    assert mismatch.value.code == "PDF_TEMPLATE_MISMATCH"
    assert mismatch.value.status_code == 409


def test_page_rotation_is_part_of_controlled_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")
    source_bytes = _plain_pdf(label="CONTROLLED ORIENTATION")
    rotated_bytes = _rotated_pdf(source_bytes, 180)
    source = engine.inspect_pdf_bytes(source_bytes)
    rotated = engine.inspect_pdf_bytes(rotated_bytes)

    source_page = source.template_fingerprint["pages"][0]
    rotated_page = rotated.template_fingerprint["pages"][0]
    assert source_page["width"] == rotated_page["width"]
    assert source_page["height"] == rotated_page["height"]
    assert source_page["rotation"] == 0
    assert rotated_page["rotation"] == 180
    assert source_page["words"] == rotated_page["words"]

    with pytest.raises(engine.PdfEngineError) as mismatch:
        engine.validate_template_provenance(source, rotated)
    assert mismatch.value.code == "PDF_TEMPLATE_MISMATCH"
    assert mismatch.value.status_code == 409
    assert "page rotation" in mismatch.value.message


def test_image_graphics_state_is_part_of_controlled_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")
    source_bytes = _image_pdf()
    faded_bytes = _faded_image_pdf(source_bytes)
    source = engine.inspect_pdf_bytes(source_bytes)
    faded = engine.inspect_pdf_bytes(faded_bytes)

    source_page = source.template_fingerprint["pages"][0]
    faded_page = faded.template_fingerprint["pages"][0]
    assert source_page["images"] == faded_page["images"]
    assert source_page["content_sha256"] != faded_page["content_sha256"]
    assert source_page["resources_sha256"] != faded_page["resources_sha256"]

    with pytest.raises(engine.PdfEngineError) as mismatch:
        engine.validate_template_provenance(source, faded)
    assert mismatch.value.code == "PDF_TEMPLATE_MISMATCH"
    assert mismatch.value.status_code == 409
    assert "controlled static page content" in mismatch.value.message or "graphics resources" in mismatch.value.message


def test_added_static_instructions_outside_form_fields_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")
    source = _plain_pdf(label="AIRWORTHINESS RELEASE")
    candidate = _pdf_with_added_static_text(source, "AUTHORIZED EXCEPTION: SKIP INSPECTION")

    source_inspection = engine.inspect_pdf_bytes(source)
    candidate_inspection = engine.inspect_pdf_bytes(candidate)
    assert candidate_inspection.template_fingerprint["total_anchors"] > source_inspection.template_fingerprint["total_anchors"]

    with pytest.raises(engine.PdfEngineError) as mismatch:
        engine.validate_template_provenance(source_inspection, candidate_inspection)
    assert mismatch.value.code == "PDF_TEMPLATE_MISMATCH"
    assert mismatch.value.status_code == 409
    assert "controlled static page content" in mismatch.value.message


def test_semantic_punctuation_and_operators_are_fingerprinted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")
    assert engine._normalize_text_token("LIMIT < 10 HOURS") == "limit < 10 hours"
    assert engine._normalize_text_token("LIMIT > 10 HOURS") == "limit > 10 hours"

    source = engine.inspect_pdf_bytes(_plain_pdf(label="LIMIT < 10 HOURS", font="Courier"))
    altered = engine.inspect_pdf_bytes(_plain_pdf(label="LIMIT > 10 HOURS", font="Courier"))
    source_anchor = source.template_fingerprint["pages"][0]["words"][0]
    altered_anchor = altered.template_fingerprint["pages"][0]["words"][0]
    assert source_anchor["text"] != altered_anchor["text"]
    assert source_anchor["appearance"] == altered_anchor["appearance"]
    assert source_anchor["bbox"] == altered_anchor["bbox"]

    with pytest.raises(engine.PdfEngineError) as mismatch:
        engine.validate_template_provenance(source, altered)
    assert mismatch.value.code == "PDF_TEMPLATE_MISMATCH"
    assert mismatch.value.status_code == 409


def test_dedicated_reader_workflows_trigger_for_authority_service_changes() -> None:
    authority_path = "frontend/src/services/pdfWorkingCopyAuthority.ts"
    workflows = (
        ROOT / ".github/workflows/publications-reader-ci.yml",
        ROOT / ".github/workflows/document-control-domain-ci.yml",
    )
    for workflow in workflows:
        content = workflow.read_text(encoding="utf-8")
        assert authority_path in content, workflow
        assert "test_pdf_reader_final_hardening.py" in content, workflow


@pytest.mark.parametrize(
    ("mutator", "changed_structure"),
    [
        (_relocate_filled_widget, "widgets"),
        (_change_outline_destination, "navigation"),
        (_change_internal_link_destination, "navigation"),
    ],
)
def test_controlled_widgets_and_navigation_reject_structural_relocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutator: object,
    changed_structure: str,
) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")
    source_bytes = _controlled_form_with_navigation()
    candidate_bytes = mutator(source_bytes)  # type: ignore[operator]
    source = engine.inspect_pdf_bytes(source_bytes)
    candidate = engine.inspect_pdf_bytes(candidate_bytes)

    source_page = source.template_fingerprint["pages"][0]
    candidate_page = candidate.template_fingerprint["pages"][0]
    assert source_page["content_sha256"] == candidate_page["content_sha256"]
    assert source_page["resources_sha256"] == candidate_page["resources_sha256"]
    if changed_structure == "widgets":
        assert source_page["widgets"] != candidate_page["widgets"]
    else:
        assert source.template_fingerprint["navigation"] != candidate.template_fingerprint["navigation"]

    with pytest.raises(engine.PdfEngineError) as mismatch:
        engine.validate_template_provenance(source, candidate)
    assert mismatch.value.code == "PDF_TEMPLATE_MISMATCH"
    assert mismatch.value.status_code == 409



def _fit_destination_array(document: object, page_index: int, mode: str) -> str:
    suffix = {
        "Fit": "/Fit",
        "FitH": "/FitH 72",
        "FitV": "/FitV 72",
        "FitR": "/FitR 0 0 200 200",
    }[mode]
    return f"[{document[page_index].xref} 0 R {suffix}]"  # type: ignore[index]


def _set_xref_destination(document: object, xref: int, destination: str) -> None:
    action_kind, _ = document.xref_get_key(xref, "A")  # type: ignore[attr-defined]
    if action_kind != "null":
        document.xref_set_key(xref, "A/D", destination)  # type: ignore[attr-defined]
    else:
        document.xref_set_key(xref, "Dest", destination)  # type: ignore[attr-defined]


def _rewrite_non_xyz_navigation(
    source: bytes,
    mode: str,
    page_index: int,
    *,
    outline: bool,
    page_link: bool,
) -> bytes:
    document = pymupdf.open(stream=source, filetype="pdf")
    try:
        destination = _fit_destination_array(document, page_index, mode)
        if outline:
            toc = document.get_toc(simple=False)
            outline_xref = int(toc[0][3]["xref"])
            _set_xref_destination(document, outline_xref, destination)
        if page_link:
            link_xref = int(document[0].get_links()[0]["xref"])
            _set_xref_destination(document, link_xref, destination)
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


@pytest.mark.parametrize("mode", ["Fit", "FitH", "FitV", "FitR"])
@pytest.mark.parametrize("navigation_kind", ["outline", "page_link"])
def test_non_xyz_internal_destinations_are_fingerprinted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    navigation_kind: str,
) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")
    baseline = _controlled_form_with_navigation()
    source_bytes = _rewrite_non_xyz_navigation(
        baseline,
        mode,
        0,
        outline=True,
        page_link=True,
    )
    candidate_bytes = _rewrite_non_xyz_navigation(
        source_bytes,
        mode,
        1,
        outline=navigation_kind == "outline",
        page_link=navigation_kind == "page_link",
    )

    source = engine.inspect_pdf_bytes(source_bytes)
    candidate = engine.inspect_pdf_bytes(candidate_bytes)
    for source_page, candidate_page in zip(
        source.template_fingerprint["pages"],
        candidate.template_fingerprint["pages"],
    ):
        assert source_page["content_sha256"] == candidate_page["content_sha256"]
        assert source_page["resources_sha256"] == candidate_page["resources_sha256"]

    collection = "outlines" if navigation_kind == "outline" else "page_links"
    source_item = source.template_fingerprint["navigation"][collection][0]
    candidate_item = candidate.template_fingerprint["navigation"][collection][0]
    assert source_item["kind"] == candidate_item["kind"]
    assert source_item["destination"] != candidate_item["destination"]
    assert source.template_fingerprint["navigation"] != candidate.template_fingerprint["navigation"]

    with pytest.raises(engine.PdfEngineError) as mismatch:
        engine.validate_template_provenance(source, candidate)
    assert mismatch.value.code == "PDF_TEMPLATE_MISMATCH"
    assert mismatch.value.status_code == 409
    assert "navigation" in mismatch.value.message
