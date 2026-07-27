from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.doc_control import workspace_authority_router as authority
from amodb.apps.doc_control import workspace_schemas as schemas
from amodb.apps.doc_control import workspace_service
from amodb.apps.doc_control import workspace_tr_terminal_router as tr_terminal
from amodb.apps.doc_control import workspace_workflow_review_router as workflow_review
from amodb.apps.doc_control.workspace_decision_policy import is_decision_approver


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


def test_explicit_null_authority_summary_is_not_treated_as_text() -> None:
    row = SimpleNamespace(status="SUBMITTED", evidence_json=[], response_summary="Earlier note")
    payload = schemas.AuthoritySubmissionUpdate(status="REJECTED", response_summary=None)
    with pytest.raises(HTTPException) as caught:
        authority.validate_authority_update(row, payload)
    assert caught.value.status_code == 409


def test_terminal_temporary_revision_states_are_immutable() -> None:
    assert tr_terminal._TERMINAL_STATUSES == {"WITHDRAWN", "INCORPORATED"}
