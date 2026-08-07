from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_company_library_exposes_real_document_categories_and_connected_state() -> None:
    backend = _source("backend/amodb/apps/doc_control/workspace_library_router.py")
    frontend = _source("frontend/src/pages/documentControl/DocumentLibraryHubPage.tsx")
    service = _source("frontend/src/services/documentLibrary.ts")

    for node_type in (
        "MANUAL",
        "POLICY",
        "PROCEDURE",
        "WORK_INSTRUCTION",
        "FORM",
        "CHECKLIST",
        "REGISTER",
        "EXTERNAL_DOCUMENT",
    ):
        assert f'"{node_type}"' in backend
        assert node_type in frontend

    assert 'node_type: str | None' in backend
    assert 'km.DocumentationNode.node_type == requested' in backend
    assert '"structure_path"' in backend
    assert '"physical"' in backend
    assert '"external"' in backend
    assert '"semantic_relationships"' in backend
    assert '"integrations"' in backend
    assert '"generated_records"' in backend
    assert 'query = query.filter(or_(*access_conditions))' in backend
    assert '_scope_match(profile.access_scope_json, "user_ids"' in backend
    assert 'total = query.count()' in backend
    assert '.offset((page - 1) * per_page)' in backend
    assert '.limit(per_page)' in backend
    assert 'candidates = query.order_by(' not in backend
    assert 'payload["profile"]["access_scope"]' not in backend
    assert 'node_type: filters.nodeType' in service
    assert 'title="Company document library"' in frontend
    assert 'Physical library' in frontend
    assert 'Full tree' in frontend
    assert 'Read' in frontend


def test_richer_library_preserves_governance_work_queue_filters_and_sorting() -> None:
    backend = _source("backend/amodb/apps/doc_control/workspace_library_router.py")
    service = _source("frontend/src/services/documentLibrary.ts")
    frontend = _source("frontend/src/pages/documentControl/DocumentLibraryHubPage.tsx")
    dashboard = _source("frontend/src/pages/documentControl/DocumentGovernanceDashboardPage.tsx")

    for token in (
        "owner_user_id",
        "department_id",
        "indexing_status",
        "unresolved_ownership",
        "unresolved_relationships",
        "structure_status",
        "superseded_referenced",
    ):
        assert token in backend
        assert token in service
        assert token in frontend
    assert 'sort: str = Query(default="code"' in backend
    assert 'direction: str = Query(default="asc"' in backend
    assert 'sort: filters.sort || "code"' in service
    assert 'direction: filters.direction || "asc"' in service
    assert 'Governance queue' in frontend
    assert 'Clear queue filter' in frontend
    assert 'Sort company library' in frontend
    assert 'unresolved_ownership' in dashboard
    assert 'unresolved_relationships' in dashboard
    assert 'indexing_status' in dashboard
    assert 'structure_status' in dashboard
    assert 'superseded_referenced' in dashboard


def test_physical_controlled_copy_is_a_reusable_circulation_record() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_copy_router.py")

    assert '"RETURNED": {"TRANSFER", "LOCATION_CHANGE", "WITHDRAW", "DESTROY"}' in source
    assert 'status="ISSUED" if holder else "RETURNED"' in source
    assert '"home_location_text": location' in source
    assert 'row.holder_user_id = None' in source
    assert 'row.holder_name = None' in source
    assert 'row.due_back_at = None' in source
    assert 'action: Literal["CHECK_OUT", "CHECK_IN", "VERIFY_LOCATION"]' in source
    assert 'Custody acknowledgement is required before check-out' in source
    assert 'A future return due date is required' in source
    assert 'not _future(payload.due_back_at)' in source
    assert 'event_type = "CHECK_OUT"' in source
    assert 'event_type = "CHECK_IN"' in source
    assert 'event_type = "LOCATION_VERIFIED"' in source
    assert '"method": "PORTAL_QR_SCAN"' in source
    assert '"code": "CONTROLLED_COPY_NOOP"' in source


def test_qr_label_is_an_identifier_not_an_authorization_bypass() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_copy_router.py")
    router = _source("backend/amodb/apps/doc_control/router.py")

    assert '@router.get("/t/{tenant_slug}/controlled-copies/{copy_id}/scan")' in source
    assert 'current_user: account_models.User = Depends(get_current_active_user)' in source
    assert 'require_manual_access(current_user, profile)' in source
    assert 'holder_visible' in source
    assert 'row.holder_user_id if controller or own_copy else None' in source
    assert 'row.holder_name if controller or own_copy else None' in source
    assert 'event_payloads = []' in source
    assert 'def _reader_event_payload' in source
    assert '"from_holder_user_id": None' in source
    assert '"to_holder_user_id": None' in source
    assert 'QR is an identifier, not an access credential.' in source
    assert 'Login is required.' in source
    assert '@router.get("/t/{tenant_slug}/controlled-copies/{copy_id}/label.pdf")' in source
    assert 'require_control_user(current_user)' in source
    assert 'workspace_copy_router' in router
    assert router.index('router.include_router(\n    workspace_copy_router') < router.index('router.include_router(\n    workspace_router')


def test_physical_library_frontend_supports_shelf_scan_signoff_and_return() -> None:
    page = _source("frontend/src/pages/documentControl/DocumentLibraryCopiesPage.tsx")
    service = _source("frontend/src/services/documentLibrary.ts")
    exports = _source("frontend/src/pages/DocControlPages.tsx")

    assert 'title="Physical document library"' in page
    assert 'Register copy' in page
    assert 'QR label' in page
    assert 'Check out to me' in page
    assert 'I accept custody of this numbered controlled copy' in page
    assert 'Sign in / return' in page
    assert 'Verify location' in page
    assert 'Custody history' in page
    assert 'scanPhysicalCopy' in service
    assert 'circulatePhysicalCopy' in service
    assert 'downloadPhysicalCopyLabel' in service
    assert 'serverUtcDate' in service
    assert 'DocumentLibraryCopiesPage' in exports
    assert 'DocumentLibraryHubPage' in exports


def test_existing_tree_relationships_and_generated_records_remain_authoritative() -> None:
    tree = _source("backend/amodb/apps/doc_control/knowledge_tree_reader.py")
    governance = _source("backend/amodb/apps/doc_control/governance_service.py")
    records = _source("frontend/src/pages/documentControl/DocumentControlRecordsPage.tsx")

    assert 'read_only_hierarchy_payload' in tree
    assert 'can_read_manual(user, control_profiles.get(manual_id))' in tree
    for relation in (
        "HAS_FORM",
        "HAS_CHECKLIST",
        "GENERATES_RECORD",
        "LINKED_REGULATION",
        "LINKED_AUDIT",
        "LINKED_CAR",
        "LINKED_WORK_ORDER",
        "LINKED_AIRCRAFT_OR_COMPONENT",
    ):
        assert f'"{relation}"' in governance
    assert 'Immutable outputs created from controlled forms, checklists, and registers' in records
    assert 'Checksum verified' in records
