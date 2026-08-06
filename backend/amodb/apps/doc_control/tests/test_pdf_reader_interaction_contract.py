from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
READER_ENTRY = REPOSITORY_ROOT / "frontend/src/pages/manuals/PdfReaderCore.tsx"
READER_CORE = REPOSITORY_ROOT / "frontend/src/pages/manuals/PdfReaderCoreV2.tsx"
READER_CONFIG = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderConfig.ts"
READER_SERVICE = REPOSITORY_ROOT / "frontend/src/services/pdfReader.ts"
READER_ENGINE = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderEngine.ts"
READER_VIRTUALIZATION = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderVirtualization.ts"
READER_STYLES = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderEngineV2.css"
READER_VIRTUAL_STYLES = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderVirtualized.css"
READER_OPERATIONAL_STYLES = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderOperationalFixes.css"
READER_LAYOUT = REPOSITORY_ROOT / "frontend/src/pages/manuals/publicationReaderZoom.css"
LAYOUT_VIEWER = REPOSITORY_ROOT / "frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx"
CAPABILITY_CACHE = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfCapabilityCache.ts"
SOURCE_CACHE = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfSourceCache.ts"
PUBLICATIONS_SERVICE = REPOSITORY_ROOT / "frontend/src/services/publications.ts"
PERFORMANCE_SERVICE = REPOSITORY_ROOT / "frontend/src/services/pdfPerformance.ts"
FAST_READER = REPOSITORY_ROOT / "backend/amodb/apps/manuals/publications_fast_reader_router.py"
FORM_OVERRIDE = REPOSITORY_ROOT / "backend/amodb/apps/manuals/pdf_reader_form_override_router.py"
CAPABILITY_SERVICE = REPOSITORY_ROOT / "backend/amodb/apps/doc_control/pdf_capability_service.py"
SAFE_PROCESSING = REPOSITORY_ROOT / "backend/amodb/apps/doc_control/pdf_safe_processing_service.py"
FULL_PDF_SERVICE = REPOSITORY_ROOT / "backend/amodb/apps/doc_control/pdfium_service.py"
UPLOAD_GUARD = REPOSITORY_ROOT / "backend/amodb/apps/manuals/upload_guard_router.py"
ROUTER = REPOSITORY_ROOT / "backend/amodb/apps/manuals/router.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_reader_uses_a_real_virtualized_page_surface() -> None:
    source = _source(READER_CORE)
    virtualization = _source(READER_VIRTUALIZATION)

    assert 'from "@tanstack/react-virtual"' in source
    assert "useVirtualizer" in source
    assert "virtualizer.getVirtualItems()" in source
    assert "virtualizer.getTotalSize()" in source
    assert 'className="pdfv2-virtual-stage"' in source
    assert "pages.map" not in source
    assert "IntersectionObserver" not in source
    assert "prioritizePdfRenderIndexes" in source
    assert "updatePdfRetainedPages" in source
    assert "selectPdfVirtualPage" in source
    assert "targetIndex" in virtualization
    assert "visibleIndexes" in virtualization


def test_page_authority_changes_only_after_the_internal_viewport_moves() -> None:
    source = _source(READER_CORE)

    jump_block = source[source.index("const jump = useCallback"):source.index("const followPdfItem")]
    assert "publishPhysicalPage" not in jump_block
    assert "virtualizer.scrollToIndex" in jump_block
    assert "setNavigationPending(page)" in jump_block
    assert "selectPdfVirtualPage" in source
    assert "publishPhysicalPage(page)" in source
    assert "onScroll={requestPhysicalSync}" in source
    assert "window.scrollBy" not in source
    assert "resolvePdfReaderScrollRoot" not in source


def test_navigation_is_not_reentrant_from_page_render_callbacks() -> None:
    source = _source(READER_CORE)

    ready_block = source[source.index("const onPageReady"):source.index("const onPageAnnotations")]
    ratio_block = source[source.index("const onPageRatio"):source.index("const onPageReady")]
    assert "jump(" not in ready_block
    assert "jump(" not in ratio_block
    assert "virtualizer.measure()" in ready_block
    assert "virtualizer.scrollToIndex" in ready_block
    assert "NAVIGATION_TIMEOUT_MS" in source


def test_canvas_is_covered_until_a_complete_frame_is_ready() -> None:
    source = _source(READER_CORE)
    styles = _source(READER_VIRTUAL_STYLES)

    assert "const [ready, setReady]" in source
    assert 'className={`pdfv2-render-cover' in source
    assert "onRenderSuccess" in source
    assert "setReady(true)" in source
    assert ".pdfv2-page-shell.is-rendering canvas" in styles
    assert "opacity: 0 !important" in styles
    assert ".pdfv2-page-shell.is-ready canvas" in styles
    assert "opacity: 1 !important" in styles
    assert ".pdfv2-render-cover" in styles


def test_reader_selects_one_final_source_before_mounting_pdfjs() -> None:
    entry = _source(READER_ENTRY)
    capability_cache = _source(CAPABILITY_CACHE)

    assert "type ReaderBootstrap" in entry
    assert "sameControlledSource" in entry
    assert "cachedSourceWithin" in entry
    assert "Preparing controlled document" in entry
    assert "sourceUrlFor" in entry
    assert "cachedReadOnly" in entry
    assert "setBootstrap" in entry
    assert "resolvedCapabilities" not in entry
    assert "readerFileUrl" not in entry
    assert "sourceCachePending" not in entry
    assert "Opening cached document" not in entry
    assert "key={identityKey}" in entry
    assert "capabilities={bootstrap.capabilities}" in entry
    assert "CACHE_MAX_AGE_MS" in capability_cache
    assert "window.sessionStorage" in capability_cache


def test_cached_capabilities_never_authorize_form_execution() -> None:
    entry = _source(READER_ENTRY)

    cached_block = entry[entry.index("function cachedReadOnly"):entry.index("function readOnlyFallback")]
    assert 'source_sha256: ""' in cached_block
    assert "can_fill: false" in cached_block
    assert "can_save_draft: false" in cached_block
    assert "can_submit: false" in cached_block
    assert "liveVerified" in entry


def test_capability_results_are_persisted_and_precomputed_after_upload() -> None:
    capability = _source(CAPABILITY_SERVICE)
    upload = _source(UPLOAD_GUARD)

    assert "CAPABILITY_CACHE_ROOT" in capability
    assert "CAPABILITY_CACHE_VERSION" in capability
    assert "_read_cached_inspection" in capability
    assert "_write_cached_inspection" in capability
    assert "os.replace(temporary, path)" in capability
    assert "warm_pdf_revision_capabilities" in capability
    assert "inspect_pdf_capabilities_bytes(content)" in capability
    assert "_safe_reader_cache_path" in capability
    assert "background_tasks.add_task(warm_pdf_revision_capabilities, revision_id)" in upload


def test_pdf_destinations_use_the_same_virtual_navigation_controller() -> None:
    source = _source(READER_CORE)

    assert "const followPdfItem" in source
    assert "target.pageNumber" in source
    assert "target.pageIndex" in source
    assert "pdf.getDestination(destination)" in source
    assert "pdf.getPageIndex(reference)" in source
    assert 'jump(page, "auto")' in source
    assert "onItemClick={(target: PdfItemClickTarget)" in source
    assert "renderAnnotationLayer" in source
    assert 'externalLinkTarget="_blank"' in source


def test_contents_pane_has_one_react_owner_and_only_scrolls_the_active_row() -> None:
    layout = _source(LAYOUT_VIEWER)

    assert "keepReactActiveRowVisible" in layout
    assert 'aria-current="page"' in layout
    assert "scrollIntoView" in layout
    assert "classList.toggle" not in layout
    assert "setAttribute(\"aria-current\"" not in layout
    assert "alignActiveNavigationRow" not in layout
    assert "onPageChange?.(pageNumber)" in layout


def test_fast_ranges_do_not_create_unbounded_canvas_concurrency() -> None:
    performance = _source(PERFORMANCE_SERVICE)

    assert "rangeChunkSize: 50 * MIB" in performance
    assert "rangeChunkSize: 20 * MIB" in performance
    assert "hotPageLimit: 12" in performance
    assert "hotPageLimit: 10" in performance
    assert "renderRadius: 4" in performance
    assert "renderRadius: 3" in performance
    assert "Network range size and canvas concurrency are separate concerns" in performance


def test_internal_reader_viewport_owns_scrolling_and_hides_incomplete_canvases() -> None:
    source = _source(READER_CORE)
    styles = _source(READER_VIRTUAL_STYLES)

    assert "viewportRef" in source
    assert "getScrollElement: () => viewportRef.current" in source
    assert "overflow-y: auto" in styles
    assert "overscroll-behavior: contain" in styles
    assert "contain: layout paint style" in styles
    assert ".publication-to-top" in styles
    assert "display: none !important" in styles


def test_jpx_images_use_packaged_pdfjs_decoders() -> None:
    config = _source(READER_CONFIG)
    vite = _source(REPOSITORY_ROOT / "frontend/vite.config.ts")

    assert "useWasm: true" in config
    assert "wasmUrl:" in config
    assert "cMapUrl:" in config
    assert "standardFontDataUrl:" in config
    assert "__PDFJS_ASSET_VERSION__" in config
    assert "fs.cpSync" in vite
    assert "pdfJsRuntimeAssetsPlugin" in vite
    assert "configureServer(server)" in vite
    assert "application/wasm" in vite
    assert "max-age=31536000, immutable" in vite
    assert "nullopenjpeg_nowasm_fallback.js" in vite
    assert "isEvalSupported: false" in config
    assert "enableScripting: false" in config


def test_acroform_widgets_remain_governed_and_fillable() -> None:
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


def test_search_uses_virtual_navigation_and_reveals_the_exact_occurrence() -> None:
    source = _source(READER_CORE)
    layout = _source(LAYOUT_VIEWER)

    assert "const revealSearchResult" in source
    assert 'querySelectorAll<HTMLElement>(".pdf-engine-search-mark")' in source
    assert "result.ordinal - 1" in source
    assert 'target.classList.add("is-active")' in source
    assert "jump(rows[0].page)" in source
    assert "routeIndexedSearchToPdf" in layout
    assert "setReaderNavigationRequest({ page: destination, token: Date.now() })" in layout


def test_source_cache_remains_partitioned_but_does_not_block_mount_indefinitely() -> None:
    entry = _source(READER_ENTRY)
    source_cache = _source(SOURCE_CACHE)
    publications = _source(PUBLICATIONS_SERVICE)

    assert "readCachedPdfSource" in entry
    assert "warmPdfSourceCache" in entry
    assert "Promise.race" in entry
    assert "timeoutMs" in entry
    assert 'CACHE_NAME = "amo-controlled-pdf-source-cache-v1"' in source_cache
    assert "MAX_USER_CACHE_BYTES" in source_cache
    assert '"X-AMO-PDF-Owner"' in source_cache
    assert '"X-AMO-PDF-Source-SHA256"' in source_cache
    assert "reader_user" in source_cache
    assert "/^(?:blob:|data:)/i.test(path)" in publications


def test_working_copy_dirty_custody_and_download_modes_are_preserved() -> None:
    source = _source(READER_CORE)
    store = _source(REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfWorkingCopyStore.ts")

    assert "dirtyRef.current" in source
    assert "editedRef.current" in source
    assert "savePdfWorkingCopy" in source
    assert "capabilities.source_sha256" in source
    assert "editedPages" in store
    assert source.count("Original PDF") == 1
    assert source.count("Editable PDF") == 1
    assert source.count("Completed form pages") == 1


def test_completed_output_keeps_script_stripping_and_full_provenance_validation() -> None:
    form_override = _source(FORM_OVERRIDE)
    safe_processing = _source(SAFE_PROCESSING)

    assert "sanitize_pdf_javascript_bytes" in form_override
    assert "inspect_script_disabled_pdf_bytes" in form_override
    assert "flatten_script_disabled_pdf_bytes" in form_override
    assert "validate_template_provenance(expected, candidate)" in form_override
    assert "reject_visual_overlays(expected, candidate)" in form_override
    assert '"script_policy": "DISABLED_AND_STRIPPED"' in form_override
    assert "_remove_script_references(source)" in safe_processing
    assert "PDF_SANITIZE_WIDGET_MISMATCH" in safe_processing
    assert "PDF_SANITIZE_LINK_MISMATCH" in safe_processing
    assert "PDF_SANITIZE_IMAGE_MISMATCH" in safe_processing


def test_backend_streaming_and_safe_form_routes_still_support_the_reader() -> None:
    fast_reader = _source(FAST_READER)
    form_override = _source(FORM_OVERRIDE)
    router = _source(ROUTER)

    assert '"Accept-Ranges": "bytes"' in fast_reader
    assert '"Content-Range"' in fast_reader
    assert "status_code=206" in fast_reader
    assert "safe_acroform" in form_override
    assert '"can_fill": safe_acroform' in form_override
    assert '@router.post("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/submit-record")' in form_override
    assert router.index("router.include_router(_pdf_reader_form_override_router)") < router.index("router.include_router(_pdf_reader_router)")
    assert router.index("router.include_router(_pdf_reader_router)") < router.index("router.include_router(_fast_reader_router)")
