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


def test_frontend_uses_range_streaming_and_non_destructive_watermark() -> None:
    repository_root = Path(__file__).resolve().parents[5]
    service = (repository_root / "frontend/src/services/publications.ts").read_text(encoding="utf-8")
    reader_page = (repository_root / "frontend/src/pages/manuals/PublicationsReaderPage.tsx").read_text(encoding="utf-8")
    viewer = (repository_root / "frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx").read_text(encoding="utf-8")
    styles = (repository_root / "frontend/src/pages/manuals/publicationReaderEnhancements.css").read_text(encoding="utf-8")

    assert "rangeChunkSize: 512 * 1024" in service
    assert "disableRange: false" in service
    assert "readCachedPublicationBootstrap" in reader_page
    assert "getPublicationReaderBootstrap" in reader_page
    assert "fetchPublicationBlob(viewerPdfPath)" not in reader_page
    assert "renderForms={false}" in viewer
    assert "getFieldObjects" in viewer
    assert "opacity: 0.32" in styles
    assert "pointer-events: none" in styles
    assert "content-visibility: auto" in styles
