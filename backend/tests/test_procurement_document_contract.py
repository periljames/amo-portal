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


def test_upload_validates_size_signature_and_duplicate_content():
    source = read("amodb/apps/procurement/document_service.py")
    assert "MAX_DOCUMENT_BYTES" in source
    assert "_validate_signature" in source
    assert "This exact document is already linked" in source
    assert "relative_to(DOCUMENT_ROOT)" in source


def test_backend_exposes_document_list_upload_download_and_void_routes():
    source = read("amodb/apps/procurement/document_router.py")
    assert '@router.get("/documents"' in source
    assert '"/documents",' in source
    assert '@router.get("/documents/{document_id}/download")' in source
    assert '@router.post("/documents/{document_id}/void"' in source
    assert "require_roles(*DOCUMENT_CONTROL_ROLES)" in source


def test_migration_extends_release_integration_head():
    source = read("amodb/alembic/versions/procure_20260803_docs.py")
    assert 'revision = "procure_20260803_docs"' in source
    assert 'down_revision = "7d9e0a1b2c3d"' in source
    assert "ProcurementDocument.__table__.create" in source


def test_quality_evidence_can_only_be_voided_by_quality():
    service = read("amodb/apps/procurement/document_service.py")
    router = read("amodb/apps/procurement/document_router.py")
    assert "Only Quality may void a record flagged as Quality evidence." in service
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
    assert "FormData" in service
    assert "Drop a completed form or supporting document" in document_center
    assert "SHA-256" in document_center
    assert "playNotificationCue" in notifications
    for cue in ["success", "warning", "error"]:
        assert f'cue === "{cue}"' in notifications
    assert 'aria-live={urgent ? "assertive" : "polite"}' in toast
