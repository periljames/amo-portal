from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _reader_core() -> str:
    return _read("frontend/src/pages/manuals/PdfReaderCoreV2.tsx")


def test_one_browser_pdf_engine_owns_react_pdf_loading() -> None:
    core = _reader_core()
    bridge = _read("frontend/src/pages/manuals/PdfReaderCore.tsx")
    publication = _read("frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx")
    linked = _read("frontend/src/pages/manuals/LinkedDocumentationPanel.tsx")

    assert "<PdfDocument" in core
    assert "options={PDF_DOCUMENT_OPTIONS}" in core
    assert "options={{" not in core
    assert "PdfReaderCoreV2" in bridge
    assert "<PdfDocument" not in publication
    assert "<PdfDocument" not in linked
    assert "PdfReaderCore" in publication
    assert "PdfReaderCore" in linked
    assert "fetchPublicationBlob(fileUrl)" not in core
    assert "publicationPdfSource(fileUrl)" in core


def test_optional_inspection_never_blocks_first_page() -> None:
    core = _reader_core()
    load_handler = core.split("const loadDocument = useCallback", 1)[1].split("const workingFile", 1)[0]

    assert "setPageCount" in load_handler
    assert "Promise.all" in load_handler
    assert load_handler.index("setPageCount") < load_handler.index("Promise.all")
    assert "getFieldObjects" in core
    assert "hasJSActions" in core
    assert ".catch(() => undefined)" in load_handler


def test_forms_and_working_copies_are_governed() -> None:
    core = _reader_core()
    store = _read("frontend/src/pages/manuals/pdfWorkingCopyStore.ts")
    capabilities = _read("frontend/src/services/pdfReader.ts")
    authority = _read("frontend/src/services/pdfWorkingCopyAuthority.ts")

    assert "renderForms={safeForm}" in core
    assert "capabilities.can_fill" in core
    assert "capabilities.can_save_draft" in core
    assert "has_javascript" in core
    assert "pdf-working-copy:v1" in store
    for partition in ("userId", "tenant", "manualId", "revisionId"):
        assert partition in store
    assert "100 * 1024 * 1024" in store
    assert ".put(row)" in store
    assert "editedPages" in store
    write_tail = store.split("export async function savePdfWorkingCopy", 1)[1].split("export async function deletePdfWorkingCopy", 1)[0]
    assert "transaction.oncomplete" in write_tail
    assert "resolve(row)" in write_tail.split("transaction.oncomplete", 1)[1]
    assert write_tail.index(".put(row)") < write_tail.index("transaction.oncomplete")

    assert "registerAuthoritativePdfSource" in capabilities
    assert "page_numbers_json" in capabilities
    assert "authoritativePdfSourceChecksum" in store
    assert "if (!authoritativePdfSourceChecksum" in store
    assert "stored !== authoritative" in store
    assert "authoritativeChecksums" in authority


def test_reader_instances_are_keyed_by_controlled_source_identity() -> None:
    publication = _read("frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx")
    linked = _read("frontend/src/pages/manuals/LinkedDocumentationPanel.tsx")

    assert "const readerIdentityKey = `${identity.tenant}:${identity.manualId}:${identity.revisionId}`" in publication
    assert "key={readerIdentityKey}" in publication
    assert "key={`${tenant}:${detail.target.manual_id}:${detail.target.revision_id}`}" in linked


def test_dirty_state_is_scoped_to_the_reader_instance() -> None:
    core = _reader_core()
    linked = _read("frontend/src/pages/manuals/LinkedDocumentationPanel.tsx")

    assert "onDirtyChange?.(value)" in core
    assert "dirtyRef.current" in core
    assert "onInput=" in core
    assert "data-page-number" in core
    assert "window.addEventListener(\"keydown\"" not in core
    assert "onDirtyChange={setReaderDirty}" in linked


def test_output_choices_are_explicit_and_not_conflated() -> None:
    core = _reader_core()
    service = _read("frontend/src/services/pdfReader.ts")
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


def test_pdfium_import_and_dependency_are_confined() -> None:
    requirements = _read("backend/requirements.txt")
    assert re.search(r"^pypdfium2==5\.12\.1$", requirements, re.MULTILINE)
    assert "pypdfium2==5.12.0" not in requirements

    imports: list[str] = []
    for path in (ROOT / "backend/amodb").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?:import|from)\s+pypdfium2", text):
            imports.append(path.relative_to(ROOT).as_posix())
    assert imports == ["backend/amodb/apps/doc_control/pdfium_service.py"]


def test_server_processing_reopens_outputs_and_rejects_unsafe_pdfs() -> None:
    service = _read("backend/amodb/apps/doc_control/pdfium_service.py")
    overlay = _read("backend/amodb/apps/doc_control/pdf_provenance_overlay.py")
    access = _read("backend/amodb/apps/manuals/knowledge_reader_access_router.py")
    router = _read("backend/amodb/apps/manuals/pdf_reader_router.py")

    assert "FPDFPage_Flatten" in service
    assert "FLAT_NORMALDISPLAY" in service
    assert "PdfDocument(output_path)" in service
    assert "output_pages != page_count" in service
    assert "PDF_DYNAMIC_XFA" in service
    assert "PDF_SCRIPTED" in service
    assert "TemporaryDirectory" in service
    assert "PDFIUM_PROCESS_TIMEOUT_SECONDS" in service
    assert "document.xref_object" in service
    assert "_decode_pdf_name_escapes" in service
    assert "_ACTION_SUBTYPE_PATTERN" in service
    for action in ("launch", "submitform", "importdata"):
        assert f'"{action}"' in service
    assert "_text_appearance_signature" in service
    assert 'completed.get("appearance") == source_word.get("appearance")' in service
    assert "validate_template_provenance" in service
    assert "template_fingerprint" in service
    assert "PDF_TEMPLATE_VISUAL_OVERLAY" in overlay
    assert "reject_visual_overlays(expected_source, candidate)" in router
    assert "process_completed_pdf" in access
    assert "process_completed_pdf" in router
    assert "create_documentation_record" in router


def test_async_pdf_routes_offload_blocking_inspection_and_flattening() -> None:
    access = _read("backend/amodb/apps/manuals/knowledge_reader_access_router.py")
    router = _read("backend/amodb/apps/manuals/pdf_reader_router.py")
    override = _read("backend/amodb/apps/manuals/pdf_reader_form_override_router.py")

    assert "from starlette.concurrency import run_in_threadpool" in router
    assert "from starlette.concurrency import run_in_threadpool" in access
    assert "from starlette.concurrency import run_in_threadpool" in override

    direct_flatten = router.split("async def flatten_reader_working_copy", 1)[1].split("@router.post", 1)[0]
    direct_submit = router.split("async def submit_reader_working_copy", 1)[1].split("@router.get", 1)[0]
    linked_submit = access.split("async def submit_linked_resource_with_source_access", 1)[1]
    for route_source in (direct_flatten, direct_submit, linked_submit):
        assert "await run_in_threadpool(_inspection, revision)" in route_source
        assert "await run_in_threadpool(" in route_source
        assert "process_completed_pdf," in route_source
        assert route_source.index("await read_bounded_pdf_upload(artifact)") < route_source.index("process_completed_pdf,")

    assert "async def flatten_completed_form_pages" in override
    assert "await run_in_threadpool(_changed_form_pages" in override
    assert "await run_in_threadpool(_extract_completed_pages" in override


def test_execution_scope_precedes_capabilities_and_uploaded_bytes() -> None:
    scope = _read("backend/amodb/apps/doc_control/knowledge_execution_scope.py")
    access = _read("backend/amodb/apps/manuals/knowledge_reader_access_router.py")
    router = _read("backend/amodb/apps/manuals/pdf_reader_router.py")

    assert 'scope.get("user_ids"' in scope
    assert 'scope.get("roles"' in scope
    assert 'scope.get("departments"' in scope
    assert "can_execute_profile(current_user, execution)" in router
    assert "require_execution_scope(current_user, execution)" in router
    assert "require_execution_scope(current_user, execution_profile)" in access

    direct_submit = router.split("async def submit_reader_working_copy", 1)[1]
    direct_read = direct_submit.index("await read_bounded_pdf_upload(artifact)")
    assert direct_submit.index("require_execution_scope(current_user, execution)") < direct_read

    linked_submit = access.split("async def submit_linked_resource_with_source_access", 1)[1]
    linked_read = linked_submit.index("await read_bounded_pdf_upload(artifact)")
    assert linked_submit.index("require_execution_scope(current_user, execution_profile)") < linked_read


def test_source_checksum_and_template_provenance_precede_record_creation() -> None:
    access = _read("backend/amodb/apps/manuals/knowledge_reader_access_router.py")
    router = _read("backend/amodb/apps/manuals/pdf_reader_router.py")

    assert "hmac.compare_digest(actual_sha256, expected_sha256)" in router
    assert "PDF_SOURCE_CHECKSUM_MISMATCH" in router
    assert "PDF_SOURCE_CHECKSUM_MISSING" in router

    process = router.split("def process_completed_pdf", 1)[1].split("def _load_direct_context", 1)[0]
    assert process.index("inspect_pdf_bytes(content)") < process.index("flatten_pdf_bytes(content)")
    assert process.index("validate_template_provenance") < process.index("reject_visual_overlays")
    assert process.index("reject_visual_overlays") < process.index("flatten_pdf_bytes(content)")

    direct_submit = router.split("async def submit_reader_working_copy", 1)[1]
    assert direct_submit.index("source_inspection = await run_in_threadpool(_inspection, revision)") < direct_submit.index("process_completed_pdf,")
    assert direct_submit.index("process_completed_pdf,") < direct_submit.index("create_documentation_record")

    linked_submit = access.split("async def submit_linked_resource_with_source_access", 1)[1]
    assert linked_submit.index("revision = _controlled_target_revision") < linked_submit.index("process_completed_pdf,")
    assert "expected_source=source_inspection" in linked_submit


def test_authorization_and_signature_guards_precede_bounded_upload_processing() -> None:
    access = _read("backend/amodb/apps/manuals/knowledge_reader_access_router.py")
    router = _read("backend/amodb/apps/manuals/pdf_reader_router.py")

    assert "async def read_bounded_pdf_upload" in router
    assert "await artifact.read(_UPLOAD_CHUNK_BYTES)" in router
    assert "len(content) > MAX_PDF_BYTES" in router

    linked_submit = access.split("async def submit_linked_resource_with_source_access", 1)[1]
    linked_read = linked_submit.index("await read_bounded_pdf_upload(artifact)")
    assert linked_submit.index("_load_authorized_reference") < linked_read
    assert linked_submit.index("detail, execution_profile = _authorized_linked_detail") < linked_read
    assert linked_submit.index('execution.get("requires_signature")') < linked_read
    assert linked_submit.index("source_inspection = await run_in_threadpool(_inspection, revision)") < linked_read

    direct_submit = router.split("async def submit_reader_working_copy", 1)[1]
    direct_read = direct_submit.index("await read_bounded_pdf_upload(artifact)")
    assert direct_submit.index("_load_direct_context") < direct_read
    assert direct_submit.index("execution.requires_signature") < direct_read
    assert direct_submit.index('capabilities["can_submit"]') < direct_read
    assert direct_submit.index("source_inspection = await run_in_threadpool(_inspection, revision)") < direct_read


def test_reader_routes_precede_compatibility_routes() -> None:
    composition = _read("backend/amodb/apps/manuals/router.py")
    assert composition.index("router.include_router(_pdf_reader_form_override_router)") < composition.index("router.include_router(_pdf_reader_router)")
    assert composition.index("router.include_router(_pdf_reader_router)") < composition.index("router.include_router(_fast_reader_router)")
    assert composition.index("router.include_router(_knowledge_reader_access_router)") < composition.index("router.include_router(_knowledge_reader_router)")


def test_reader_ci_executes_engine_and_frontend_contracts() -> None:
    publications = _read(".github/workflows/publications-reader-ci.yml")
    document_control = _read(".github/workflows/document-control-domain-ci.yml")
    for workflow in (publications, document_control):
        assert "test_pdf_reader_engine.py" in workflow
        assert "test_pdf_reader_source_contract.py" in workflow
        assert "pdfReaderEngine.test.ts" in workflow
        assert "npm run build" in workflow
    assert "pdf-capabilities" in document_control
    assert "flatten.pdf" in document_control
    assert "submit-record" in document_control
