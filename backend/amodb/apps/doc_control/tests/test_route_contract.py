from __future__ import annotations

from amodb.main import app


def test_document_control_override_routes_are_registered_first() -> None:
    expected_first_modules = {
        "/doc-control/workspace/t/{tenant_slug}/dashboard": "amodb.apps.doc_control.workspace_dashboard_router",
        "/doc-control/workspace/t/{tenant_slug}/documents": "amodb.apps.doc_control.workspace_library_router",
        "/doc-control/workspace/t/{tenant_slug}/documents/{manual_id}": "amodb.apps.doc_control.workspace_record_router",
        "/doc-control/workspace/t/{tenant_slug}/documents/{manual_id}/profile": "amodb.apps.doc_control.workspace_profile_router",
        "/doc-control/workspace/t/{tenant_slug}/integration-links": "amodb.apps.doc_control.workspace_integration_router",
        "/doc-control/workspace/t/{tenant_slug}/change-requests": "amodb.apps.doc_control.workspace_change_router",
        "/doc-control/workspace/t/{tenant_slug}/change-requests/{change_id}": "amodb.apps.doc_control.workspace_change_router",
        "/doc-control/workspace/t/{tenant_slug}/authority-submissions/{submission_id}": "amodb.apps.doc_control.workspace_authority_router",
        "/doc-control/workspace/t/{tenant_slug}/controlled-copies": "amodb.apps.doc_control.workspace_copy_due_router",
        "/doc-control/workspace/t/{tenant_slug}/controlled-copies/{copy_id}/events": "amodb.apps.doc_control.workspace_copy_evidence_router",
        "/doc-control/workspace/t/{tenant_slug}/distribution-campaigns": "amodb.apps.doc_control.workspace_distribution_router",
        "/doc-control/workspace/t/{tenant_slug}/distribution-campaigns/{campaign_id}/issue": "amodb.apps.doc_control.workspace_distribution_router",
        "/doc-control/workspace/t/{tenant_slug}/distribution-campaigns/{campaign_id}/acknowledge": "amodb.apps.doc_control.workspace_distribution_router",
        "/doc-control/workspace/t/{tenant_slug}/external-sources": "amodb.apps.doc_control.workspace_external_router",
        "/doc-control/workspace/t/{tenant_slug}/external-sources/{source_id}/receipts": "amodb.apps.doc_control.workspace_external_router",
        "/doc-control/workspace/t/{tenant_slug}/reviews": "amodb.apps.doc_control.workspace_review_router",
        "/doc-control/workspace/t/{tenant_slug}/reviews/{review_id}/complete": "amodb.apps.doc_control.workspace_review_router",
        "/doc-control/workspace/t/{tenant_slug}/temporary-revisions": "amodb.apps.doc_control.workspace_tr_router",
        "/doc-control/workspace/t/{tenant_slug}/temporary-revisions/{tr_id}/transition": "amodb.apps.doc_control.workspace_tr_terminal_router",
        "/doc-control/workspace/t/{tenant_slug}/workflows": "amodb.apps.doc_control.workspace_workflow_create_router",
        "/doc-control/workspace/t/{tenant_slug}/workflows/{workflow_id}/transition": "amodb.apps.doc_control.workspace_workflow_review_router",
    }
    routes = [
        route
        for route in app.routes
        if getattr(route, "path", "").startswith("/doc-control/workspace/")
    ]
    for path, expected_module in expected_first_modules.items():
        matches = [route for route in routes if route.path == path]
        assert matches, path
        assert getattr(matches[0].endpoint, "__module__", "") == expected_module