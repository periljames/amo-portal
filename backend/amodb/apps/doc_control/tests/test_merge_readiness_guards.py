from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from amodb.apps.doc_control import workspace_access
from amodb.apps.doc_control import workspace_authority_router as authority
from amodb.apps.doc_control import workspace_responsibility_access as responsibility_access
from amodb.apps.doc_control import workspace_schemas as schemas
from amodb.apps.doc_control import workspace_service
from amodb.apps.doc_control import workspace_tr_terminal_router as tr_terminal
from amodb.apps.doc_control import workspace_workflow_review_router as workflow_review
from amodb.apps.doc_control.workspace_decision_policy import is_decision_approver


def _request(method: str, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )


def test_quality_inspector_is_controller_without_decision_authority() -> None:
    user = SimpleNamespace(is_superuser=False, is_amo_admin=False, role="QUALITY_INSPECTOR")
    assert workspace_service.is_control_user(user) is True
    assert is_decision_approver(user) is False


def test_controlled_decisions_require_reason_and_evidence() -> None:
    payload = schemas.WorkflowTransitionRequest(action="APPROVE_QUALITY", expected_version=1)
    with pytest.raises(HTTPException) as caught:
        workflow_review.validate_decision_evidence(payload)
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "DECISION_EVIDENCE_REQUIRED"

    workflow_review.validate_decision_evidence(
        schemas.WorkflowTransitionRequest(
            action="APPROVE_QUALITY",
            comments="Quality review completed against retained checklist evidence.",
            evidence=[{"asset_id": "evidence-1"}],
            expected_version=1,
        )
    )


def test_empty_evidence_objects_do_not_satisfy_decision_evidence() -> None:
    payload = schemas.WorkflowTransitionRequest(
        action="PUBLISH",
        comments="Release authorized against the retained approval package.",
        evidence=[{}, {"asset_id": "   "}],
        expected_version=1,
    )
    with pytest.raises(HTTPException) as caught:
        workflow_review.validate_decision_evidence(payload)
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "DECISION_EVIDENCE_REQUIRED"
    assert caught.value.detail["invalid_evidence_indexes"] == [0, 1]


def test_workflow_transition_bypasses_only_the_coarse_controller_gate() -> None:
    assigned_reviewer = SimpleNamespace(
        id="reviewer-1",
        is_superuser=False,
        is_amo_admin=False,
        role="TECHNICIAN",
        department_id=None,
    )

    # The route-level dependency must defer transition authority to
    # require_workflow_action; otherwise a valid governed reviewer is rejected
    # before the assignment-aware endpoint can evaluate their exact action.
    workspace_access.enforce_workspace_access(
        _request(
            "POST",
            "/doc-control/workspace/t/tenant-1/workflows/workflow-1/transition",
        ),
        assigned_reviewer,
    )

    # The same reviewer still cannot enter unrelated controller surfaces.
    with pytest.raises(HTTPException) as caught:
        workspace_access.enforce_workspace_access(
            _request("POST", "/doc-control/workspace/t/tenant-1/controlled-copies"),
            assigned_reviewer,
        )
    assert caught.value.status_code == 403
    assert caught.value.detail == "Document Control privileges required"


def test_assigned_reviewer_authority_is_not_overridden_by_accountable_role_policy(monkeypatch) -> None:
    technical_workflow = SimpleNamespace(
        state="TECHNICAL_REVIEW",
        tenant_id="tenant-1",
        manual_id="manual-1",
        revision_id="revision-1",
    )
    quality_workflow = SimpleNamespace(
        state="QUALITY_REVIEW",
        tenant_id="tenant-1",
        manual_id="manual-1",
        revision_id="revision-1",
    )
    management_workflow = SimpleNamespace(
        state="ACCOUNTABLE_MANAGER_APPROVAL",
        tenant_id="tenant-1",
        manual_id="manual-1",
        revision_id="revision-1",
    )
    assigned_reviewer = SimpleNamespace(
        id="reviewer-1",
        is_superuser=False,
        is_amo_admin=False,
        role="USER",
        department_id=None,
    )

    monkeypatch.setattr(
        responsibility_access,
        "has_confirmed_responsibility",
        lambda _db, *, workflow, user, responsibility_types: True,
    )

    assert responsibility_access.can_perform_workflow_action(
        object(), workflow=technical_workflow, user=assigned_reviewer, action="APPROVE_TECHNICAL"
    ) is True
    assert responsibility_access.can_perform_workflow_action(
        object(), workflow=quality_workflow, user=assigned_reviewer, action="APPROVE_QUALITY"
    ) is True
    assert responsibility_access.can_perform_workflow_action(
        object(), workflow=management_workflow, user=assigned_reviewer, action="APPROVE_ACCOUNTABLE_MANAGER"
    ) is True

    # The evidence guard must not re-impose the generic accountable-role policy;
    # downstream require_workflow_action is the authoritative per-action gate.
    review_source = Path(workflow_review.__file__).read_text(encoding="utf-8")
    assert "require_decision_approver(current_user)" not in review_source


def test_publication_still_requires_accountable_decision_authority() -> None:
    workflow = SimpleNamespace(
        state="SCHEDULED_FOR_EFFECTIVITY",
        tenant_id="tenant-1",
        manual_id="manual-1",
        revision_id="revision-1",
    )
    reviewer_only = SimpleNamespace(
        id="reviewer-1",
        is_superuser=False,
        is_amo_admin=False,
        role="USER",
        department_id=None,
    )
    assert responsibility_access.can_perform_workflow_action(
        object(), workflow=workflow, user=reviewer_only, action="PUBLISH"
    ) is False


def test_every_publication_recipient_must_remain_active() -> None:
    with pytest.raises(HTTPException) as caught:
        workflow_review.validate_publication_recipient_counts(
            total_recipients=2,
            active_recipients=1,
        )
    assert caught.value.status_code == 409
    blocker = caught.value.detail["blockers"][0]
    assert blocker["code"] == "DISTRIBUTION_HAS_INVALID_RECIPIENTS"
    assert blocker["total_recipients"] == 2
    assert blocker["active_recipients"] == 1


def test_publication_recipient_counts_allow_only_complete_revalidation() -> None:
    workflow_review.validate_publication_recipient_counts(
        total_recipients=2,
        active_recipients=2,
    )


def test_explicit_null_authority_summary_is_not_treated_as_text() -> None:
    row = SimpleNamespace(status="SUBMITTED", evidence_json=[], response_summary="Earlier note")
    payload = schemas.AuthoritySubmissionUpdate(status="REJECTED", response_summary=None)
    with pytest.raises(HTTPException) as caught:
        authority.validate_authority_update(row, payload)
    assert caught.value.status_code == 409


def test_terminal_temporary_revision_states_are_immutable() -> None:
    assert tr_terminal._TERMINAL_STATUSES == {"WITHDRAWN", "INCORPORATED"}


def test_controller_ui_uses_server_approval_capability() -> None:
    repository_root = Path(__file__).resolve().parents[5]
    guarded_source = (
        repository_root
        / "frontend/src/pages/documentControl/DocumentControlLifecycleActionsGuarded.tsx"
    ).read_text(encoding="utf-8")
    controller_source = (
        repository_root
        / "frontend/src/pages/documentControl/DocumentControlControllerLifecycleActions.tsx"
    ).read_text(encoding="utf-8")
    assert "capabilities?.approve" in guarded_source
    assert "DECISION_SEPARATED_VIEWS" in guarded_source
    assert "ApprovalBoundary" in controller_source
    assert "PUBLISH" not in controller_source
    assert "ARCHIVE" not in controller_source
    assert "APPROVE_QUALITY" not in controller_source
