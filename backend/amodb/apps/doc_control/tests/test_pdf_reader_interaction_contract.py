from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
READER_ENTRY = REPOSITORY_ROOT / "frontend/src/pages/manuals/PdfReaderCore.tsx"
READER_CORE = REPOSITORY_ROOT / "frontend/src/pages/manuals/PdfReaderCoreV2.tsx"
READER_CONFIG = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderConfig.ts"
READER_SERVICE = REPOSITORY_ROOT / "frontend/src/services/pdfReader.ts"
READER_ENGINE = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderEngine.ts"
READER_STYLES = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderEngineV2.css"
READER_OPERATIONAL_STYLES = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderOperationalFixes.css"
READER_LAYOUT = REPOSITORY_ROOT / "frontend/src/pages/manuals/publicationReaderZoom.css"
LAYOUT_VIEWER = REPOSITORY_ROOT / "frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx"
CAPABILITY_CACHE = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfCapabilityCache.ts"
SOURCE_CACHE = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfSourceCache.ts"
PUBLICATIONS_SERVICE = REPOSITORY_ROOT / "frontend/src/services/publications.ts"
FAST_READER = REPOSITORY_ROOT / "backend/amodb/apps/manuals/publications_fast_reader_router.py"
FORM_OVERRIDE = REPOSITORY_ROOT / "backend/amodb/apps/manuals/pdf_reader_form_override_router.py"
CAPABILITY_SERVICE = REPOSITORY_ROOT / "backend/amodb/apps/doc_control/pdf_capability_service.py"
SAFE_PROCESSING = REPOSITORY_ROOT / "backend/amodb/apps/doc_control/pdf_safe_processing_service.py"
FULL_PDF_SERVICE = REPOSITORY_ROOT / "backend/amodb/apps/doc_control/pdfium_service.py"
ROUTER = REPOSITORY_ROOT / "backend/amodb/apps/manuals/router.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_reader_renders_real_canvas_pages_and_supports_all_pdf_destination_forms() -> None:
    source = _source(READER_CORE)

    assert 'renderMode="canvas"' in source
    assert 'renderMode="none"' not in source
    assert "data-page-number={page}" in source
    assert "const RENDER_RADIUS = 3" in source
    assert "setRenderWindow(page, pageCount)" in source
    assert "jump(navigationRequest.page)" in source
    assert "navigationTargetRef.current" in source
    assert "if (target !== null && page !== target) return" in source
    assert "const followPdfItem" in source
    assert "target.pageNumber" in source
    assert "target.pageIndex" in source
    assert "pdf.getDestination(destination)" in source
    assert "pdf.getPageIndex(reference)" in source
    assert 'jump(page, "smooth")' in source
    assert "onItemClick={(target: PdfItemClickTarget)" in source
    assert "renderAnnotationLayer" in source


def test_render_window_is_bounded_stable_and_prefetches_ahead() -> None:
    source = _source(READER_CORE)

    assert "radius * 2 + 1" in source
    assert "function samePages" in source
    assert "samePages(current, next) ? current : next" in source
    assert "performanceProfile.prefetchMarginPx" in source
    assert "hotPageWindow" in source
    assert "currentPageRef.current" in source


def test_fit_modes_measure_the_visible_viewport() -> None:
    source = _source(READER_CORE)

    assert "root?.clientHeight || window.innerHeight" in source
    assert 'fitMode === "PAGE"' in source
    assert 'fitMode === "WIDTH"' in source
    assert 'setFitMode("PAGE")' in source
    assert "ResizeObserver" in source


def test_reader_paints_immediately_then_revalidates_capabilities_without_remounting() -> None:
    entry = _source(READER_ENTRY)
    capability_cache = _source(CAPABILITY_CACHE)

    assert "readCachedPdfCapabilities" in entry
    assert "cachedReadOnly" in entry
    assert "READ_ONLY_FALLBACK" in entry
    assert "getPdfReaderCapabilities" in entry
    assert "cachePdfCapabilities" in entry
    assert "key={identityKey}" in entry
    assert "key={readerModeKey}" not in entry
    assert "if (!resolvedCapabilities)" not in entry
    assert "capabilities={resolvedCapabilities}" in entry
    assert "CACHE_MAX_AGE_MS" in capability_cache
    assert "window.sessionStorage" in capability_cache
    assert "can_fill: false" in entry


def test_reader_reuses_a_partitioned_persistent_pdf_source_cache() -> None:
    entry = _source(READER_ENTRY)
    source_cache = _source(SOURCE_CACHE)
    publications = _source(PUBLICATIONS_SERVICE)

    assert "readCachedPdfSource" in entry
    assert "warmPdfSourceCache" in entry
    assert "Opening cached document" in entry
    assert "URL.createObjectURL" in entry
    assert "fileUrl={cachedPdfUrl || readerFileUrl}" in entry
    assert 'CACHE_NAME = "amo-controlled-pdf-source-cache-v1"' in source_cache
    assert "MAX_USER_CACHE_BYTES" in source_cache
    assert "MAX_USER_CACHE_ENTRIES" in source_cache
    assert '"X-AMO-PDF-Owner"' in source_cache
    assert '"X-AMO-PDF-Source-SHA256"' in source_cache
    assert "reader_user" in source_cache
    assert "/^(?:blob:|data:)/i.test(path)" in publications
    assert "withCredentials: false" in publications


def test_capability_failure_keeps_reader_available_and_shows_exact_reason() -> None:
    entry = _source(READER_ENTRY)

    assert "function readOnlyFallback" in entry
    assert "error instanceof Error && error.message.trim()" in entry
    assert "The document remains available in read-only mode" in entry
    assert "setResolvedCapabilities(readOnlyFallback(error, initialCachedCapabilities))" in entry


def test_scripted_source_uses_server_sanitized_reader_but_preserves_original_download() -> None:
    entry = _source(READER_ENTRY)
    service = _source(READER_SERVICE)
    form_override = _source(FORM_OVERRIDE)

    assert "reader_pdf_url?: string | null" in service
    assert "source_has_javascript?: boolean" in service
    assert "javascript_policy?" in service
    assert "const readerFileUrl = resolvedCapabilities.reader_pdf_url || props.fileUrl" in entry
    assert "fileUrl={cachedPdfUrl || readerFileUrl}" in entry
    assert "originalDownloadUrl={props.originalDownloadUrl || props.fileUrl}" in entry
    assert 'payload["reader_pdf_url"]' in form_override
    assert "script-disabled.pdf" in form_override
    assert 'X-Publication-Source": "script-disabled-working-template"' in form_override


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
    assert "pdfJsAssetDirectorySet.has" in vite
    assert "assetPath.startsWith(allowedRoot)" in vite
    assert "application/wasm" in vite
    assert "max-age=31536000, immutable" in vite
    assert "nullopenjpeg_nowasm_fallback.js" in vite
    for directory in ("wasm", "cmaps", "standard_fonts"):
        assert directory in vite
    assert "isEvalSupported: false" in config
    assert "enableScripting: false" in config


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


def test_contents_pane_tracks_the_active_pdf_page_after_scroll_and_jump() -> None:
    layout = _source(LAYOUT_VIEWER)

    assert "function alignActiveNavigationRow" in layout
    assert 'querySelector<HTMLElement>(".publication-toc__list")' in layout
    assert 'querySelector<HTMLElement>(".publication-toc__row.active")' in layout
    assert "container.getBoundingClientRect()" in layout
    assert "container.scrollTo" in layout
    assert "attempt >= 14" in layout
    assert "[currentPage, readerNavigationRequest?.token]" in layout


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


def test_capability_route_does_not_run_full_page_provenance_scan() -> None:
    form_override = _source(FORM_OVERRIDE)
    capability_service = _source(CAPABILITY_SERVICE)
    full_service = _source(FULL_PDF_SERVICE)

    assert "inspect_pdf_capabilities_bytes" in form_override
    assert "inspection = _capability_inspection(revision)" in form_override
    assert '"template_fingerprint": None' in capability_service
    assert "_security_profile(content)" in capability_service
    assert "page.get_drawings()" not in capability_service
    assert "_page_text_spans" not in capability_service
    assert "page.get_drawings()" in full_service


def test_completed_output_strips_scripts_but_keeps_full_provenance_validation() -> None:
    form_override = _source(FORM_OVERRIDE)
    safe_processing = _source(SAFE_PROCESSING)

    assert "sanitize_pdf_javascript_bytes" in form_override
    assert "inspect_script_disabled_pdf_bytes" in form_override
    assert "flatten_script_disabled_pdf_bytes" in form_override
    assert "validate_template_provenance(expected, candidate)" in form_override
    assert "reject_visual_overlays(expected, candidate)" in form_override
    assert '"script_policy": "DISABLED_AND_STRIPPED"' in form_override
    assert "_remove_script_references(source)" in safe_processing
    assert 'document.xref_set_key(names_xref, "JavaScript", "null")' in safe_processing
    assert 'document.xref_set_key(xref, "AA", "null")' in safe_processing
    assert 'document.update_object(xref, "<< >>")' in safe_processing
    assert "garbage=1, deflate=False" in safe_processing
    assert "source.scrub(" not in safe_processing
    assert "PDF_SANITIZE_WIDGET_MISMATCH" in safe_processing
    assert "PDF_SANITIZE_LINK_MISMATCH" in safe_processing
    assert "PDF_SANITIZE_IMAGE_MISMATCH" in safe_processing
    assert "contains_unsafe_action" in safe_processing


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
    assert '@router.post("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/submit-record")' in form_override
    assert router.index("router.include_router(_pdf_reader_form_override_router)") < router.index("router.include_router(_pdf_reader_router)")
    assert router.index("router.include_router(_pdf_reader_router)") < router.index("router.include_router(_fast_reader_router)")
