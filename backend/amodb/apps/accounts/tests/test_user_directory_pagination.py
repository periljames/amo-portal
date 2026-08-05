from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import attributes

from amodb.apps.accounts import models
from amodb.apps.accounts.router_user_directory import (
    PRESENCE_FRESH_SECONDS,
    prevent_inactive_department_assignment,
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


def _user(*, active: bool, department_id: str | None = None) -> models.User:
    user = models.User(
        id="user-1",
        amo_id="amo-1",
        staff_code="USR001",
        email="user@example.com",
        first_name="Test",
        last_name="User",
        full_name="Test User",
        role=models.AccountRole.TECHNICIAN,
        hashed_password="not-used",
        is_active=active,
    )
    attributes.set_committed_value(user, "department_id", department_id)
    return user


def test_inactive_user_cannot_receive_new_department():
    user = _user(active=False)
    user.department_id = "department-1"
    session = SimpleNamespace(new=[], dirty=[user])

    with pytest.raises(HTTPException) as exc:
        prevent_inactive_department_assignment(session, None, None)

    assert exc.value.status_code == 409
    assert "Inactive users cannot be assigned" in str(exc.value.detail)


def test_inactive_user_can_have_department_cleared():
    user = _user(active=False, department_id="department-1")
    user.department_id = None
    session = SimpleNamespace(new=[], dirty=[user])

    prevent_inactive_department_assignment(session, None, None)


def test_active_user_can_receive_department():
    user = _user(active=True)
    user.department_id = "department-1"
    session = SimpleNamespace(new=[], dirty=[user])

    prevent_inactive_department_assignment(session, None, None)


def test_directory_route_is_registered_once():
    from amodb.apps.accounts.router_admin import router

    routes = [
        route
        for route in router.routes
        if getattr(route, "path", None) == "/accounts/admin/user-directory"
        and "GET" in (getattr(route, "methods", None) or set())
    ]
    assert len(routes) == 1
