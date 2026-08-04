import pytest
from pydantic import ValidationError

from amodb.apps.work.execution_schemas import (
    HandbackReviewRequest,
    TaskIssueResolve,
)


def test_non_routine_disposition_requires_linked_task():
    with pytest.raises(ValidationError):
        TaskIssueResolve(
            disposition="NON_ROUTINE",
            resolution_notes="Raised as additional work",
        )


def test_rectified_issue_does_not_require_non_routine_task():
    payload = TaskIssueResolve(
        disposition="RECTIFIED",
        resolution_notes="Rectified and checked",
    )
    assert payload.linked_non_routine_task_id is None


def test_handback_review_accepts_only_controlled_decisions():
    accepted = HandbackReviewRequest(
        decision="ACCEPT",
        review_notes="Records trace verified",
    )
    assert accepted.decision == "ACCEPT"
    with pytest.raises(ValidationError):
        HandbackReviewRequest(
            decision="CLOSE",
            review_notes="Invalid shortcut",
        )
