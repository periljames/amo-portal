from __future__ import annotations

from pathlib import Path

from amodb.main import app


ROOT = Path(__file__).resolve().parents[5]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_reports_portfolio_route_precedes_compatibility_workspace() -> None:
    path = "/doc-control/workspace/t/{tenant_slug}/reports-portfolio"
    matches = [route for route in app.routes if getattr(route, "path", "") == path]
    assert matches, path
    assert matches[0].endpoint.__module__ == "amodb.apps.doc_control.workspace_reports_portfolio_router"

    router = _source("backend/amodb/apps/doc_control/router.py")
    assert router.index("router.include_router(workspace_reports_portfolio_router") < router.index(
        "router.include_router(\n    workspace_router"
    )


def test_reports_portfolio_is_bounded_and_controller_only() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_reports_portfolio_router.py")
    assert "page: int = Query(default=1, ge=1)" in source
    assert "per_page: int = Query(default=50, ge=1, le=100)" in source
    assert "offset = (page - 1) * per_page" in source
    assert ".offset(offset).limit(per_page).all()" in source
    assert '"pagination": _pagination(page, per_page, total, len(items))' in source
    assert "require_control_user(current_user)" in source
    assert ".all()" not in source.split("manuals = query.order_by", 1)[0].split("query = db.query(manual_models.Manual)", 1)[1]


def test_reports_portfolio_uses_authoritative_exception_records() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_reports_portfolio_router.py")
    for entity in (
        "DocumentDistributionRecipient",
        "DocumentReviewPlan",
        "ExternalDocumentSource",
        "DocumentControlledCopy",
        "DocumentControlProfile",
    ):
        assert entity in source
    for key in (
        '"acknowledgements"',
        '"periodic_reviews"',
        '"external_currency"',
        '"controlled_copy_returns"',
        '"document_reviews"',
    ):
        assert key in source


def test_regulatory_mapping_migration_repairs_clean_databases_idempotently() -> None:
    source = _source("backend/amodb/alembic/versions/document_control_20260808_regulatory_mapping_schema.py")
    assert 'down_revision = "docgov_rel_20260807_merge"' in source
    assert '"regulation_catalog" not in tables' in source
    assert '"regulation_requirements" not in tables' in source
    assert '"manual_requirement_links" not in tables' in source
    assert "sa.inspect(op.get_bind()).get_table_names()" in source
    assert "ix_manual_requirement_links_revision_id" in source
