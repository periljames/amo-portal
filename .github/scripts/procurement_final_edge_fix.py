from pathlib import Path
import re
import textwrap


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected one match in {path}, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


service = Path("backend/amodb/apps/procurement/document_service.py")
router = Path("backend/amodb/apps/procurement/document_router.py")
schemas = Path("backend/amodb/apps/procurement/schemas.py")
procurement_router = Path("backend/amodb/apps/procurement/router.py")
document_center = Path("frontend/src/pages/procurement/ProcurementDocumentCenter.tsx")
document_contract = Path("backend/tests/test_procurement_document_contract.py")
frontend_contract = Path("backend/tests/test_procurement_frontend_contract.py")
module_contract = Path("backend/tests/test_procurement_module_contract.py")

# Ensure every retained file is deleted if create_document fails before returning.
service_text = service.read_text(encoding="utf-8")
function_start = service_text.index("def create_document(")
block_start = service_text.index("    if file and file.filename:\n", function_start)
block_end = service_text.index("    return record\n", block_start) + len("    return record\n")
original_block = service_text[block_start:block_end]
if "    try:\n" in original_block[:20]:
    raise SystemExit("create_document cleanup block is already wrapped")
wrapped_block = (
    "    try:\n"
    + textwrap.indent(original_block, "    ")
    + "    except Exception:\n"
    + "        if target_path is not None:\n"
    + "            target_path.unlink(missing_ok=True)\n"
    + "        raise\n"
)
service.write_text(service_text[:block_start] + wrapped_block + service_text[block_end:], encoding="utf-8")

# Keep all cleanup before a successful commit. Build the response before commit and never refresh/delete afterward.
router_text = router.read_text(encoding="utf-8")
pattern = re.compile(
    r"    record = document_service\.create_document\(\n(?P<args>.*?)\n    \)\n"
    r"    try:\n"
    r"        db\.commit\(\)\n"
    r"        db\.refresh\(record\)\n"
    r"    except Exception as exc:\n"
    r"        db\.rollback\(\)\n"
    r"        document_service\.discard_document_file\(record\)\n"
    r"        raise HTTPException\(status_code=500, detail=\"The document evidence could not be committed\.\"\) from exc\n"
    r"    return _serialize\(record, amo_code\)",
    re.DOTALL,
)
match = pattern.search(router_text)
if not match:
    raise SystemExit("Could not locate Procurement document transaction block")
args = match.group("args")
replacement = f'''    record: document_models.ProcurementDocument | None = None
    try:
        record = document_service.create_document(
{args}
        )
        response = _serialize(record, amo_code)
        db.commit()
    except HTTPException:
        db.rollback()
        if record is not None:
            document_service.discard_document_file(record)
        raise
    except Exception as exc:
        db.rollback()
        if record is not None:
            document_service.discard_document_file(record)
        raise HTTPException(status_code=500, detail="The document evidence could not be committed.") from exc
    return response'''
router.write_text(router_text[:match.start()] + replacement + router_text[match.end():], encoding="utf-8")

# Remove the deleted bypass action from the public request model and RBAC contract.
replace_once(
    schemas,
    'pattern="^(SUBMIT|TECHNICAL_APPROVE|BUDGET_APPROVE|SEND_TO_SOURCING|APPROVE|REJECT|CANCEL|CLOSE)$"',
    'pattern="^(SUBMIT|TECHNICAL_APPROVE|BUDGET_APPROVE|APPROVE|REJECT|CANCEL|CLOSE)$"',
)
replace_once(
    procurement_router,
    'if payload.action in {"SEND_TO_SOURCING", "APPROVE"} and current_user.role not in PROCUREMENT_ROLES and not current_user.is_superuser:',
    'if payload.action == "APPROVE" and current_user.role not in PROCUREMENT_ROLES and not current_user.is_superuser:',
)

# Preserve server-aligned active-only pagination after a void action.
replace_once(
    document_center,
    '      setDocuments((current) => current.map((item) => item.id === updated.id ? updated : item));',
    '''      setDocuments((current) => {
        if (mode === "VOID" && !includeVoid) {
          return current.filter((item) => item.id !== updated.id);
        }
        return current.map((item) => item.id === updated.id ? updated : item);
      });''',
)

# Focused regression contracts for all four final review findings.
document_text = document_contract.read_text(encoding="utf-8")
if "test_document_file_cleanup_is_transaction_boundary_safe" not in document_text:
    document_contract.write_text(document_text + '''


def test_document_file_cleanup_is_transaction_boundary_safe():
    service = read("amodb/apps/procurement/document_service.py")
    router = read("amodb/apps/procurement/document_router.py")
    create_block = service.split("def create_document(", 1)[1].split("def list_documents(", 1)[0]
    route_block = router.split("def procurement_document_link(", 1)[1].split("@router.get(\"/documents/{document_id}/download\")", 1)[0]
    assert "if target_path is not None:" in create_block
    assert "target_path.unlink(missing_ok=True)" in create_block
    assert "response = _serialize(record, amo_code)" in route_block
    assert route_block.index("response = _serialize(record, amo_code)") < route_block.index("db.commit()")
    assert "db.refresh(record)" not in route_block
    assert "except HTTPException:" in route_block
    assert route_block.count("document_service.discard_document_file(record)") == 2
''', encoding="utf-8")

frontend_text = frontend_contract.read_text(encoding="utf-8")
if "test_voiding_preserves_active_only_pagination_alignment" not in frontend_text:
    frontend_contract.write_text(frontend_text + '''


def test_voiding_preserves_active_only_pagination_alignment():
    documents = read("pages/procurement/ProcurementDocumentCenter.tsx")
    assert 'mode === "VOID" && !includeVoid' in documents
    assert "current.filter((item) => item.id !== updated.id)" in documents
    assert "loadPage(documents.length, false)" in documents
''', encoding="utf-8")

module_text = module_contract.read_text(encoding="utf-8")
if "test_deleted_sourcing_bypass_is_absent_from_public_api_contract" not in module_text:
    module_contract.write_text(module_text + '''


def test_deleted_sourcing_bypass_is_absent_from_public_api_contract() -> None:
    service = _read(PROCUREMENT / "service.py")
    schemas = _read(PROCUREMENT / "schemas.py")
    router = _read(PROCUREMENT / "router.py")
    assert "SEND_TO_SOURCING" not in service
    assert "SEND_TO_SOURCING" not in schemas
    assert "SEND_TO_SOURCING" not in router
''', encoding="utf-8")

# Fail the patch if any reviewed defect remains.
checks = {
    "post-commit refresh": "db.refresh(record)",
    "public sourcing bypass schema": "SEND_TO_SOURCING",
}
route_block = router.read_text(encoding="utf-8").split("def procurement_document_link(", 1)[1].split("@router.get(\"/documents/{document_id}/download\")", 1)[0]
if checks["post-commit refresh"] in route_block:
    raise SystemExit("Post-commit document refresh remains")
for path in [schemas, procurement_router]:
    if checks["public sourcing bypass schema"] in path.read_text(encoding="utf-8"):
        raise SystemExit(f"SEND_TO_SOURCING remains in {path}")
if 'mode === "VOID" && !includeVoid' not in document_center.read_text(encoding="utf-8"):
    raise SystemExit("Active-only void pagination correction is missing")
