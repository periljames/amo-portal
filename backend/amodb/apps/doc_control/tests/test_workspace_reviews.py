from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.doc_control import workspace_review_router as reviews
from amodb.apps.doc_control import workspace_schemas as schemas


def _review(status: str = "SCHEDULED"):
    return SimpleNamespace(status=status)


def test_completed_review_cannot_be_completed_again() -> None:
    with pytest.raises(HTTPException) as caught:
        reviews.validate_review_completion(
            _review("COMPLETED"),
            schemas.ReviewCompleteRequest(outcome="CONTINUE"),
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "REVIEW_ALREADY_CLOSED"


def test_non_continuation_requires_findings() -> None:
    with pytest.raises(HTTPException) as caught:
        reviews.validate_review_completion(
            _review(),
            schemas.ReviewCompleteRequest(
                outcome="CHANGE_REQUIRED",
                actions=[{"action": "Revise chapter 3"}],
            ),
        )
    assert caught.value.status_code == 422


def test_non_continuation_requires_resulting_actions() -> None:
    with pytest.raises(HTTPException) as caught:
        reviews.validate_review_completion(
            _review(),
            schemas.ReviewCompleteRequest(
                outcome="WITHDRAW",
                findings=[{"finding": "Source is obsolete"}],
            ),
        )
    assert caught.value.status_code == 422


def test_continuation_can_complete_without_findings() -> None:
    reviews.validate_review_completion(
        _review(),
        schemas.ReviewCompleteRequest(outcome="CONTINUE"),
    )


def test_effective_review_rejects_unpublished_document(monkeypatch) -> None:
    monkeypatch.setattr(
        reviews,
        "get_manual",
        lambda *args, **kwargs: SimpleNamespace(
            id="manual-1",
            current_published_rev_id=None,
        ),
    )
    payload = schemas.ReviewPlanCreate(
        manual_id="manual-1",
        due_at=datetime.utcnow() + timedelta(days=30),
    )

    with pytest.raises(HTTPException) as caught:
        reviews._effective_review_payload(
            SimpleNamespace(),
            tenant=SimpleNamespace(amo_id="amo-1"),
            payload=payload,
        )

    assert caught.value.status_code == 409


def test_effective_review_rejects_past_due_date(monkeypatch) -> None:
    monkeypatch.setattr(
        reviews,
        "get_manual",
        lambda *args, **kwargs: SimpleNamespace(
            id="manual-1",
            current_published_rev_id="revision-1",
        ),
    )
    monkeypatch.setattr(reviews, "get_revision", lambda *args, **kwargs: SimpleNamespace(id="revision-1"))
    payload = schemas.ReviewPlanCreate(
        manual_id="manual-1",
        revision_id="revision-1",
        due_at=datetime.utcnow() - timedelta(minutes=1),
    )

    with pytest.raises(HTTPException) as caught:
        reviews._effective_review_payload(
            SimpleNamespace(),
            tenant=SimpleNamespace(amo_id="amo-1"),
            payload=payload,
        )

    assert caught.value.status_code == 422
