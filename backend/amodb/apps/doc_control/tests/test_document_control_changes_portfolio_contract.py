from __future__ import annotations

from pathlib import Path

from amodb.main import app


ROOT = Path(__file__).resolve().parents[5]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_changes_portfolio_route_is_registered_before_compatibility_workspace() -> None:
    path = "/doc-control/workspace/t/{tenant_slug}/changes-portfolio"
    matches = [route for route in app.routes if getattr(route, "path", "") == path]
    assert matches, path
    assert matches[0].endpoint.__module__ == "amodb.apps.doc_control.workspace_portfolio_router"

    router = _source("backend/amodb/apps/doc_control/router.py")
    assert router.index("router.include_router(workspace_portfolio_router") < router.index(
        "router.include_router(\n    workspace_router"
    )


def test_changes_portfolio_is_server_paginated_and_bounded() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_portfolio_router.py")

    assert "page: int = Query(default=1, ge=1)" in source
    assert "per_page: int = Query(default=50, ge=1, le=100)" in source
    assert "offset = (page - 1) * per_page" in source
    assert ".offset(offset).limit(per_page).all()" in source
    assert '"pagination": _pagination(page, per_page, total, len(items))' in source
    assert "require_control_user(current_user)" in source


def test_changes_portfolio_consolidates_lifecycle_without_changing_legacy_lists() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_portfolio_router.py")

    for view in (
        "requests",
        "draft",
        "in-review",
        "awaiting-quality",
        "awaiting-management",
        "authority",
        "temporary-revisions",
        "ready-for-release",
        "closed",
    ):
        assert f'"{view}"' in source

    assert '"kind": "CHANGE_REQUEST"' in source
    assert '"kind": "WORKFLOW"' in source
    assert '"kind": "AUTHORITY_SUBMISSION"' in source
    assert '"kind": "TEMPORARY_REVISION"' in source
    assert 'document-control/library/{manual.id}?tab=workflow' in source
    assert 'document-control/library/{manual.id}?tab=changes' in source


def test_changes_portfolio_keeps_tenant_scope_on_every_entity_query() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_portfolio_router.py")

    assert "DocumentChangeRequest.tenant_id == tenant.amo_id" in source
    assert "DocumentAuthoritySubmission.tenant_id == tenant.amo_id" in source
    assert "DocumentTemporaryRevision.tenant_id == tenant.amo_id" in source
    assert "DocumentWorkflowInstance.tenant_id == tenant.amo_id" in source
    assert "manual_models.Manual.tenant_id == tenant.id" in source
