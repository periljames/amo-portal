from __future__ import annotations

from types import SimpleNamespace

from amodb.apps.doc_control import workspace_schemas as schemas
from amodb.apps.doc_control.workspace_workflow_authority_router import (
    _matching_submission,
    _normalise_system_managed_readiness,
)


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class _DB:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *args, **kwargs):
        return _Query(self.rows)


def _submission(*, evidence=None, summary=None):
    return SimpleNamespace(
        evidence_json=list(evidence or []),
        response_summary=summary,
    )


def test_submitted_workflow_requires_retained_submission_evidence() -> None:
    assert _matching_submission(
        _DB([_submission()]),
        tenant_id="amo-1",
        revision_id="revision-1",
        approved=False,
    ) is None
    row = _submission(evidence=[{"asset_id": "submission-letter"}])
    assert _matching_submission(
        _DB([row]),
        tenant_id="amo-1",
        revision_id="revision-1",
        approved=False,
    ) is row


def test_approved_workflow_requires_evidence_and_response_reference() -> None:
    assert _matching_submission(
        _DB([_submission(evidence=[{"asset_id": "approval"}])]),
        tenant_id="amo-1",
        revision_id="revision-1",
        approved=True,
    ) is None
    row = _submission(
        evidence=[{"asset_id": "approval"}],
        summary="KCAA approval reference KCAA/AMO/2026/041",
    )
    assert _matching_submission(
        _DB([row]),
        tenant_id="amo-1",
        revision_id="revision-1",
        approved=True,
    ) is row


def test_unchanged_system_distribution_state_is_not_treated_as_manual_override() -> None:
    workflow = SimpleNamespace(distribution_readiness_status="READY")
    payload = schemas.WorkflowTransitionRequest(
        action="PUBLISH",
        expected_version=4,
        distribution_readiness_status="READY",
    )
    normalised = _normalise_system_managed_readiness(workflow, payload)
    assert normalised.distribution_readiness_status is None


def test_changed_distribution_state_is_left_for_guard_rejection() -> None:
    workflow = SimpleNamespace(distribution_readiness_status="NOT_REQUIRED")
    payload = schemas.WorkflowTransitionRequest(
        action="PUBLISH",
        expected_version=4,
        distribution_readiness_status="READY",
    )
    normalised = _normalise_system_managed_readiness(workflow, payload)
    assert normalised.distribution_readiness_status == "READY"
