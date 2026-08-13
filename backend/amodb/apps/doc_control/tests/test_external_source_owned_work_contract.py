from __future__ import annotations

from pathlib import Path

from amodb.main import app


ROOT = Path(__file__).resolve().parents[5]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_owned_external_source_work_route_is_registered() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/doc-control/workspace/t/{tenant_slug}/external-source-work" in paths


def test_external_source_work_uses_governed_document_owner() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_external_assessment_router.py")

    assert "DocumentControlProfile.owner_user_id == current_user.id" in source
    assert "manual_models.Manual.tenant_id == tenant.id" in source
    assert "ASSESSMENT_REQUIRED_STATUSES" in source
    assert '"kind": "EXTERNAL_SOURCE_ACTION"' in source
    assert '"status": status' in source
    assert "NEW_REVISION_REQUIRES_ASSESSMENT" in source
    assert "CURRENCY_CHECK_DUE" in source
    assert 'f"?view=external-sources&assessment_source={source.id}"' in source


def test_unowned_or_non_actionable_external_sources_do_not_become_personal_work() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_external_assessment_router.py")

    assert "if not assessment_required and not currency_due:" in source
    assert "continue" in source
    assert "No tenant-wide source count is exposed as" in source
    assert '"limit": 20' in source
