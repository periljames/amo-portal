from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.doc_control import workspace_schemas as schemas
from amodb.apps.doc_control.workspace_authority_router import validate_authority_update


def _submission(status: str = "DRAFT", *, evidence=None, response_summary=None):
    return SimpleNamespace(
        status=status,
        evidence_json=list(evidence or []),
        response_summary=response_summary,
    )


def _update(status: str, **values):
    payload = {
        "status": status,
        "response_summary": None,
        "response_due_at": None,
        "evidence": None,
    }
    payload.update(values)
    return schemas.AuthoritySubmissionUpdate(**payload)


def test_submission_requires_retained_evidence() -> None:
    with pytest.raises(HTTPException) as caught:
        validate_authority_update(_submission(), _update("SUBMITTED"))
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "AUTHORITY_SUBMISSION_EVIDENCE_REQUIRED"


def test_approval_requires_response_reference_and_evidence() -> None:
    row = _submission("IN_REVIEW")
    with pytest.raises(HTTPException) as caught:
        validate_authority_update(row, _update("APPROVED"))
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "AUTHORITY_APPROVAL_EVIDENCE_REQUIRED"


def test_approval_with_evidence_and_summary_is_allowed() -> None:
    validate_authority_update(
        _submission("IN_REVIEW"),
        _update(
            "APPROVED",
            response_summary="KCAA approval reference KCAA/AMO/2026/041",
            evidence=[{"asset_id": "authority-approval-letter"}],
        ),
    )


def test_approved_submission_is_terminal() -> None:
    with pytest.raises(HTTPException) as caught:
        validate_authority_update(
            _submission(
                "APPROVED",
                evidence=[{"asset_id": "approval"}],
                response_summary="Approved",
            ),
            _update("WITHDRAWN", response_summary="Revoke"),
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "AUTHORITY_TRANSITION_INVALID"


def test_rejection_requires_reason() -> None:
    with pytest.raises(HTTPException) as caught:
        validate_authority_update(_submission("IN_REVIEW"), _update("REJECTED"))
    assert caught.value.status_code == 409
