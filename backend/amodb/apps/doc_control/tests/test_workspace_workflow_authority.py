from __future__ import annotations

from types import SimpleNamespace

from amodb.apps.doc_control.workspace_workflow_authority_router import _matching_submission


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
