from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_procurement_documents_are_tenant_scoped_and_immutable():
    source = read("amodb/apps/procurement/document_models.py")
    assert 'ForeignKey("amos.id", ondelete="CASCADE")' in source
    assert 'status = Column(' in source
    assert 'VOID = "VOID"' in source
    assert "sha256" in source
    assert "void_reason" in source
    assert "BigInteger" in source
    for field in ["physical_reference", "external_system", "dms_document_id", "verification_status"]:
        assert field in source


def test_upload_validates_size_signature_and_duplicate_content():
    source = read("amodb/apps/procurement/document_service.py")
    assert "MAX_DOCUMENT_BYTES" in source
    assert "_validate_signature" in source
    assert "This exact document is already linked" in source
    assert "relative_to(DOCUMENT_ROOT)" in source
    assert "Quality evidence requires a QMS, audit, CAR, inspection, or release reference." in source


def test_backend_exposes_document_list_upload_download_and_void_routes():
    source = read("amodb/apps/procurement/document_router.py")
    assert '@router.get("/documents"' in source
    assert '"/documents",' in source
    assert '@router.get("/documents/{document_id}/download")' in source
    assert '@router.post("/documents/{document_id}/verify"' in source
    assert '@router.post("/documents/{document_id}/void"' in source
    assert "require_roles(*DOCUMENT_CONTROL_ROLES)" in source
    assert "require_roles(*QUALITY_DOCUMENT_ROLES)" in source


def test_document_list_has_stable_pagination():
    service = read("amodb/apps/procurement/document_service.py")
    router = read("amodb/apps/procurement/document_router.py")
    assert "offset: int = 0" in service
    assert ".offset(bounded_offset)" in service
    assert "ProcurementDocument.id.desc()" in service
    assert "offset: int = Query(0, ge=0)" in router
    assert "limit: int = Query(100, ge=1, le=500)" in router
    assert "offset=offset" in router


def test_migration_extends_procurement_branch():
    source = read("amodb/alembic/versions/procure_20260803_docs.py")
    assert 'revision = "procure_20260803_docs"' in source
    assert 'down_revision = "procurement_20260803_full_domain"' in source
    assert "ProcurementDocument.__table__.create" in source


def test_quality_evidence_decisions_are_independent_and_final():
    service = read("amodb/apps/procurement/document_service.py")
    router = read("amodb/apps/procurement/document_router.py")
    assert "Only Quality may void a record flagged as Quality evidence." in service
    assert "Only evidence submitted for Quality review can receive a Quality decision." in service
    assert "The evidence uploader cannot verify or reject the same evidence." in service
    assert "The Quality evidence already has a final verification decision." in service
    assert "not record.is_quality_evidence" in service
    assert "record.verification_status != document_models.ProcurementDocumentVerificationStatus.PENDING" in service
    assert "record.uploaded_by_user_id" in service
    assert "actor_is_quality=current_user.role in" in router


def test_procurement_document_router_is_registered_with_the_api():
    inventory_package = read("amodb/apps/inventory/__init__.py")
    assert "procurement_router" in inventory_package
    assert "procurement_document_router" in inventory_package
    assert "router.include_router(procurement_document_router)" in inventory_package


def test_frontend_uses_controlled_upload_and_distinct_feedback():
    module = read("../frontend/src/pages/procurement/ProcurementModule.tsx")
    document_center = read("../frontend/src/pages/procurement/ProcurementDocumentCenter.tsx")
    service = read("../frontend/src/services/procurement.ts")
    notifications = read("../frontend/src/services/notificationPreferences.ts")
    toast = read("../frontend/src/components/feedback/ToastProvider.tsx")
    assert "Promise.allSettled" in module
    assert 'activeDepartment="procurement"' in module
    assert "ProcurementDocumentCenter" in module
    assert "currentUserId={user?.id || null}" in module
    assert "FormData" in service
    assert "Drop a completed form or supporting file" in document_center
    assert "SHA-256" in document_center
    for source in ["PHYSICAL_FORM", "DMS_CONTROLLED", "EXTERNAL_SOFTWARE"]:
        assert source in document_center
    assert "verifyProcurementDocument" in document_center
    assert "document.is_quality_evidence" in document_center
    assert 'document.verification_status === "PENDING"' in document_center
    assert "document.uploaded_by_user_id" in document_center
    assert "Load older evidence" in document_center
    assert "offset: documents.length" not in document_center
    assert "loadPage(documents.length, false)" in document_center
    assert "XMLHttpRequest" in service
    assert "xhr.upload.onprogress" in service
    assert 'params.set("offset"' in service
    assert 'params.set("limit"' in service
    assert "playNotificationCue" in notifications
    for cue in ["success", "warning", "error"]:
        assert f'cue === "{cue}"' in notifications
    assert 'aria-live={urgent ? "assertive" : "polite"}' in toast


def test_frontend_document_controls_are_accessible_and_motion_safe():
    document_center = read("../frontend/src/pages/procurement/ProcurementDocumentCenter.tsx")
    styles = read("../frontend/src/styles/procurement.css")
    workspace = ROOT / "../frontend/src/styles/procurement-workspace.css"
    if workspace.exists():
        styles += workspace.read_text(encoding="utf-8")
    service = read("../frontend/src/services/procurement.ts")
    assert 'role="dialog"' in document_center
    assert 'aria-modal="true"' in document_center
    assert 'role="alert"' in document_center
    assert 'aria-live="polite"' in document_center
    assert "prefers-reduced-motion" in styles
    assert 'xhr.upload.onprogress' in service
    assert 'timeout = 90_000' in service


def test_procurement_routes_do_not_reintroduce_stores_aliases():
    module = read("../frontend/src/pages/procurement/ProcurementModule.tsx")
    router = read("../frontend/src/router.tsx")
    preload = read("../frontend/src/app/routePreload.ts")
    inventory_router = read("amodb/apps/inventory/router.py")
    assert 'part === "stores"' not in module
    assert 'parts[2] === "procurement" || parts[2] === "stores"' not in router
    assert 'procurement(?:\\/|$)' in preload
    assert '"/purchasing/' not in inventory_router
    assert "procurement_service" not in inventory_router



def test_procurement_evidence_uses_persistent_upload_root():
    service = read("amodb/apps/procurement/document_service.py")
    environment = (ROOT.parent / ".env.example").read_text(encoding="utf-8")
    expected = "/srv/amo/uploads/procurement-documents"
    assert f'PROCUREMENT_DOCUMENT_DIR", "{expected}"' in service
    assert f"PROCUREMENT_DOCUMENT_DIR={expected}" in environment



def test_quality_evidence_decision_is_atomic_and_shared_audited():
    service = read("amodb/apps/procurement/document_service.py")
    assert ".with_for_update()" in service
    assert "audit_services.create_audit_event(" in service
    assert "audit_schemas.AuditEventCreate(" in service
    assert "after_json=detail" in service



def test_document_file_cleanup_is_transaction_boundary_safe():
    service = read("amodb/apps/procurement/document_service.py")
    router = read("amodb/apps/procurement/document_router.py")
    create_block = service.split("def create_document(", 1)[1].split("def list_documents(", 1)[0]
    route_block = router.split("def procurement_document_link(", 1)[1].split('@router.get("/documents/{document_id}/download")', 1)[0]
    assert "if target_path is not None:" in create_block
    assert "target_path.unlink(missing_ok=True)" in create_block
    assert "response = _serialize(record, amo_code)" in route_block
    assert route_block.index("response = _serialize(record, amo_code)") < route_block.index("db.commit()")
    assert "db.refresh(record)" not in route_block
    assert "except HTTPException:" in route_block
    assert route_block.count("document_service.discard_document_file(record)") == 2
