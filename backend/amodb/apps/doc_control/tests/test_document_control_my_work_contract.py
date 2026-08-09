from __future__ import annotations

from pathlib import Path

from amodb.main import app


ROOT = Path(__file__).resolve().parents[5]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_my_work_route_is_registered_and_bounded() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/doc-control/workspace/t/{tenant_slug}/my-work" in paths

    source = _source("backend/amodb/apps/doc_control/workspace_dashboard_router.py")
    assert 'visible[:30]' in source
    assert '"limit": 30' in source


def test_my_work_only_uses_attributable_user_obligations() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_dashboard_router.py")

    assert "DocumentChangeRequest.owner_user_id == current_user.id" in source
    assert "DocumentReviewPlan.owner_user_id == current_user.id" in source
    assert "DocumentDistributionRecipient.recipient_user_id == current_user.id" in source
    assert 'DocumentDistributionRecipient.status == "PENDING"' in source


def test_workflow_tasks_require_confirmed_effective_responsibility() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_dashboard_router.py")

    assert 'DocumentResponsibilityAssignment.confirmation_status == "CONFIRMED"' in source
    assert "DocumentResponsibilityAssignment.effective_from <= today" in source
    assert "DocumentResponsibilityAssignment.effective_to >= today" in source
    assert "DocumentResponsibilityAssignment.assignee_user_id == current_user.id" in source
    assert "DocumentResponsibilityAssignment.assignee_department_id == current_user.department_id" in source
    assert "DocumentResponsibilityAssignment.assignee_role.in_" in source
    assert "WORKFLOW_RESPONSIBILITY" in source
    assert "required.intersection(responsibilities.get(row.manual_id, set()))" in source


def test_my_work_filters_document_metadata_through_reader_access() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_dashboard_router.py")

    assert "if can_read_manual(current_user, profiles.get(manual.id))" in source
    assert 'task["manual_id"] in labels' in source
    assert '"document": labels[task["manual_id"]]' in source


def test_reader_dashboard_does_not_load_controller_governance_totals() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_dashboard_router.py")

    assert "if not is_control_user(current_user):" in source
    assert "return _reader_dashboard(" in source
    assert "dashboard[\"metrics\"].update(_controller_control_gaps" in source
