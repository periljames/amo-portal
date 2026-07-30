from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from amodb.apps.rostering import calendar_feed


def test_published_assignments_builds_sqlalchemy_loader_options_without_strings() -> None:
    db = MagicMock()
    query = MagicMock()
    db.query.return_value = query
    query.join.return_value = query
    query.options.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = []

    rows = calendar_feed._published_assignments(
        db,
        amo_id="amo-test",
        user_id="user-test",
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
    )

    assert rows == []
    query.options.assert_called_once()


def test_empty_personal_calendar_is_valid_crlf_terminated_ics(monkeypatch) -> None:
    db = MagicMock()
    user_query = MagicMock()
    db.query.return_value = user_query
    user_query.filter.return_value.first.return_value = SimpleNamespace(full_name="Test Engineer")

    monkeypatch.setattr(calendar_feed, "_published_assignments", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        calendar_feed.commitments,
        "list_commitments",
        lambda *args, **kwargs: SimpleNamespace(items=[]),
    )

    content = calendar_feed.personal_calendar(
        db,
        amo_id="amo-test",
        user_id="user-test",
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
    )

    assert content.startswith("BEGIN:VCALENDAR\r\n")
    assert "X-WR-CALNAME:AMO Portal · Test Engineer\r\n" in content
    assert content.endswith("END:VCALENDAR\r\n")
    assert "\n" not in content.replace("\r\n", "")
