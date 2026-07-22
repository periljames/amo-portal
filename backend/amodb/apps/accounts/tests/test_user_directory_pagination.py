from __future__ import annotations

from datetime import datetime, timedelta, timezone

from amodb.apps.accounts.router_user_directory import (
    PRESENCE_FRESH_SECONDS,
    resolve_directory_presence,
)


def test_directory_treats_fresh_away_user_as_connected():
    now = datetime.now(timezone.utc)
    presence = resolve_directory_presence(
        raw_state="away",
        last_seen_at=now - timedelta(seconds=30),
        now=now,
    )
    assert presence.state == "away"
    assert presence.is_online is True


def test_directory_marks_expired_presence_offline():
    now = datetime.now(timezone.utc)
    presence = resolve_directory_presence(
        raw_state="online",
        last_seen_at=now - timedelta(seconds=PRESENCE_FRESH_SECONDS + 1),
        now=now,
    )
    assert presence.state == "offline"
    assert presence.is_online is False


def test_directory_route_is_registered_once():
    from amodb.apps.accounts.router_admin import router

    routes = [
        route
        for route in router.routes
        if getattr(route, "path", None) == "/accounts/admin/user-directory"
        and "GET" in (getattr(route, "methods", None) or set())
    ]
    assert len(routes) == 1
