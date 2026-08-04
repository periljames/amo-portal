from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
READER_CORE = REPOSITORY_ROOT / "frontend/src/pages/manuals/PdfReaderCoreV2.tsx"
READER_ENGINE = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderEngine.ts"
READER_STYLES = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderEngineV2.css"
READER_OPERATIONAL_STYLES = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderOperationalFixes.css"
READER_LAYOUT = REPOSITORY_ROOT / "frontend/src/pages/manuals/publicationReaderZoom.css"
LAYOUT_VIEWER = REPOSITORY_ROOT / "frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx"
FAST_READER = REPOSITORY_ROOT / "backend/amodb/apps/manuals/publications_fast_reader_router.py"
FORM_OVERRIDE = REPOSITORY_ROOT / "backend/amodb/apps/manuals/pdf_reader_form_override_router.py"
ROUTER = REPOSITORY_ROOT / "backend/amodb/apps/manuals/router.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_reader_renders_real_canvas_pages_and_supports_deterministic_navigation() -> None:
    source = _source(READER_CORE)

    assert 'renderMode="canvas"' in source
    assert 'renderMode="none"' not in source
    assert "data-page-number={page}" in source
    assert "const RENDER_RADIUS = 3" in source
    assert "setRenderWindow(page, pageCount)" in source
    assert "jump(navigationRequest.page)" in source
    assert "navigationTargetRef.current" in source
    assert "if (target !== null && page !== target) return" in source
    assert "onItemClick=" in source
    assert "if (pageNumber) jump(pageNumber)" in source
    assert "renderAnnotationLayer" in source


def test_render_window_is_bounded_stable_and_prefetches_ahead() -> None:
    source = _source(READER_CORE)

    assert "radius * 2 + 1" in source
    assert "function samePages" in source
    assert "samePages(current, next) ? current : next" in source
    assert 'rootMargin: "1200px 0px"' in source
    assert "currentPageRef.current" in source


def test_fit_modes_measure_the_visible_viewport() -> None:
    source = _source(READER_CORE)

    assert "root?.clientHeight || window.innerHeight" in source
    assert 'fitMode === "PAGE"' in source
    assert 'fitMode === "WIDTH"' in source
    assert 'setFitMode("PAGE")' in source
    assert "ResizeObserver" in source


def test_acroform_widgets_enable_automatically_only_for_safe_documents() -> None:
    source = _source(READER_CORE)
    legacy_stylesheet = _source(READER_STYLES)
    operational_stylesheet = _source(READER_OPERATIONAL_STYLES)

    assert "capabilities.can_fill" in source
    assert "capabilities.has_acroform || fieldCount > 0" in source
    assert "!capabilities.has_javascript" in source
    assert "!capabilities.is_dynamic_xfa" in source
    assert "!capabilities.encrypted" in source
    assert "renderForms={safeForm}" in source
    assert "onInput=" in source
    assert ".pdfv2-reader.is-form-active" in legacy_stylesheet
    assert ".pdfv2-reader.is-form-active .annotationLayer .widgetAnnotation" in operational_stylesheet
    assert "pointer-events: auto !important" in operational_stylesheet
    assert ".pdfv2-reader:not(.is-form-active)" in operational_stylesheet


def test_search_moves_the_document_and_the_exact_occurrence() -> None:
    source = _source(READER_CORE)
    layout = _source(LAYOUT_VIEWER)

    assert "const revealSearchResult" in source
    assert 'querySelectorAll<HTMLElement>(".pdf-engine-search-mark")' in source
    assert "result.ordinal - 1" in source
    assert 'target.classList.add("is-active")' in source
    assert "routeIndexedSearchToPdf" in layout
    assert 'target.closest(".publication-search-results button")' in layout
    assert "searchResultPage(button)" in layout
    assert "setReaderNavigationRequest({ page: destination, token: Date.now() })" in layout


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
    assert "clearNavigationTimer()" in source


def test_download_menu_exposes_three_distinct_outputs() -> None:
    source = _source(READER_CORE)

    assert source.count("Original PDF") == 1
    assert source.count("Editable PDF") == 1
    assert source.count("Completed form pages") == 1
    assert "editedPages.length ? editedPages : formPages" in source


def test_backend_streaming_and_safe_form_routes_support_the_reader() -> None:
    fast_reader = _source(FAST_READER)
    form_override = _source(FORM_OVERRIDE)
    router = _source(ROUTER)

    assert '"Accept-Ranges": "bytes"' in fast_reader
    assert '"Content-Range"' in fast_reader
    assert "status_code=206" in fast_reader
    assert "safe_acroform" in form_override
    assert '"can_fill": safe_acroform' in form_override
    assert "changed_pages or requested_form_pages" in form_override
    assert router.index("router.include_router(_pdf_reader_form_override_router)") < router.index("router.include_router(_pdf_reader_router)")
    assert router.index("router.include_router(_pdf_reader_router)") < router.index("router.include_router(_fast_reader_router)")
