from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
READER_CORE = REPOSITORY_ROOT / "frontend/src/pages/manuals/PdfReaderCoreV2.tsx"
READER_ENGINE = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderEngine.ts"
READER_STYLES = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderEngineV2.css"
READER_LAYOUT = REPOSITORY_ROOT / "frontend/src/pages/manuals/publicationReaderZoom.css"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_reader_renders_real_canvas_pages_and_supports_precise_page_navigation() -> None:
    source = _source(READER_CORE)

    assert 'renderMode="canvas"' in source
    assert 'renderMode="none"' not in source
    assert "data-page-number={page}" in source
    assert "nearbyPages(page, pageCount)" in source
    assert "jump(navigationRequest.page)" in source
    assert "renderAnnotationLayer" in source


def test_fit_modes_measure_the_visible_viewport() -> None:
    source = _source(READER_CORE)

    assert "root?.clientHeight || window.innerHeight" in source
    assert 'setFitMode("PAGE")' not in source  # mode is selected through the toolbar state
    assert 'fitMode === "PAGE"' in source
    assert 'fitMode === "WIDTH"' in source
    assert "ResizeObserver" in source


def test_acroform_widgets_enable_automatically_only_for_safe_documents() -> None:
    source = _source(READER_CORE)
    stylesheet = _source(READER_STYLES)

    assert "capabilities.can_fill" in source
    assert "!capabilities.has_javascript" in source
    assert "!capabilities.is_dynamic_xfa" in source
    assert "!capabilities.encrypted" in source
    assert "renderForms={safeForm}" in source
    assert "onInput=" in source
    assert ".pdfv2-reader.is-form-active" in stylesheet
    assert "pointer-events: auto !important" in stylesheet


def test_pdf_layout_resizes_with_navigation_without_breaking_sticky_controls() -> None:
    stylesheet = _source(READER_LAYOUT)
    reader_styles = _source(READER_STYLES)

    assert "--portal-sticky-offset: 44px" in stylesheet
    assert "grid-template-columns: clamp(230px, 20vw, 320px) minmax(0, 1fr)" in stylesheet
    assert ".publication-reader-width--focus .publication-linked-layout" in stylesheet
    assert ".publication-reader-width--wide .publication-linked-layout" in stylesheet
    assert "position: sticky" in reader_styles
    assert "overflow: auto" in reader_styles


def test_working_copy_dirty_custody_and_changed_pages_are_retained() -> None:
    source = _source(READER_CORE)
    store = _source(REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfWorkingCopyStore.ts")

    assert "dirtyRef.current" in source
    assert "editedRef.current" in source
    assert "savePdfWorkingCopy" in source
    assert "capabilities.source_sha256" in source
    assert "editedPages" in store
    assert "authoritativePdfSourceChecksum" in store
    assert "stored !== authoritative" in store


def test_reader_scrolling_and_draft_finalization_are_instance_scoped() -> None:
    source = _source(READER_CORE)
    engine = _source(READER_ENGINE)

    assert 'querySelector<HTMLElement>(":scope > .pdf-engine-viewport")' in engine
    assert 'closest<HTMLElement>(".app-shell__scroll")' in engine
    assert "resolvePdfReaderScrollRoot(host)" in source
    assert "deletePdfWorkingCopy(identity)" in source
    assert "searchController.current?.abort()" in source


def test_download_menu_exposes_three_distinct_outputs() -> None:
    source = _source(READER_CORE)

    assert source.count("Original PDF") == 1
    assert source.count("Editable PDF") == 1
    assert source.count("Completed form pages") == 1
    assert "editedPages.length ? editedPages : formPages" in source
