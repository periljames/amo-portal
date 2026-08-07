from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _runs_reader_backend_contracts(workflow: str) -> bool:
    complete_suite = "pytest -q amodb/apps/doc_control/tests" in workflow
    explicit_suite = all(
        test_name in workflow
        for test_name in (
            "test_pdf_reader_engine.py",
            "test_pdf_reader_source_contract.py",
            "test_pdf_reader_final_hardening.py",
        )
    )
    return complete_suite or explicit_suite


def test_one_virtualized_browser_viewer_owns_pdf_loading() -> None:
    shell = _read("frontend/src/pages/manuals/PdfReaderCoreV5.tsx")
    core = _read("frontend/src/pages/manuals/PdfReaderCoreV4.tsx")
    baseline = _read("frontend/src/pages/manuals/PdfReaderCoreV3.tsx")
    bridge = _read("frontend/src/pages/manuals/PdfReaderCore.tsx")
    publication = _read(
        "frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx"
    )
    linked = _read("frontend/src/pages/manuals/LinkedDocumentationPanel.tsx")

    assert "useVirtualizer" in core
    assert "orderedVirtualItems.map" in core
    assert "<PdfDocument" in core
    assert "<PdfPage" in core
    assert "PdfReaderCoreV4" in shell
    assert "<PdfDocument" not in shell
    assert "<PdfPage" not in shell
    assert "PdfReaderCoreV5" in bridge
    assert 'from "./PdfReaderCoreV5"' in bridge
    assert "useVirtualizer" in baseline
    assert "PdfReaderCore" in publication
    assert "PdfReaderCore" in linked


def test_integrated_reader_owns_contents_pages_and_indexed_search() -> None:
    shell = _read("frontend/src/pages/manuals/PdfReaderCoreV5.tsx")
    style = _read("frontend/src/pages/manuals/pdfReaderNavigatorV5.css")

    for label in ("Contents", "Pages", "Search", "Filter contents"):
        assert label in shell
    assert "searchPublicationReader" in shell
    assert "readCachedPublicationBootstrap" in shell
    assert "useVirtualizer" in shell
    assert "pdfv5-page-virtualizer" in shell
    assert "publication-reader-page--dense-pdf-reader" in shell
    assert "publication-reader-workspace" in style
    assert "publication-navigation" in style
    assert "publication-floating-header" in style


def test_integrated_reader_is_theme_aware_high_contrast_and_touch_safe() -> None:
    shell = _read("frontend/src/pages/manuals/PdfReaderCoreV5.tsx")
    toolbar = _read("frontend/src/pages/manuals/pdfReaderDenseToolbar.css")
    navigator = _read("frontend/src/pages/manuals/pdfReaderNavigatorV5.css")
    global_style = _read("frontend/src/styles/global.css")

    assert 'body[data-color-scheme="light"]' in global_style
    assert 'body[data-color-scheme="light"] .pdfv4-reader' in toolbar
    assert 'body[data-color-scheme="light"] .pdfv5-shell' in navigator
    for token in (
        "--pdfv4-toolbar-text",
        "--pdfv4-toolbar-muted",
        "--pdfv4-toolbar-disabled",
        "--pdfv4-focus",
        "--pdfv5-text",
        "--pdfv5-muted",
        "--pdfv5-accent",
    ):
        assert token in toolbar or token in navigator
    assert "stroke-width: 2.15" in toolbar
    assert "stroke-width: 2.15" in navigator
    assert "@media (forced-colors: active)" in toolbar
    assert "@media (forced-colors: active)" in navigator
    assert "@media (pointer: coarse)" in toolbar
    assert "@media (pointer: coarse)" in navigator
    assert "@media (max-width: 1024px)" in toolbar
    assert "@media (max-width: 760px)" in toolbar
    assert "@media (max-width: 520px)" in toolbar
    assert "@media (max-width: 760px)" in navigator
    assert "MOBILE_NAV_QUERY" in shell
    assert "initialNavigationOpen" in shell
    assert "pdfv5-mobile-scrim" in shell
    assert "pdfv5-mobile-close" in shell
    assert 'aria-label="Close document navigation"' in shell
    assert "closeMobileNavigation" in shell


def test_source_identity_and_working_copy_custody_remain_partitioned() -> None:
    core = _read("frontend/src/pages/manuals/PdfReaderCoreV4.tsx")
    bridge = _read("frontend/src/pages/manuals/PdfReaderCore.tsx")
    store = _read("frontend/src/pages/manuals/pdfWorkingCopyStore.ts")
    capabilities = _read("frontend/src/services/pdfReader.ts")
    authority = _read("frontend/src/services/pdfWorkingCopyAuthority.ts")

    assert "readerKey" in bridge
    assert "sourceMountedRef" in bridge
    assert "capabilities.source_sha256" in core
    assert "pdf-working-copy:v1" in store
    for partition in ("userId", "tenant", "manualId", "revisionId"):
        assert partition in store
    assert "100 * 1024 * 1024" in store
    assert "editedPages" in store
    assert "authoritativePdfSourceChecksum" in store
    assert "stored !== authoritative" in store
    assert "registerAuthoritativePdfSource" in capabilities
    assert "authoritativeChecksums" in authority


def test_pdfjs_runtime_assets_and_security_options_remain_packaged() -> None:
    config = _read("frontend/src/pages/manuals/pdfReaderConfig.ts")
    vite = _read("frontend/vite.config.ts")
    core = _read("frontend/src/pages/manuals/PdfReaderCoreV4.tsx")

    assert "useWasm: true" in config
    assert "wasmUrl:" in config
    assert "cMapUrl:" in config
    assert "standardFontDataUrl:" in config
    assert "__PDFJS_ASSET_VERSION__" in config
    assert "fs.cpSync" in vite
    assert "pdfJsRuntimeAssetsPlugin" in vite
    assert "isEvalSupported: false" in config
    assert "enableScripting: false" in config
    assert "enableXfa: false" in config
    assert "PDFScriptingManager" not in core


def test_dense_reader_keeps_governed_toolbar_contract() -> None:
    core = _read("frontend/src/pages/manuals/PdfReaderCoreV4.tsx")
    style = _read("frontend/src/pages/manuals/pdfReaderDenseToolbar.css")
    workflow = _read(".github/workflows/publications-reader-ci.yml")

    for icon in (
        "PanelLeft",
        "Search",
        "ArrowUp",
        "ArrowDown",
        "Bookmark",
        "Printer",
        "Download",
        "Maximize2",
        "ChevronsRight",
    ):
        assert icon in core
    for scale in (
        "Automatic Zoom",
        "Actual Size",
        "Page Fit",
        "Page Width",
        "50",
        "75",
        "100",
        "125",
        "150",
        "200",
        "300",
        "400",
    ):
        assert scale in core or scale in _read(
            "frontend/src/pages/manuals/pdfReaderToolbarModel.ts"
        )
    assert "Open File" not in core
    assert "publication-control-status" in style
    assert "publication-reader-controls > button" in style
    assert "pdfReaderToolbarModel.test.ts" in workflow


def test_server_processing_reopens_outputs_and_rejects_unsafe_pdfs() -> None:
    service = _read("backend/amodb/apps/doc_control/pdfium_service.py")
    overlay = _read(
        "backend/amodb/apps/doc_control/pdf_provenance_overlay.py"
    )
    access = _read(
        "backend/amodb/apps/manuals/knowledge_reader_access_router.py"
    )
    router = _read("backend/amodb/apps/manuals/pdf_reader_router.py")
    override = _read(
        "backend/amodb/apps/manuals/pdf_reader_form_override_router.py"
    )

    assert "FPDFPage_Flatten" in service
    assert "PDF_DYNAMIC_XFA" in service
    assert "PDF_SCRIPTED" in service
    assert "validate_template_provenance" in service
    assert "PDF_TEMPLATE_VISUAL_OVERLAY" in overlay
    assert "reject_visual_overlays(expected_source, candidate)" in router
    assert "process_completed_pdf" in access
    assert "create_documentation_record" in router
    assert "sanitize_pdf_javascript_bytes" in override
    assert "inspect_script_disabled_pdf_bytes" in override
    assert "flatten_script_disabled_pdf_bytes" in override


def test_pdfium_import_and_dependency_are_confined() -> None:
    requirements = _read("backend/requirements.txt")
    assert re.search(r"^pypdfium2==5\.12\.1$", requirements, re.MULTILINE)

    imports: list[str] = []
    for path in (ROOT / "backend/amodb").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?:import|from)\s+pypdfium2", text):
            imports.append(path.relative_to(ROOT).as_posix())
    assert sorted(imports) == sorted([
        "backend/amodb/apps/doc_control/pdf_capability_service.py",
        "backend/amodb/apps/doc_control/pdfium_service.py",
    ])


def test_reader_routes_precede_compatibility_routes() -> None:
    composition = _read("backend/amodb/apps/manuals/router.py")

    assert composition.index(
        "router.include_router(_pdf_reader_precomputed_router)"
    ) < composition.index(
        "router.include_router(_pdf_reader_form_override_router)"
    )
    assert composition.index(
        "router.include_router(_pdf_reader_form_override_router)"
    ) < composition.index("router.include_router(_pdf_reader_router)")
    assert composition.index(
        "router.include_router(_pdf_reader_router)"
    ) < composition.index("router.include_router(_fast_reader_router)")


def test_reader_ci_covers_backend_contracts_and_frontend_build() -> None:
    publications = _read(".github/workflows/publications-reader-ci.yml")
    document_control = _read(
        ".github/workflows/document-control-domain-ci.yml"
    )

    assert _runs_reader_backend_contracts(publications)
    assert _runs_reader_backend_contracts(document_control)
    for workflow in (publications, document_control):
        assert "pdfReaderEngine.test.ts" in workflow
        assert "pdfReaderToolbarModel.test.ts" in workflow
        assert "npm run build" in workflow
