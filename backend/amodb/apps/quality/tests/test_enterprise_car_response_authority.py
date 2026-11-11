"""The reviewer must see the last committed CAR response across valid lifecycle states.

Prepared for Phase 3. This is a handler contract test, not a substitute for
the PostgreSQL + invited-browser scenario in run 41999293028.
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from uuid import uuid4

import pytest

from amodb.apps.quality import models


router = importlib.import_module("amodb.apps.quality.router")


@pytest.mark.parametrize("car_status", [
    models.CARStatus.PENDING_VERIFICATION,
    models.CARStatus.IN_PROGRESS,
    models.CARStatus.CLOSED,
])
def test_committed_response_visible_to_authorized_reviewer_after_status_change(monkeypatch, car_status):
    car_id = uuid4()
    recorded = SimpleNamespace(id=uuid4(), root_cause="Revised operational RCA")
    car = SimpleNamespace(id=car_id, status=car_status)
    reviewer = SimpleNamespace(id="quality-reviewer", amo_id="tenant-a")
    verified = []

    def get_car(_db, *, amo_id, car_id, lock):
        assert amo_id == "tenant-a"
        assert lock is False
        return car

    monkeypatch.setattr(router, "_current_amo_id", lambda _user: "tenant-a")
    monkeypatch.setattr(router, "_get_car_for_amo", get_car)
    monkeypatch.setattr(router, "_require_car_review_access", lambda _db, _user, _car: verified.append("authorized"))
    monkeypatch.setattr(router, "_car_invite_latest_active_response", lambda _db, _id: recorded)
    monkeypatch.setattr(router, "_serialize_car_response", lambda _db, _id, row, *, is_latest: {
        "id": str(row.id), "root_cause": row.root_cause, "is_latest": is_latest,
    })

    result = router.list_car_responses_for_review(
        car_id=car_id, request=None, mark_open=False, db=object(), current_user=reviewer,
    )
    assert verified == ["authorized"]
    assert result == [{"id": str(recorded.id), "root_cause": "Revised operational RCA", "is_latest": True}]


def test_no_submitted_response_does_not_invent_review_evidence(monkeypatch):
    car_id = uuid4()
    car = SimpleNamespace(id=car_id, status=models.CARStatus.IN_PROGRESS)
    monkeypatch.setattr(router, "_current_amo_id", lambda _user: "tenant-a")
    monkeypatch.setattr(router, "_get_car_for_amo", lambda *_args, **_kwargs: car)
    monkeypatch.setattr(router, "_require_car_review_access", lambda *_args: None)
    monkeypatch.setattr(router, "_car_invite_latest_active_response", lambda *_args: None)
    assert router.list_car_responses_for_review(
        car_id=car_id, request=None, mark_open=False, db=object(),
        current_user=SimpleNamespace(amo_id="tenant-a"),
    ) == []
