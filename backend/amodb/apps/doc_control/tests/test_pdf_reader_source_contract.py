from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def reader_core() -> str:
    return read("frontend/src/pages/manuals/PdfReaderCoreV3.tsx")


def runs_reader_backend_contracts(workflow: str) -> bool:
    complete = "pytest -q amodb/apps/doc_control/tests" in workflow
    explicit = all(
        name in workflow
        for name in (
            "test_pdf_reader_engine.py",
            "test_pdf_reader_source_contract.py",
            "test_pdf_reader_final_hardening.py",
            "test_pdf_reader_interaction_contract.py",
        )
    )
    return complete or explicit


def test_one_browser_engine_owns_document_loading() -> None:
    core = reader_core()
    bridge = read("frontend/src/pages/manuals/PdfReaderCore.tsx")
    publication = read("frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx")
    linked = read("frontend/src/pages/manuals/LinkedDocumentationPanel.tsx")

    assert "<PdfDocument" in core
    assert "options={PDF_DOCUMENT_OPTIONS}" in core
    assert "options={{" not in core
    assert "PdfReaderCoreV3" in bridge
    assert "<PdfDocument" not in publication
    assert "<PdfDocument" not in linked
    assert "PdfReaderCore" in publication
    assert "PdfReaderCore" in linked
    assert "publicationPdfSource(fileUrl)" in core


def test_final_source_is_selected_before_first_pdfjs_mount() -> None:
    bridge = read("frontend/src/pages/manuals/PdfReaderCore.tsx")
    assert "getPdfReaderCapabilities" in bridge
    assert "readCachedPdfCapabilities" in bridge
    assert "cachedReadOnly" in bridge
    assert "const chooseSource" in bridge
    assert "const mount" in bridge
    assert "if (!readerFileUrl)" in bridge
    assert "fileUrl={readerFileUrl}" in bridge
    assert "cachedPdfUrl || readerFileUrl" not in bridge


def test_pages_are_virtualized_instead_of_preallocating_all_wrappers() -> None:
    core = reader_core()
    assert "useVirtualizer" in core
    assert "count: pageCount" in core
    assert "getScrollElement: () => viewportRef.current" in core
    assert "virtualizer.getVirtualItems()" in core
    assert "virtualizer.scrollToIndex" in core
    assert "Array.from({ length: pageCount" not in core
    assert "IntersectionObserver" not in core


def test_forms_and_working_copies_remain_governed() -> None:
    core = reader_core()
    store = read("frontend/src/pages/manuals/pdfWorkingCopyStore.ts")
    capabilities = read("frontend/src/services/pdfReader.ts")
    authority = read("frontend/src/services/pdfWorkingCopyAuthority.ts")

    assert "renderForms={safeForm}" in core
    assert "capabilities.can_fill" in core
    assert "capabilities.can_save_draft" in core
    assert "has_javascript" in core
    assert "annotationStorage.onSetModified" in core
    assert "pdf-working-copy:v1" in store
    for partition in ("userId", "tenant", "manualId", "revisionId"):
        assert partition in store
    assert "100 * 1024 * 1024" in store
    assert ".put(row)" in store
    assert "editedPages" in store
    write_tail = store.split("export async function savePdfWorkingCopy", 1)[1].split(
        "export async function deletePdfWorkingCopy", 1
    )[0]
    assert write_tail.index(".put(row)") < write_tail.index("transaction.oncomplete")
    assert "registerAuthoritativePdfSource" in capabilities
    assert "page_numbers_json" in capabilities
    assert "authoritativePdfSourceChecksum" in store
    assert "stored !== authoritative" in store
    assert "authoritativeChecksums" in authority


def test_reader_instances_are_keyed_by_controlled_source_identity() -> None:
    publication = read("frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx")
    linked = read("frontend/src/pages/manuals/LinkedDocumentationPanel.tsx")
    assert "const readerIdentityKey = `${identity.tenant}:${identity.manualId}:${identity.revisionId}`" in publication
    assert "key={readerIdentityKey}" in publication
    assert "key={`${tenant}:${detail.target.manual_id}:${detail.target.revision_id}`}" in linked


def test_dirty_state_is_scoped_to_reader_instance() -> None:
    core = reader_core()
    linked = read("frontend/src/pages/manuals/LinkedDocumentationPanel.tsx")
    assert "onDirtyChange?.(value)" in core
    assert "dirtyRef.current" in core
    assert "onInput=" in core
    assert "data-page-number" in core
    assert "window.addEventListener(\"keydown\"" not in core
    assert "onDirtyChange={setReaderDirty}" in linked


def test_output_choices_are_explicit_and_not_conflated() -> None:
    core = reader_core()
    service = read("frontend/src/services/pdfReader.ts")
    for label in (
        "Original PDF",
        "Editable PDF",
        "Completed form pages",
        "Submit retained record",
    ):
        assert label in core
    assert '"WORKING_COPY"' in core
    assert "flattenPdfWorkingCopy" in core
    assert "editedPages.length ? editedPages : formPages" in core
    assert "page_numbers_json" in service


def test_pdfium_dependency_is_pinned_and_confined() -> None:
    requirements = read("backend/requirements.txt")
    assert re.search(r"^pypdfium2==5\.12\.1$", requirements, re.MULTILINE)
    imports: list[str] = []
    for path in (ROOT / "backend/amodb").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?:import|from)\s+pypdfium2", text):
            imports.append(path.relative_to(ROOT).as_posix())
    assert imports == [
        "backend/amodb/apps/doc_control/pdf_capability_service.py",
        "backend/amodb/apps/doc_control/pdfium_service.py",
    ]


def test_server_processing_reopens_outputs_and_rejects_unsafe_pdfs() -> None:
    service = read("backend/amodb/apps/doc_control/pdfium_service.py")
    overlay = read("backend/amodb/apps/doc_control/pdf_provenance_overlay.py")
    access = read("backend/amodb/apps/manuals/knowledge_reader_access_router.py")
    router = read("backend/amodb/apps/manuals/pdf_reader_router.py")

    assert "FPDFPage_Flatten" in service
    assert "FLAT_NORMALDISPLAY" in service
    assert "PdfDocument(output_path)" in service
    assert "output_pages != page_count" in service
    assert "PDF_DYNAMIC_XFA" in service
    assert "PDF_SCRIPTED" in service
    assert "TemporaryDirectory" in service
    assert "PDFIUM_PROCESS_TIMEOUT_SECONDS" in service
    assert "validate_template_provenance" in service
    assert "PDF_TEMPLATE_VISUAL_OVERLAY" in overlay
    assert "reject_visual_overlays(expected_source, candidate)" in router
    assert "process_completed_pdf" in access
    assert "process_completed_pdf" in router
    assert "create_documentation_record" in router


def test_async_routes_offload_blocking_pdf_work() -> None:
    access = read("backend/amodb/apps/manuals/knowledge_reader_access_router.py")
    router = read("backend/amodb/apps/manuals/pdf_reader_router.py")
    override = read("backend/amodb/apps/manuals/pdf_reader_form_override_router.py")

    for text in (router, access, override):
        assert "from starlette.concurrency import run_in_threadpool" in text
    assert "await run_in_threadpool(_changed_form_pages" in override
    assert "await run_in_threadpool(_extract_completed_pages" in override


def test_execution_scope_precedes_uploaded_bytes() -> None:
    scope = read("backend/amodb/apps/doc_control/knowledge_execution_scope.py")
    access = read("backend/amodb/apps/manuals/knowledge_reader_access_router.py")
    router = read("backend/amodb/apps/manuals/pdf_reader_router.py")

    assert 'scope.get("user_ids"' in scope
    assert 'scope.get("roles"' in scope
    assert 'scope.get("departments"' in scope
    direct = router.split("async def submit_reader_working_copy", 1)[1]
    assert direct.index("require_execution_scope(current_user, execution)") < direct.index(
        "await read_bounded_pdf_upload(artifact)"
    )
    linked = access.split("async def submit_linked_resource_with_source_access", 1)[1]
    assert linked.index("require_execution_scope(current_user, execution_profile)") < linked.index(
        "await read_bounded_pdf_upload(artifact)"
    )


def test_checksum_and_provenance_precede_record_creation() -> None:
    router = read("backend/amodb/apps/manuals/pdf_reader_router.py")
    assert "hmac.compare_digest(actual_sha256, expected_sha256)" in router
    assert "PDF_SOURCE_CHECKSUM_MISMATCH" in router
    process = router.split("def process_completed_pdf", 1)[1].split("def _load_direct_context", 1)[0]
    assert process.index("inspect_pdf_bytes(content)") < process.index("flatten_pdf_bytes(content)")
    assert process.index("validate_template_provenance") < process.index("reject_visual_overlays")
    assert process.index("reject_visual_overlays") < process.index("flatten_pdf_bytes(content)")


def test_reader_routes_precede_compatibility_routes() -> None:
    composition = read("backend/amodb/apps/manuals/router.py")
    assert composition.index("router.include_router(_pdf_reader_form_override_router)") < composition.index(
        "router.include_router(_pdf_reader_router)"
    )
    assert composition.index("router.include_router(_pdf_reader_router)") < composition.index(
        "router.include_router(_fast_reader_router)"
    )
    assert composition.index("router.include_router(_knowledge_reader_access_router)") < composition.index(
        "router.include_router(_knowledge_reader_router)"
    )


def test_reader_ci_covers_virtual_model_backend_and_build() -> None:
    publications = read(".github/workflows/publications-reader-ci.yml")
    document_control = read(".github/workflows/document-control-domain-ci.yml")
    assert runs_reader_backend_contracts(publications)
    assert runs_reader_backend_contracts(document_control)
    assert "pdfReaderEngine.test.ts" in publications
    assert "pdfReaderVirtualModel.test.ts" in publications
    for workflow in (publications, document_control):
        assert "npm run build" in workflow


def test_network_profile_keeps_20_mib_default_and_50_mib_bursts() -> None:
    performance = read("frontend/src/services/pdfPerformance.ts")
    publications = read("frontend/src/services/publications.ts")
    core = reader_core()

    assert "rangeChunkSize: 50 * MIB" in performance
    assert "rangeChunkSize: 20 * MIB" in performance
    assert "rangeChunkSize: 512 * KIB" in performance
    assert "downlink >= 25" in performance
    assert "rtt <= 80" in performance
    assert "performance.rangeChunkSize" in publications
    assert "disableAutoFetch: false" in publications
    assert "disableRange: false" in publications
    assert "disableStream: false" in publications
    assert "profile.maxDevicePixelRatio" in core
    assert "hotIndexes" in core


def test_publication_navigation_uses_unique_render_identity() -> None:
    reader = read("frontend/src/pages/manuals/PublicationsReaderPage.tsx")
    assert "renderKey: string" in reader
    assert "renderKey: `section:${section.id}:${index}`" in reader
    assert "key={item.renderKey}" in reader
    assert "navRowRefs.current[item.renderKey]" in reader
    assert "collapsed.has(item.renderKey)" in reader
