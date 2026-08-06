from __future__ import annotations

import inspect

import pytest

from amodb.apps.rostering import calendar_feed


def test_calendar_loader_paths_are_sqlalchemy_2_compatible() -> None:
    options = calendar_feed._published_assignment_loader_options()

    assert len(options) == 3
    source = inspect.getsource(calendar_feed._published_assignment_loader_options)
    assert '.selectinload("task")' not in source
    assert '.selectinload("work_order")' not in source
    assert '.selectinload("aircraft")' not in source
    assert "work_models.TaskAssignment.task" in source
    assert "work_models.TaskCard.work_order" in source
    assert "work_models.WorkOrder.aircraft" in source


def test_calendar_subscription_token_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "calendar-feed-regression-secret")

    token = calendar_feed.calendar_token(amo_id="AMO-TEST", user_id="USER-TEST")

    assert calendar_feed.decode_calendar_token(token) == ("AMO-TEST", "USER-TEST")


def test_calendar_subscription_token_rejects_tampering(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "calendar-feed-regression-secret")
    token = calendar_feed.calendar_token(amo_id="AMO-TEST", user_id="USER-TEST")
    replacement = "0" if token[-1] != "0" else "1"

    with pytest.raises(ValueError, match="Invalid calendar subscription token"):
        calendar_feed.decode_calendar_token(f"{token[:-1]}{replacement}")
