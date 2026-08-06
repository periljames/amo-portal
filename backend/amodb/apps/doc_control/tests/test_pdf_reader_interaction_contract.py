from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
ENTRY = ROOT / "frontend/src/pages/manuals/PdfReaderCore.tsx"
CORE = ROOT / "frontend/src/pages/manuals/PdfReaderCoreV2.tsx"
LAYOUT = ROOT / "frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx"
STYLES = ROOT / "frontend/src/pages/manuals/pdfJsControlledViewer.css"
PRECOMPUTE = ROOT / "backend/amodb/apps/manuals/pdf_reader_precompute.py"
PRECOMPUTED_ROUTER = ROOT / "backend/amodb/apps/manuals/pdf_reader_precomputed_router.py"
UPLOAD_GUARD = ROOT / "backend/amodb/apps/manuals/upload_guard_router.py"
ROUTER = ROOT / "backend/amodb/apps/manuals/router.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_official_pdfjs_viewer_owns_virtualization_render_queue_and_links() -> None:
    source = _source(CORE)

    assert 'from "pdfjs-dist/web/pdf_viewer.mjs"' in source
    assert "new pdfjsViewer.PDFViewer" in source
    assert "new pdfjsViewer.PDFLinkService" in source
    assert "new pdfjsViewer.PDFFindController" in source
    assert "linkService.setViewer(viewer)" in source
    assert "viewer.setDocument(pdf)" in source
    assert "linkService.setDocument(pdf, null)" in source

    # The removed implementation created all page wrappers and managed its own
    # hot render set. PDF.js now owns page creation, eviction and priority.
    for removed in (
        "pages.map((page)",
        "hotPageWindow",
        "setRenderWindow",
        "primeRenderTarget",
        "RENDER_RADIUS",
        "IntersectionObserver",
        "<PdfPage",
        "<PdfDocument",
    ):
        assert removed not in source


def test_navigation_publishes_only_from_the_confirmed_physical_viewport() -> None:
    source = _source(CORE)

    navigate = source.split("const navigateToPage", 1)[1].split(
        "const applyScale", 1
    )[0]
    confirmed = source.split("const onUpdateViewArea", 1)[1].split(
        "const onPageRendered", 1
    )[0]

    assert "viewer.scrollPageIntoView({ pageNumber: page })" in navigate
    assert "publishConfirmedPage" not in navigate
    assert "updateviewarea" in source
    assert "event?.location?.pageNumber" in confirmed
    assert "publishConfirmedPage(page)" in confirmed
    assert "PAGE_TOP_OFFSET" not in source
    assert "NAVIGATION_SETTLE_MS" not in source
    assert "window.scrollBy" not in source


def test_document_source_is_resolved_once_before_pdfjs_mounts() -> None:
    entry = _source(ENTRY)
    source = _source(CORE)

    assert "Preparing controlled document" in entry
    assert "mountedSourceRef" in entry
    assert "reader_pdf_url || props.fileUrl" in entry
    assert "if (!capabilities || !stableSource)" in entry
    assert "key={`${identity.tenant}:${identity.manualId}:${identity.revisionId}:${sourceKey}`}" in entry
    assert "readCachedPdfSource" not in entry
    assert "Opening cached document" not in entry
    assert "sourceCachePending" not in entry
    assert "The immutable source key is the only document-lifecycle dependency" in source


def test_forms_remain_script_disabled_and_controlled_outputs_are_preserved() -> None:
    source = _source(CORE)

    assert "enableXfa: false" in source
    assert "isEvalSupported: false" in source
    assert "pdfjsLib.AnnotationMode.ENABLE_FORMS" in source
    assert "PDFScriptingManager" not in source
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


def test_rendering_transitions_never_force_an_unfinished_canvas_visible() -> None:
    styles = _source(STYLES)

    assert ".page:not(.is-rendered) canvas" in styles
    assert "visibility: hidden" in styles
    assert ".page canvas" in styles
    assert "background: #fff" in styles
    assert "opacity: 1 !important" not in styles
    assert "visibility: visible !important" not in styles


def test_reader_owns_a_dedicated_scroll_viewport_without_fixed_offsets() -> None:
    styles = _source(STYLES)
    source = _source(CORE)

    assert "overflow: auto" in styles
    assert "overscroll-behavior: contain" in styles
    assert 'className="pdfv2-viewport pdf-engine-viewport"' in source
    assert "position: sticky" not in styles
    assert "scroll-margin-top" not in styles
    assert "--portal-sticky-offset" not in styles
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
    # Native PDF links still use PDFLinkService, while the backend section list
    # remains stable instead of being replaced after the reader is already open.
    assert "onOutlineReady={onOutlineReady}" not in layout


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
