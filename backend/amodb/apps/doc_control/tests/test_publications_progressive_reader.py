from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from amodb.apps.manuals import approved_intake_router as approved
from amodb.apps.manuals import publications_fast_reader_router as reader


def _request(range_header: str | None = None) -> Request:
    headers = []
    if range_header:
        headers.append((b"range", range_header.encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/manuals/t/tenant/manual/rev/revision/stream.pdf",
            "raw_path": b"/manuals/t/tenant/manual/rev/revision/stream.pdf",
            "root_path": "",
            "scheme": "https",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 443),
        }
    )


def _frontend(path: str) -> str:
    repository_root = Path(__file__).resolve().parents[5]
    return (repository_root / path).read_text(encoding="utf-8")


def test_exact_pdf_stream_honours_single_byte_ranges(tmp_path: Path) -> None:
    source = tmp_path / "approved.pdf"
    source.write_bytes(b"%PDF-1.7\n0123456789abcdef")

    response = reader._stream_source(
        source,
        _request("bytes=9-12"),
        filename="approved.pdf",
        cache_key="checksum-1",
    )

    assert response.status_code == 206
    assert response.media_type == "application/pdf"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-range"] == f"bytes 9-12/{source.stat().st_size}"
    assert response.headers["content-length"] == "4"
    assert response.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert response.headers["x-publication-source"] == "exact-original"
    assert response.headers["x-acroform-policy"] == "read-only"
    assert b"".join(reader._iter_file(source, 9, 12)) == source.read_bytes()[9:13]


def test_exact_pdf_stream_rejects_invalid_or_multiple_ranges(tmp_path: Path) -> None:
    source = tmp_path / "approved.pdf"
    source.write_bytes(b"%PDF-test")

    with pytest.raises(HTTPException) as caught:
        reader._stream_source(
            source,
            _request("bytes=0-1,4-5"),
            filename="approved.pdf",
            cache_key="checksum-2",
        )

    assert caught.value.status_code == 416


def test_approved_intake_requires_final_pdf_source(tmp_path: Path) -> None:
    docx = tmp_path / "manual.docx"
    docx.write_bytes(b"docx")
    revision = SimpleNamespace(source_type_enum="DOCX", source_storage_path=str(docx))

    with pytest.raises(HTTPException) as caught:
        approved._require_exact_pdf_source(revision)

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "APPROVED_INTAKE_REQUIRES_PDF"


def test_approved_intake_preserves_existing_pdf_file(tmp_path: Path) -> None:
    source = tmp_path / "kcaa-approved.pdf"
    original = b"%PDF-1.7\nsource-with-signatures-and-figures"
    source.write_bytes(original)
    revision = SimpleNamespace(source_type_enum="PDF", source_storage_path=str(source))

    resolved = approved._require_exact_pdf_source(revision)

    assert resolved == source
    assert resolved.read_bytes() == original


def test_progressive_reader_routes_precede_legacy_routes() -> None:
    from amodb.main import app

    expected = {
        "/manuals/t/{tenant_slug}/{manual_id}/rev/{revision_id}/reader-bootstrap": "amodb.apps.manuals.publications_fast_reader_router",
        "/manuals/t/{tenant_slug}/{manual_id}/rev/{revision_id}/reader-metadata": "amodb.apps.manuals.publications_fast_reader_router",
        "/manuals/t/{tenant_slug}/{manual_id}/rev/{revision_id}/stream.pdf": "amodb.apps.manuals.publications_fast_reader_router",
        "/manuals/t/{tenant_slug}/{manual_id}/rev/{revision_id}/approved-intake": "amodb.apps.manuals.approved_intake_router",
    }
    for path, expected_module in expected.items():
        matching = [route for route in app.routes if getattr(route, "path", "") == path]
        assert matching, path
        assert matching[0].endpoint.__module__ == expected_module


def test_frontend_uses_adaptive_range_streaming_and_non_destructive_watermark() -> None:
    service = _frontend("frontend/src/services/publications.ts")
    performance = _frontend("frontend/src/services/pdfPerformance.ts")
    reader_page = _frontend("frontend/src/pages/manuals/PublicationsReaderPage.tsx")
    bridge = _frontend("frontend/src/pages/manuals/PdfReaderCore.tsx")
    core = _frontend("frontend/src/pages/manuals/PdfReaderCoreV4.tsx")
    styles = _frontend("frontend/src/pages/manuals/pdfReaderEngineV3.css")

    assert "getPdfReaderPerformanceProfile" in service
    assert "rangeChunkSize: performance.rangeChunkSize" in service
    assert "512 * KIB" in performance
    assert "20 * MIB" in performance
    assert "50 * MIB" in performance
    assert "disableRange: false" in service
    assert "readCachedPublicationBootstrap" in reader_page
    assert "getPublicationReaderBootstrap" in reader_page
    assert "fetchPublicationBlob(viewerPdfPath)" not in reader_page
    assert 'renderMode="canvas"' in core
    assert "renderForms={safeForm}" in core
    assert "getFieldObjects" in core
    assert "PdfReaderCoreV4" in bridge
    assert "UNCONTROLLED DRAFT" in core
    assert "pointer-events: none" in styles
    assert "content-visibility: auto" not in styles
    assert 'renderMode="none"' not in core


def test_pdf_readers_keep_loading_inputs_stable_after_document_success() -> None:
    config = _frontend("frontend/src/pages/manuals/pdfReaderConfig.ts")
    bridge = _frontend("frontend/src/pages/manuals/PdfReaderCore.tsx")
    core = _frontend("frontend/src/pages/manuals/PdfReaderCoreV4.tsx")
    viewer = _frontend("frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx")
    linked_panel = _frontend("frontend/src/pages/manuals/LinkedDocumentationPanel.tsx")

    assert "export const PDF_DOCUMENT_OPTIONS = Object.freeze" in config
    assert "options={PDF_DOCUMENT_OPTIONS}" in core
    assert "options={{ isEvalSupported" not in core
    assert "<PdfDocument" not in viewer
    assert "<PdfDocument" not in linked_panel
    assert "PdfReaderCore" in viewer
    assert "PdfReaderCore" in linked_panel
    assert "PdfReaderCoreV4" in bridge
    assert "const loadDocument = useCallback" in core
    assert "onLoadSuccess={loadDocument}" in core
    assert "onLoadSuccess={async" not in core
    assert "onLoadError=" in core


def test_progress_refresh_does_not_clear_an_already_loaded_virtualized_pdf() -> None:
    core = _frontend("frontend/src/pages/manuals/PdfReaderCoreV4.tsx")

    assert "setPageCount(0)" not in core
    assert "const restored = clampPdfValue(initialPage, 1, count)" in core
    assert "setPageCount(count)" in core
    assert "setCurrentPage(restored)" in core
    assert "setHotIndexes([restored - 1])" in core
    assert "useVirtualizer" in core


def test_reader_renders_only_virtualized_visible_and_hot_pages() -> None:
    core = _frontend("frontend/src/pages/manuals/PdfReaderCoreV4.tsx")
    styles = _frontend("frontend/src/pages/manuals/pdfReaderEngineV3.css")

    assert "useVirtualizer" in core
    assert "orderedVirtualItems.map" in core
    assert "rangeExtractor" in core
    assert "hotIndexes" in core
    assert 'renderMode="canvas"' in core
    assert 'renderMode="none"' not in core
    assert "content-visibility" not in styles
    assert ".pdfv3-page.is-ready .pdfv3-page-surface" in styles


def test_reader_exposes_exactly_three_download_outputs() -> None:
    core = _frontend("frontend/src/pages/manuals/PdfReaderCoreV4.tsx")

    assert core.count("Original PDF") == 1
    assert core.count("Editable PDF") == 1
    assert core.count("Completed form pages") == 1
    assert "editedPages.length ? editedPages : formPages" in core
    assert "flattenPdfWorkingCopy" in core
