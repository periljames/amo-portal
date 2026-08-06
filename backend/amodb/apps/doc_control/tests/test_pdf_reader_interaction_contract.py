from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
ENTRY = ROOT / "frontend/src/pages/manuals/PdfReaderCore.tsx"
CORE = ROOT / "frontend/src/pages/manuals/PdfReaderCoreV3.tsx"
LAYOUT = ROOT / "frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx"
STYLES = ROOT / "frontend/src/pages/manuals/pdfReaderEngineV3.css"
LIVE_E2E = ROOT / "frontend/tests/e2e/publications-reader-live.spec.ts"
PRECOMPUTE = ROOT / "backend/amodb/apps/manuals/pdf_reader_precompute.py"
PRECOMPUTED_ROUTER = ROOT / "backend/amodb/apps/manuals/pdf_reader_precomputed_router.py"
UPLOAD_GUARD = ROOT / "backend/amodb/apps/manuals/upload_guard_router.py"
ROUTER = ROOT / "backend/amodb/apps/manuals/router.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_tanstack_virtualizer_owns_page_mounting_and_render_priority() -> None:
    source = _source(CORE)

    assert 'from "@tanstack/react-virtual"' in source
    assert "useVirtualizer" in source
    assert "count: pageCount" in source
    assert "getScrollElement: () => viewportRef.current" in source
    assert "rangeExtractor" in source
    assert "virtualizer.getVirtualItems()" in source
    assert "orderedVirtualItems.map" in source
    assert "hotIndexes" in source
    assert "const limit = profile.mode" in source
    assert "pages.map((page)" not in source
    assert "IntersectionObserver" not in source


def test_navigation_publishes_only_from_the_confirmed_physical_viewport() -> None:
    source = _source(CORE)

    jump = source.split("const jump", 1)[1].split("const setDirtyState", 1)[0]
    physical = source.split("const synchronizePhysicalPage", 1)[1].split(
        "const schedulePhysicalSync", 1
    )[0]

    assert "virtualizer.scrollToIndex" in jump
    assert "publishPhysicalPage" not in jump
    assert "publishPhysicalPage(closest.index + 1)" in physical
    assert "onScroll={schedulePhysicalSync}" in source
    assert "PAGE_TOP_OFFSET" not in source
    assert "window.scrollBy" not in jump


def test_document_source_is_resolved_once_before_pdf_mount() -> None:
    entry = _source(ENTRY)

    assert "Preparing controlled document" in entry
    assert "chooseSource" in entry
    assert "sourceMountedRef" in entry
    assert "cachedReadOnly" in entry
    assert "reader_pdf_url || props.fileUrl" in entry
    assert "if (!readerFileUrl)" in entry
    assert "sourceChanged || sourceUrlChanged" in entry
    assert "sourceCachePending" not in entry
    assert "Opening cached document" not in entry


def test_forms_remain_script_disabled_and_controlled_outputs_are_preserved() -> None:
    source = _source(CORE)
    config = _source(ROOT / "frontend/src/pages/manuals/pdfReaderConfig.ts")

    assert "isEvalSupported: false" in config
    assert "enableScripting: false" in config
    assert "enableXfa: false" in config
    assert "PDFScriptingManager" not in source
    assert "renderForms={safeForm}" in source
    assert "capabilities.can_fill" in source
    assert "!capabilities.has_javascript" in source
    assert "savePdfWorkingCopy" in source
    assert "capabilities.source_sha256" in source
    assert "flattenPdfWorkingCopy" in source
    assert "submitPdfWorkingCopy" in source
    for label in (
        "Original PDF",
        "Editable PDF",
        "Completed form pages",
        "Submit retained record",
    ):
        assert label in source


def test_zoom_and_first_render_hide_every_unfinished_canvas() -> None:
    source = _source(CORE)
    styles = _source(STYLES)

    assert "setReady(false)" in source
    assert "}, [page, width]);" in source
    assert "pdfv3-page-skeleton" in source
    assert "onRenderSuccess" in source
    assert ".pdfv3-page-surface" in styles
    assert "opacity: 0" in styles
    assert "visibility: hidden" in styles
    assert ".pdfv3-page.is-ready .pdfv3-page-surface" in styles
    assert "opacity: 1" in styles
    assert "background: #fff !important" in styles
    assert "visibility: visible !important" not in styles


def test_working_copy_autosave_is_generation_and_lifecycle_safe() -> None:
    source = _source(CORE)

    assert "editGenerationRef" in source
    assert "lifecycleGenerationRef" in source
    assert "autosaveInFlightRef" in source
    assert "autosaveQueuedRef" in source
    assert "isPdfWorkingCopyGenerationCurrent" in source
    assert "isPdfDraftLifecycleCurrent" in source
    assert "await deletePdfWorkingCopy(identity).catch(() => undefined)" in source
    assert "clearAutosaveTimer()" in source


def test_exact_111_page_browser_gate_covers_all_recorded_failures() -> None:
    source = _source(LIVE_E2E)

    for setting in (
        "E2E_PUBLICATION_111_PAGE_PATH",
        "E2E_PUBLICATION_TOC_TARGET",
        "E2E_PUBLICATION_TOC_TARGET_PAGE",
        "E2E_PUBLICATION_PDF_LINK_SOURCE_PAGE",
        "E2E_PUBLICATION_PDF_LINK_TARGET_PAGE",
        "E2E_PUBLICATION_FORM_PAGE",
        "E2E_PUBLICATION_FORM_FIELD_SELECTOR",
    ):
        assert setting in source
    assert 'toContainText("/ 111")' in source
    assert "expectUsableBitmap" in source
    assert "pdfv3-page-skeleton" in source
    assert "waitForPhysicalPage(page, TOC_TARGET_PAGE)" in source
    assert "waitForPhysicalPage(page, PDF_LINK_TARGET_PAGE)" in source
    assert "expectConfiguredFormValue" in source
    assert "Editable PDF" in source
    assert "Completed form pages" in source
    assert "CAPABILITY_RESPONSE_MS" in source
    assert "pdfSources.size).toBe(1)" in source


def test_reader_owns_a_dedicated_scroll_viewport_without_shell_offsets() -> None:
    styles = _source(STYLES)
    source = _source(CORE)

    assert "overflow: auto" in styles
    assert "overscroll-behavior: contain" in styles
    assert 'className="pdfv3-viewport"' in source
    assert "position: sticky" not in styles
    assert "scroll-margin-top" not in styles
    assert "PAGE_TOP_OFFSET" not in source
    assert ".publication-to-top" in styles
    assert "display: none !important" in styles


def test_contents_is_controlled_only_by_publications_reader_react_state() -> None:
    layout = _source(LAYOUT)

    assert "alignActiveNavigationRow" not in layout
    assert "classList.toggle" not in layout
    assert "aria-current" not in layout
    assert "container.scrollTo" not in layout
    assert "routeIndexedSearchToPdf" in layout
    assert "setReaderNavigationRequest" in layout
    assert "onOutlineReady={onOutlineReady}" in layout


def test_pdf_capabilities_and_safe_derivative_are_precomputed_by_checksum() -> None:
    precompute = _source(PRECOMPUTE)
    route = _source(PRECOMPUTED_ROUTER)
    upload = _source(UPLOAD_GUARD)
    composition = _source(ROUTER)

    assert "_inspection_cache_path" in precompute
    assert "source_sha256.lower()" in precompute
    assert "os.replace(temporary, target)" in precompute
    assert "cached_pdf_inspection" in precompute
    assert "_safe_reader_cache_path" in precompute
    assert "precompute_pdf_reader_assets" in upload
    assert "background_tasks.add_task(precompute_pdf_reader_assets, revision_id)" in upload
    assert "cached_pdf_inspection" in route
    assert "reader_pdf_url" in route
    assert composition.index(
        "router.include_router(_pdf_reader_precomputed_router)"
    ) < composition.index(
        "router.include_router(_pdf_reader_form_override_router)"
    )
