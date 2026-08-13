from __future__ import annotations

from pathlib import Path

from amodb.main import app


ROOT = Path(__file__).resolve().parents[5]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_my_work_route_is_registered_and_bounded() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/doc-control/workspace/t/{tenant_slug}/my-work" in paths
    assert "/doc-control/workspace/t/{tenant_slug}/external-source-work" in paths

    source = _source("backend/amodb/apps/doc_control/workspace_dashboard_router.py")
    assert 'visible[:30]' in source
    assert '"limit": 30' in source
    external = _source("backend/amodb/apps/doc_control/workspace_external_assessment_router.py")
    assert 'items[:20]' in external
    assert '"limit": 20' in external


def test_my_work_only_uses_attributable_user_obligations() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_dashboard_router.py")

    assert "DocumentChangeRequest.owner_user_id == current_user.id" in source
    assert "DocumentReviewPlan.owner_user_id == current_user.id" in source
    assert "DocumentDistributionRecipient.recipient_user_id == current_user.id" in source
    assert 'DocumentDistributionRecipient.status == "PENDING"' in source
    assert "DocumentAuthoritySubmission.submitted_by_user_id == current_user.id" in source
    assert "DocumentTemporaryRevision.created_by_user_id == current_user.id" in source
    assert "DocumentControlledCopy.holder_user_id == current_user.id" in source

    external = _source("backend/amodb/apps/doc_control/workspace_external_assessment_router.py")
    assert "DocumentControlProfile.owner_user_id == current_user.id" in external
    assert "manual_models.Manual.tenant_id == tenant.id" in external
    assert "if not assessment_required and not currency_due:" in external


def test_specialist_personal_work_has_explicit_kinds_and_canonical_targets() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_dashboard_router.py")

    assert '"kind": "AUTHORITY_ACTION"' in source
    assert '"kind": "TEMPORARY_REVISION"' in source
    assert '"kind": "CONTROLLED_COPY"' in source
    assert "?tab=workflow#document-control-record-actions" in source
    assert "?tab=changes#document-control-record-actions" in source
    assert "/document-control/controlled-copies?copy=" in source

    external = _source("backend/amodb/apps/doc_control/workspace_external_assessment_router.py")
    assert '"kind": "EXTERNAL_SOURCE_ACTION"' in external
    assert "NEW_REVISION_REQUIRES_ASSESSMENT" in external
    assert "CURRENCY_CHECK_DUE" in external
    assert "assessment_source" in external


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
