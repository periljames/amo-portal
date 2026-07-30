from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_one_browser_pdf_engine_owns_react_pdf_loading() -> None:
    core = _read("frontend/src/pages/manuals/PdfReaderCore.tsx")
    publication = _read("frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx")
    linked = _read("frontend/src/pages/manuals/LinkedDocumentationPanel.tsx")

    assert "<PdfDocument" in core
    assert "options={PDF_DOCUMENT_OPTIONS}" in core
    assert "options={{" not in core
    assert "<PdfDocument" not in publication
    assert "<PdfDocument" not in linked
    assert "PdfReaderCore" in publication
    assert "PdfReaderCore" in linked
    assert "fetchPublicationBlob(fileUrl)" not in core
    assert "publicationPdfSource(fileUrl)" in core


def test_optional_inspection_never_blocks_first_page() -> None:
    core = _read("frontend/src/pages/manuals/PdfReaderCore.tsx")
    load_handler = core.split("const handleDocumentLoad = useCallback", 1)[1].split("const runSearch", 1)[0]

    assert "setPageCount" in load_handler
    assert "inspectDocument(loaded)" in load_handler
    assert "await resolveOutline" not in load_handler
    assert "await loaded.getFieldObjects" not in load_handler
    assert "hasJSActions" in core
    assert "inspectionGenerationRef" in core
    assert "searchControllerRef.current?.abort()" in core


def test_forms_and_working_copies_are_governed() -> None:
    core = _read("frontend/src/pages/manuals/PdfReaderCore.tsx")
    store = _read("frontend/src/pages/manuals/pdfWorkingCopyStore.ts")

    assert "renderForms={fillMode && canFill}" in core
    assert "capabilities.can_fill" in core
    assert "capabilities.can_save_draft" in core
    assert "PDF JavaScript" in core or "hasJavaScript" in core
    assert "pdf-working-copy:v1" in store
    for partition in ("userId", "tenant", "manualId", "revisionId"):
        assert partition in store
    assert "100 * 1024 * 1024" in store
    assert ".put(row)" in store
    write_tail = store.split("export async function savePdfWorkingCopy", 1)[1].split("export async function deletePdfWorkingCopy", 1)[0]
    assert "transaction.oncomplete" in write_tail
    assert "resolve(row)" in write_tail.split("transaction.oncomplete", 1)[1]
    assert write_tail.index(".put(row)") < write_tail.index("transaction.oncomplete")


def test_shortcuts_and_dirty_state_are_scoped_to_the_engaged_reader() -> None:
    core = _read("frontend/src/pages/manuals/PdfReaderCore.tsx")
    linked = _read("frontend/src/pages/manuals/LinkedDocumentationPanel.tsx")

    assert "activePdfReaderId" in core
    assert "if (activePdfReaderId !== readerId) return" in core
    assert "onPointerDownCapture={activateReader}" in core
    assert "onFocusCapture={activateReader}" in core
    assert 'dirty ? "is-dirty"' in core
    assert "onDirtyChangeRef.current?.(dirty)" in core
    assert "onDirtyChange={setReaderDirty}" in linked


def test_output_choices_are_explicit_and_not_conflated() -> None:
    core = _read("frontend/src/pages/manuals/PdfReaderCore.tsx")
    for label in (
        "Original controlled source",
        "Editable working copy",
        "Flattened copy",
        "Submit retained record",
    ):
        assert label in core
    assert '"WORKING_COPY"' in core
    assert '"FLATTENED"' in core
    assert 'output_mode: "FLATTENED_RECORD"' in core


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
    assert "process_completed_pdf" in access
    assert "process_completed_pdf" in router
    assert "create_documentation_record" in router


def test_authorization_and_signature_guards_precede_bounded_upload_processing() -> None:
    access = _read("backend/amodb/apps/manuals/knowledge_reader_access_router.py")
    router = _read("backend/amodb/apps/manuals/pdf_reader_router.py")

    assert "async def read_bounded_pdf_upload" in router
    assert "await artifact.read(_UPLOAD_CHUNK_BYTES)" in router
    assert "len(content) > MAX_PDF_BYTES" in router

    linked_submit = access.split("async def submit_linked_resource_with_source_access", 1)[1]
    linked_read = linked_submit.index("await read_bounded_pdf_upload(artifact)")
    assert linked_submit.index("_load_authorized_reference") < linked_read
    assert linked_submit.index("detail = _authorized_linked_detail") < linked_read
    assert linked_submit.index('execution.get("requires_signature")') < linked_read

    direct_submit = router.split("async def submit_reader_working_copy", 1)[1]
    direct_read = direct_submit.index("await read_bounded_pdf_upload(artifact)")
    assert direct_submit.index("_load_direct_context") < direct_read
    assert direct_submit.index("execution.requires_signature") < direct_read
    assert direct_submit.index('capabilities["can_submit"]') < direct_read


def test_reader_routes_precede_compatibility_routes() -> None:
    composition = _read("backend/amodb/apps/manuals/router.py")
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
