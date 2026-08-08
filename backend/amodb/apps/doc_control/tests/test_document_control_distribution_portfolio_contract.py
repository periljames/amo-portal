from __future__ import annotations

from pathlib import Path

from amodb.main import app


ROOT = Path(__file__).resolve().parents[5]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_distribution_portfolio_route_is_registered_before_compatibility_workspace() -> None:
    path = "/doc-control/workspace/t/{tenant_slug}/distribution-portfolio"
    matches = [route for route in app.routes if getattr(route, "path", "") == path]
    assert matches, path
    assert matches[0].endpoint.__module__ == "amodb.apps.doc_control.workspace_distribution_portfolio_router"

    router = _source("backend/amodb/apps/doc_control/router.py")
    assert router.index("router.include_router(workspace_distribution_portfolio_router") < router.index(
        "router.include_router(\n    workspace_router"
    )


def test_distribution_portfolio_is_server_paginated_bounded_and_controller_only() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_distribution_portfolio_router.py")

    assert "page: int = Query(default=1, ge=1)" in source
    assert "per_page: int = Query(default=50, ge=1, le=100)" in source
    assert "offset = (page - 1) * per_page" in source
    assert ".offset(offset).limit(per_page).all()" in source
    assert '"pagination": _pagination(page, per_page, total, len(items))' in source
    assert "require_control_user(current_user)" in source


def test_distribution_portfolio_keeps_authoritative_distribution_and_custody_states() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_distribution_portfolio_router.py")

    for view in (
        "campaigns",
        "pending-acknowledgements",
        "overdue-acknowledgements",
        "physical-copies",
        "recalls",
    ):
        assert f'"{view}"' in source
    assert 'DocumentDistributionRecipient.status == "PENDING"' in source
    assert 'DocumentControlledCopy.status == "RECALLED"' in source
    assert 'row.status == "ISSUED"' in source
    assert 'display_status = "OVERDUE"' in source
    assert '"custody_status": row.status' in source


def test_distribution_portfolio_batches_campaign_recipient_counts() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_distribution_portfolio_router.py")

    assert "campaign_ids = [row.id for row, _manual in rows]" in source
    assert "DocumentDistributionRecipient.campaign_id.in_(campaign_ids)" in source
    assert ".group_by(dm.DocumentDistributionRecipient.campaign_id).all()" in source
    assert '"acknowledged"' in source
    assert '"pending"' in source
    assert '"overdue"' in source


def test_distribution_portfolio_scopes_every_query_to_the_tenant() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_distribution_portfolio_router.py")

    assert "DocumentDistributionCampaign.tenant_id == tenant.amo_id" in source
    assert "DocumentDistributionRecipient.tenant_id == tenant.amo_id" in source
    assert "DocumentControlledCopy.tenant_id == tenant.amo_id" in source
    assert "manual_models.Manual.tenant_id == tenant.id" in source
