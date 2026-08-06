from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
READER_ENTRY = REPOSITORY_ROOT / "frontend/src/pages/manuals/PdfReaderCore.tsx"
READER_CORE = REPOSITORY_ROOT / "frontend/src/pages/manuals/PdfReaderCoreV3.tsx"
READER_CONFIG = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderConfig.ts"
READER_SERVICE = REPOSITORY_ROOT / "frontend/src/services/pdfReader.ts"
READER_STYLES = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderEngineV3.css"
READER_MODEL = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderVirtualModel.ts"
LAYOUT_VIEWER = REPOSITORY_ROOT / "frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx"
CAPABILITY_CACHE = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfCapabilityCache.ts"
SOURCE_CACHE = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfSourceCache.ts"
PUBLICATIONS_SERVICE = REPOSITORY_ROOT / "frontend/src/services/publications.ts"
PERFORMANCE = REPOSITORY_ROOT / "frontend/src/services/pdfPerformance.ts"
WORKING_COPY_STORE = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfWorkingCopyStore.ts"
FAST_READER = REPOSITORY_ROOT / "backend/amodb/apps/manuals/publications_fast_reader_router.py"
FORM_OVERRIDE = REPOSITORY_ROOT / "backend/amodb/apps/manuals/pdf_reader_form_override_router.py"
CAPABILITY_SERVICE = REPOSITORY_ROOT / "backend/amodb/apps/doc_control/pdf_capability_service.py"
SAFE_PROCESSING = REPOSITORY_ROOT / "backend/amodb/apps/doc_control/pdf_safe_processing_service.py"
FULL_PDF_SERVICE = REPOSITORY_ROOT / "backend/amodb/apps/doc_control/pdfium_service.py"
ROUTER = REPOSITORY_ROOT / "backend/amodb/apps/manuals/router.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_reader_resolves_one_final_source_before_mounting_pdfjs() -> None:
    entry = _source(READER_ENTRY)

    assert "PdfReaderCoreV3" in entry
    assert "CACHE_LOOKUP_BUDGET_MS = 140" in entry
    assert "readCachedPdfCapabilities" in entry
    assert "cachedReadOnly" in entry
    assert "getPdfReaderCapabilities" in entry
    assert "const chooseSource" in entry
    assert "const mount" in entry
    assert "sourceChanged || sourceUrlChanged" in entry
    assert "fileUrl={readerFileUrl}" in entry
    assert "Preparing controlled document" in entry
    assert "Opening cached document" not in entry
    assert "cachedPdfUrl || readerFileUrl" not in entry


def test_reader_virtualizes_pages_in_one_internal_scroll_viewport() -> None:
    source = _source(READER_CORE)
    styles = _source(READER_STYLES)

    assert "useVirtualizer" in source
    assert "count: pageCount" in source
    assert "getScrollElement: () => viewportRef.current" in source
    assert "virtualizer.getVirtualItems()" in source
    assert "virtualizer.getTotalSize()" in source
    assert "virtualizer.measureElement(element)" in source
    assert "rangeExtractor" in source
    assert "hotIndexes" in source
    assert "Array.from({ length: pageCount" not in source
    assert "IntersectionObserver" not in source
    assert ".pdfv3-viewport" in styles
    assert "overflow: auto" in styles
    assert "contain: strict" in styles


def test_navigation_publishes_only_the_physical_virtual_page() -> None:
    source = _source(READER_CORE)
    model = _source(READER_MODEL)

    jump = source[source.index("const jump ="):source.index("const setDirtyState")]
    assert "virtualizer.scrollToIndex" in jump
    assert "setCurrentPage" not in jump
    assert "onPageChange" not in jump
    assert "publishPhysicalPage" in source
    assert "synchronizePhysicalPage" in source
    assert "viewport.scrollTop" in source
    assert "selectPhysicalVirtualPage" in model
    assert "item.start <= anchor && item.end > anchor" in model
    assert "navigationTargetRef" not in source
    assert "onRenderSuccess={() =>" in source
    assert "jump(page)" not in source[source.index("onRenderSuccess"):]


def test_pdf_destinations_search_and_page_box_use_the_same_navigation_executor() -> None:
    source = _source(READER_CORE)
    layout = _source(LAYOUT_VIEWER)

    assert "const followPdfItem" in source
    assert "target.pageNumber" in source
    assert "target.pageIndex" in source
    assert "pdf.getDestination(destination)" in source
    assert "pdf.getPageIndex(reference)" in source
    assert 'jump(page, "auto")' in source
    assert "onItemClick={(target: PdfItemClickTarget)" in source
    assert "moveSearch" in source
    assert "routeIndexedSearchToPdf" in layout
    assert "setReaderNavigationRequest({ page: destination, token: Date.now() })" in layout


def test_unfinished_canvas_is_never_exposed_as_a_black_page() -> None:
    source = _source(READER_CORE)
    styles = _source(READER_STYLES)

    assert "const [ready, setReady]" in source
    assert 'className="pdfv3-page-skeleton"' in source
    assert "onRenderSuccess" in source
    assert "setReady(true)" in source
    assert "onRenderError" in source
    assert ".pdfv3-page-surface" in styles
    assert "opacity: 0" in styles
    assert ".pdfv3-page.is-ready .pdfv3-page-surface" in styles
    assert "opacity: 1" in styles
    assert "background: #fff" in styles


def test_canvas_count_is_bounded_without_reducing_network_burst_sizes() -> None:
    source = _source(READER_CORE)
    performance = _source(PERFORMANCE)

    assert "rangeChunkSize: 20 * MIB" in performance
    assert "rangeChunkSize: 50 * MIB" in performance
    assert "hotPageLimit: 24" not in performance
    assert "hotPageLimit: 18" not in performance
    assert "maxDevicePixelRatio: 1.6" not in performance
    assert "nextHotPageIndexes" in source
    assert 'profile.mode === "burst" ? 10' in source


def test_native_acroforms_and_working_copy_custody_are_preserved() -> None:
    source = _source(READER_CORE)
    store = _source(WORKING_COPY_STORE)

    assert "capabilities.can_fill" in source
    assert "!capabilities.has_javascript" in source
    assert "!capabilities.is_dynamic_xfa" in source
    assert "!capabilities.encrypted" in source
    assert "renderForms={safeForm}" in source
    assert "annotationStorage.onSetModified" in source
    assert "savePdfWorkingCopy" in source
    assert "capabilities.source_sha256" in source
    assert "editedPagesRef.current" in source
    assert "deletePdfWorkingCopy(identity)" in source
    assert "authoritativePdfSourceChecksum" in store
    assert "stored !== authoritative" in store


def test_download_menu_keeps_original_editable_and_completed_outputs_distinct() -> None:
    source = _source(READER_CORE)

    assert source.count("Original PDF") == 1
    assert source.count("Editable PDF") == 1
    assert source.count("Completed form pages") == 1
    assert "originalDownloadUrl || fileUrl" in source
    assert "editedPages.length ? editedPages : formPages" in source
    assert "flattenPdfWorkingCopy" in source
    assert "submitPdfWorkingCopy" in source


def test_contents_has_one_react_state_authority() -> None:
    layout = _source(LAYOUT_VIEWER)

    assert "alignActiveNavigationRow" not in layout
    assert 'classList.toggle("active"' not in layout
    assert 'setAttribute("aria-current"' not in layout
    assert "onPageChange?.(pageNumber)" in layout
    assert "setCurrentPage(pageNumber)" in layout


def test_reader_does_not_overlay_the_document_with_to_top_control() -> None:
    styles = _source(READER_STYLES)

    assert ".publication-to-top" in styles
    assert "display: none !important" in styles


def test_capability_inspection_is_cached_by_immutable_source_checksum() -> None:
    service = _source(CAPABILITY_SERVICE)

    assert 'CAPABILITY_CACHE_VERSION = "v3"' in service
    assert "PDF_CAPABILITY_CACHE_DIR" in service
    assert "_read_cached_inspection(source_sha256)" in service
    assert "_write_cached_inspection(inspection)" in service
    assert "os.replace(temporary, path)" in service
    assert "Capability caching is an acceleration only" in service


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
    assert "application/wasm" in vite
    assert "max-age=31536000, immutable" in vite
    for directory in ("wasm", "cmaps", "standard_fonts"):
        assert directory in vite
    assert "isEvalSupported: false" in config
    assert "enableScripting: false" in config


def test_reader_cache_is_partitioned_and_bounded() -> None:
    source_cache = _source(SOURCE_CACHE)
    publications = _source(PUBLICATIONS_SERVICE)

    assert 'CACHE_NAME = "amo-controlled-pdf-source-cache-v1"' in source_cache
    assert "MAX_USER_CACHE_BYTES" in source_cache
    assert "MAX_USER_CACHE_ENTRIES" in source_cache
    assert '"X-AMO-PDF-Owner"' in source_cache
    assert '"X-AMO-PDF-Source-SHA256"' in source_cache
    assert "reader_user" in source_cache
    assert "/^(?:blob:|data:)/i.test(path)" in publications
    assert "withCredentials: false" in publications


def test_completed_output_keeps_security_and_provenance_validation() -> None:
    form_override = _source(FORM_OVERRIDE)
    safe_processing = _source(SAFE_PROCESSING)
    full_service = _source(FULL_PDF_SERVICE)

    assert "sanitize_pdf_javascript_bytes" in form_override
    assert "inspect_script_disabled_pdf_bytes" in form_override
    assert "flatten_script_disabled_pdf_bytes" in form_override
    assert "validate_template_provenance(expected, candidate)" in form_override
    assert "reject_visual_overlays(expected, candidate)" in form_override
    assert '"script_policy": "DISABLED_AND_STRIPPED"' in form_override
    assert "_remove_script_references(source)" in safe_processing
    assert 'document.xref_set_key(xref, "AA", "null")' in safe_processing
    assert "page.get_drawings()" in full_service


def test_backend_streaming_and_route_order_support_the_reader() -> None:
    fast_reader = _source(FAST_READER)
    form_override = _source(FORM_OVERRIDE)
    router = _source(ROUTER)

    assert '"Accept-Ranges": "bytes"' in fast_reader
    assert '"Content-Range"' in fast_reader
    assert "status_code=206" in fast_reader
    assert "safe_acroform" in form_override
    assert '"can_fill": safe_acroform' in form_override
    assert '@router.post("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/submit-record")' in form_override
    assert router.index("router.include_router(_pdf_reader_form_override_router)") < router.index(
        "router.include_router(_pdf_reader_router)"
    )
    assert router.index("router.include_router(_pdf_reader_router)") < router.index(
        "router.include_router(_fast_reader_router)"
    )
