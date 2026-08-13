from __future__ import annotations

from pathlib import Path

from amodb.main import app


ROOT = Path(__file__).resolve().parents[5]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_integration_catalog_routes_are_registered() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/doc-control/workspace/t/{tenant_slug}/integration-catalog" in paths
    assert "/doc-control/workspace/t/{tenant_slug}/integration-catalog/search" in paths


def test_catalog_search_is_allowlisted_tenant_scoped_and_bounded() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_integration_router.py")

    assert "_ALLOWED_TABLE_RULES" in source
    assert "_table_allowed(module, table.name)" in source
    assert "_tenant_column(table)" in source
    assert "require_control_user(current_user)" in source
    assert "resolve_tenant(db, tenant_slug, current_user)" in source
    assert "tenant_values = [str(tenant.amo_id), str(tenant.id)]" in source
    assert "sa.cast(tenant_column, sa.String).in_(tenant_values)" in source
    assert "Query(default=25, ge=1, le=50)" in source


def test_catalog_never_replaces_server_side_link_verification() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_integration_router.py")

    assert "def verify_source_entity(" in source
    assert "The linked source record belongs to another tenant" in source
    assert "verified_payload = payload.model_copy(" in source
    assert '"status_snapshot": verification["status_snapshot"]' in source
    assert '"metadata": {**dict(payload.metadata), **verification}' in source
