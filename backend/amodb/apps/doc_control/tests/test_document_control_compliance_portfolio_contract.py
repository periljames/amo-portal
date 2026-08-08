from __future__ import annotations

from pathlib import Path

from amodb.main import app


ROOT = Path(__file__).resolve().parents[5]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_compliance_portfolio_route_is_registered_before_compatibility_workspace() -> None:
    path = "/doc-control/workspace/t/{tenant_slug}/compliance-portfolio"
    matches = [route for route in app.routes if getattr(route, "path", "") == path]
    assert matches, path
    assert matches[0].endpoint.__module__ == "amodb.apps.doc_control.workspace_compliance_portfolio_router"

    router = _source("backend/amodb/apps/doc_control/router.py")
    assert router.index("router.include_router(workspace_compliance_portfolio_router") < router.index(
        "router.include_router(\n    workspace_router"
    )


def test_compliance_portfolio_is_server_paginated_bounded_and_controller_only() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_compliance_portfolio_router.py")

    assert "page: int = Query(default=1, ge=1)" in source
    assert "per_page: int = Query(default=50, ge=1, le=100)" in source
    assert "offset = (page - 1) * per_page" in source
    assert ".offset(offset).limit(per_page).all()" in source
    assert '"pagination": _pagination(page, per_page, total, len(items))' in source
    assert "require_control_user(current_user)" in source


def test_compliance_portfolio_uses_authoritative_assurance_entities() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_compliance_portfolio_router.py")

    for view in (
        "reviews",
        "external-sources",
        "relationships",
        "applicability",
        "superseded-references",
    ):
        assert f'"{view}"' in source
    assert "DocumentReviewPlan" in source
    assert "ExternalDocumentSource" in source
    assert "ExternalRevisionReceipt" in source
    assert "DocumentGovernedRelationship" in source
    assert "DocumentApplicabilityRule" in source
    assert "compliance score" in source.lower()


def test_external_source_view_reports_assessment_and_due_state_without_inventing_currency() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_compliance_portfolio_router.py")

    assert 'receipt.currency_status == "UNVERIFIED"' in source
    assert 'receipt.applicability_status == "PENDING"' in source
    assert 'display_status = "ASSESSMENT_REQUIRED"' in source
    assert '"received_revision": receipt.revision_label if receipt else None' in source
    assert '"currency_status": receipt.currency_status if receipt else None' in source


def test_superseded_reference_view_requires_an_explicit_version_specific_relationship() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_compliance_portfolio_router.py")

    assert "target_revision_id.isnot(None)" in source
    assert "current_published_rev_id.isnot(None)" in source
    assert "target_revision_id != target_manual.current_published_rev_id" in source
    assert 'resolution_status == "CONFIRMED"' in source
    assert '"status": "SUPERSEDED_REFERENCE"' in source


def test_compliance_portfolio_scopes_all_source_documents_to_the_tenant() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_compliance_portfolio_router.py")

    assert "DocumentReviewPlan.tenant_id == tenant.amo_id" in source
    assert "ExternalDocumentSource.tenant_id == tenant.amo_id" in source
    assert "DocumentGovernedRelationship.tenant_id == tenant.amo_id" in source
    assert "DocumentApplicabilityRule.tenant_id == tenant.amo_id" in source
    assert "manual_models.Manual.tenant_id == tenant.id" in source
