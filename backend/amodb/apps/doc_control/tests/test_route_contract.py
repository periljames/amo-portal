from __future__ import annotations

from amodb.main import app


def test_document_control_override_routes_are_registered_first() -> None:
    expected_first_modules = {
        "/doc-control/workspace/t/{tenant_slug}/dashboard": "amodb.apps.doc_control.workspace_dashboard_router",
        "/doc-control/workspace/t/{tenant_slug}/documents": "amodb.apps.doc_control.workspace_library_router",
        "/doc-control/workspace/t/{tenant_slug}/documents/{manual_id}": "amodb.apps.doc_control.workspace_record_router",
        "/doc-control/workspace/t/{tenant_slug}/workflows/{workflow_id}/transition": "amodb.apps.doc_control.workspace_workflow_router",
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
