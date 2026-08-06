from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
ENTRY = ROOT / "frontend/src/pages/manuals/PdfReaderCore.tsx"
CORE = ROOT / "frontend/src/pages/manuals/PdfReaderCoreV3.tsx"
MODEL = ROOT / "frontend/src/pages/manuals/pdfReaderVirtualModel.ts"
STYLES = ROOT / "frontend/src/pages/manuals/pdfReaderEngineV3.css"
LAYOUT = ROOT / "frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx"
CONFIG = ROOT / "frontend/src/pages/manuals/pdfReaderConfig.ts"
PERFORMANCE = ROOT / "frontend/src/services/pdfPerformance.ts"
SOURCE_CACHE = ROOT / "frontend/src/pages/manuals/pdfSourceCache.ts"
WORKING_COPY = ROOT / "frontend/src/pages/manuals/pdfWorkingCopyStore.ts"
PUBLICATIONS = ROOT / "frontend/src/services/publications.ts"
FORM_OVERRIDE = ROOT / "backend/amodb/apps/manuals/pdf_reader_form_override_router.py"
CAPABILITY_SERVICE = ROOT / "backend/amodb/apps/doc_control/pdf_capability_service.py"
SAFE_PROCESSING = ROOT / "backend/amodb/apps/doc_control/pdf_safe_processing_service.py"
FAST_READER = ROOT / "backend/amodb/apps/manuals/publications_fast_reader_router.py"
ROUTER = ROOT / "backend/amodb/apps/manuals/router.py"
VITE = ROOT / "frontend/vite.config.ts"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_reader_resolves_one_final_source_before_mounting_pdfjs() -> None:
    text = source(ENTRY)
    assert "PdfReaderCoreV3" in text
    assert "CACHE_LOOKUP_BUDGET_MS = 140" in text
    assert "readCachedPdfCapabilities" in text
    assert "getPdfReaderCapabilities" in text
    assert "const chooseSource" in text
    assert "const mount" in text
    assert "sourceChanged || sourceUrlChanged" in text
    assert "fileUrl={readerFileUrl}" in text
    assert "Opening cached document" not in text
    assert "cachedPdfUrl || readerFileUrl" not in text


def test_reader_uses_real_virtualization_and_one_scroll_owner() -> None:
    text = source(CORE)
    css = source(STYLES)
    assert "useVirtualizer" in text
    assert "count: pageCount" in text
    assert "getScrollElement: () => viewportRef.current" in text
    assert "virtualizer.getVirtualItems()" in text
    assert "virtualizer.getTotalSize()" in text
    assert "virtualizer.measureElement(element)" in text
    assert "rangeExtractor" in text
    assert "Array.from({ length: pageCount" not in text
    assert "IntersectionObserver" not in text
    assert ".pdfv3-viewport" in css
    assert "overflow: auto" in css
    assert "contain: strict" in css


def test_toolbar_page_changes_only_after_physical_virtual_scroll() -> None:
    text = source(CORE)
    model = source(MODEL)
    jump = text[text.index("const jump ="):text.index("const setDirtyState")]
    assert "virtualizer.scrollToIndex" in jump
    assert "setCurrentPage" not in jump
    assert "onPageChange" not in jump
    assert "publishPhysicalPage" in text
    assert "synchronizePhysicalPage" in text
    assert "viewport.scrollTop" in text
    assert "selectPhysicalVirtualPage" in model
    assert "item.start <= anchor && item.end > anchor" in model
    assert "navigationTargetRef" not in text


def test_all_navigation_paths_share_the_virtual_jump_executor() -> None:
    text = source(CORE)
    layout = source(LAYOUT)
    assert "const followPdfItem" in text
    assert "target.pageNumber" in text
    assert "target.pageIndex" in text
    assert "pdf.getDestination(destination)" in text
    assert "pdf.getPageIndex(reference)" in text
    assert 'jump(page, "auto")' in text
    assert "onItemClick={(target: PdfItemClickTarget)" in text
    assert "moveSearch" in text
    assert "routeIndexedSearchToPdf" in layout
    assert "setReaderNavigationRequest({ page: destination, token: Date.now() })" in layout


def test_render_callbacks_cannot_recursively_restart_navigation() -> None:
    text = source(CORE)
    render_success = text[text.index("onRenderSuccess"):text.index("onRenderError")]
    assert "setReady(true)" in render_success
    assert "jump(" not in render_success
    assert "navigationTargetRef" not in text


def test_unfinished_canvas_is_masked_until_render_success() -> None:
    text = source(CORE)
    css = source(STYLES)
    assert "const [ready, setReady]" in text
    assert 'className="pdfv3-page-skeleton"' in text
    assert "onRenderSuccess" in text
    assert "setReady(true)" in text
    assert "onRenderError" in text
    assert ".pdfv3-page-surface" in css
    assert "opacity: 0" in css
    assert ".pdfv3-page.is-ready .pdfv3-page-surface" in css
    assert "opacity: 1" in css
    assert "background: #fff" in css


def test_network_bursts_are_preserved_but_canvas_pressure_is_bounded() -> None:
    text = source(CORE)
    performance = source(PERFORMANCE)
    assert "rangeChunkSize: 20 * MIB" in performance
    assert "rangeChunkSize: 50 * MIB" in performance
    assert "hotPageLimit: 24" not in performance
    assert "hotPageLimit: 18" not in performance
    assert "maxDevicePixelRatio: 1.6" not in performance
    assert "hotIndexes" in text
    assert 'profile.mode === "burst" ? 10' in text


def test_native_forms_and_draft_custody_are_preserved() -> None:
    text = source(CORE)
    store = source(WORKING_COPY)
    assert "capabilities.can_fill" in text
    assert "!capabilities.has_javascript" in text
    assert "!capabilities.is_dynamic_xfa" in text
    assert "!capabilities.encrypted" in text
    assert "renderForms={safeForm}" in text
    assert "annotationStorage.onSetModified" in text
    assert "savePdfWorkingCopy" in text
    assert "capabilities.source_sha256" in text
    assert "editedPagesRef.current" in text
    assert "deletePdfWorkingCopy(identity)" in text
    assert "authoritativePdfSourceChecksum" in store
    assert "stored !== authoritative" in store


def test_download_outputs_remain_distinct_and_governed() -> None:
    text = source(CORE)
    assert text.count("Original PDF") == 1
    assert text.count("Editable PDF") == 1
    assert text.count("Completed form pages") == 1
    assert "originalDownloadUrl || fileUrl" in text
    assert "editedPages.length ? editedPages : formPages" in text
    assert "flattenPdfWorkingCopy" in text
    assert "submitPdfWorkingCopy" in text


def test_contents_has_one_react_state_authority() -> None:
    text = source(LAYOUT)
    assert "alignActiveNavigationRow" not in text
    assert 'classList.toggle("active"' not in text
    assert 'setAttribute("aria-current"' not in text
    assert "setCurrentPage(pageNumber)" in text
    assert "onPageChange?.(pageNumber)" in text


def test_pdf_layout_does_not_overlay_document_content() -> None:
    css = source(STYLES)
    assert ".publication-to-top" in css
    assert "display: none !important" in css


def test_capabilities_are_cached_by_immutable_checksum() -> None:
    text = source(CAPABILITY_SERVICE)
    assert 'CAPABILITY_CACHE_VERSION = "v3"' in text
    assert "PDF_CAPABILITY_CACHE_DIR" in text
    assert "_read_cached_inspection(source_sha256)" in text
    assert "_write_cached_inspection(inspection)" in text
    assert "os.replace(temporary, path)" in text
    assert "Capability caching is an acceleration only" in text


def test_pdfjs_runtime_assets_cover_scans_cmaps_and_fonts() -> None:
    config = source(CONFIG)
    vite = source(VITE)
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


def test_source_cache_is_partitioned_and_bounded() -> None:
    cache = source(SOURCE_CACHE)
    publications = source(PUBLICATIONS)
    assert 'CACHE_NAME = "amo-controlled-pdf-source-cache-v1"' in cache
    assert "MAX_USER_CACHE_BYTES" in cache
    assert "MAX_USER_CACHE_ENTRIES" in cache
    assert '"X-AMO-PDF-Owner"' in cache
    assert '"X-AMO-PDF-Source-SHA256"' in cache
    assert "reader_user" in cache
    assert "/^(?:blob:|data:)/i.test(path)" in publications
    assert "withCredentials: false" in publications


def test_completed_output_keeps_security_and_provenance_validation() -> None:
    override = source(FORM_OVERRIDE)
    safe = source(SAFE_PROCESSING)
    assert "sanitize_pdf_javascript_bytes" in override
    assert "inspect_script_disabled_pdf_bytes" in override
    assert "flatten_script_disabled_pdf_bytes" in override
    assert "validate_template_provenance(expected, candidate)" in override
    assert "reject_visual_overlays(expected, candidate)" in override
    assert '"script_policy": "DISABLED_AND_STRIPPED"' in override
    assert "_remove_script_references(source)" in safe
    assert 'document.xref_set_key(xref, "AA", "null")' in safe


def test_backend_range_streaming_and_route_order_remain_valid() -> None:
    fast = source(FAST_READER)
    override = source(FORM_OVERRIDE)
    router = source(ROUTER)
    assert '"Accept-Ranges": "bytes"' in fast
    assert '"Content-Range"' in fast
    assert "status_code=206" in fast
    assert "safe_acroform" in override
    assert '"can_fill": safe_acroform' in override
    assert '@router.post("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/submit-record")' in override
    assert router.index("router.include_router(_pdf_reader_form_override_router)") < router.index(
        "router.include_router(_pdf_reader_router)"
    )
    assert router.index("router.include_router(_pdf_reader_router)") < router.index(
        "router.include_router(_fast_reader_router)"
    )
