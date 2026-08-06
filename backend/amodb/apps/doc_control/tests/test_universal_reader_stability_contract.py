from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
LAYOUT = ROOT / "frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx"
FOCUS_STYLES = ROOT / "frontend/src/pages/manuals/publicationReaderFocusMode.css"
ROADMAP = ROOT / "docs/document-control/UNIVERSAL_DOCUMENT_READER_ARCHITECTURE.md"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_navigation_request_is_a_one_shot_command_not_persistent_state() -> None:
    source = _source(LAYOUT)

    assert "clearReaderNavigationCommand" in source
    assert "dispatchReaderNavigation" in source
    assert 'root.addEventListener("scroll", releaseConsumedCommand, true)' in source
    assert 'target.closest(".pdfv3-zoom")' in source
    assert "clearReaderNavigationCommand();" in source
    assert "current?.page === pageNumber ? null : current" in source
    assert "NAVIGATION_COMMAND_TTL_MS" in source


def test_reader_mode_uses_page_level_fullscreen_with_escape_fallback() -> None:
    source = _source(LAYOUT)
    styles = _source(FOCUS_STYLES)

    assert "READER_MODE_CLASS" in source
    assert "page.requestFullscreen()" in source
    assert "document.exitFullscreen()" in source
    assert 'document.addEventListener("fullscreenchange"' in source
    assert 'event.key !== "Escape"' in source
    assert "publication-reader-mode-active" in source
    assert "Reader mode" in source
    assert "Exit reader mode" in source
    assert ".publication-reader-page--reader-mode" in styles
    assert "position: fixed !important" in styles
    assert "height: 100dvh !important" in styles
    assert ".publication-reader-workspace" in styles
    assert ".pdfv3-reader" in styles


def test_page_sharing_remains_permission_controlled() -> None:
    source = _source(LAYOUT)
    roadmap = _source(ROADMAP)

    assert "copyControlledPageLink" in source
    assert 'url.hash = `pdf-page-${currentPage}`' in source
    assert "navigator.clipboard.writeText" in source
    assert "navigator.share" not in source
    assert "possession of the URL grants no access" in roadmap
    assert "must never be uploaded automatically to a third-party social platform" in roadmap
    assert "PUBLIC_RELEASED" in roadmap


def test_universal_reader_plan_is_format_neutral_and_revision_locked() -> None:
    roadmap = _source(ROADMAP)

    for required in (
        "DocumentLocation",
        "DocumentAnnotation",
        "source_sha256",
        "PDF",
        "DOCX and ODT",
        "XLSX and ODS",
        "PPTX and ODP",
        "HTML, Markdown and plain text",
        "Images and scanned documents",
        "normalized_bbox",
        "character_range",
        "revision checksum",
        "Audit workspace capabilities",
        "Mandatory test matrix",
    ):
        assert required in roadmap

    assert "must never depend only on a transient DOM element" in roadmap
    assert "never silently moves evidence" in roadmap
    assert "no stale-navigation snap-back" in roadmap
