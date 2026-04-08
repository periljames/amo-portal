from __future__ import annotations

from datetime import datetime, timedelta, timezone

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import router_admin


def test_presence_resolution_marks_fresh_away_as_active():
    now = datetime.now(timezone.utc)
    state, is_online = router_admin._resolve_presence_state(
        raw_state="away",
        last_seen_at=now - timedelta(seconds=45),
        now=now,
    )
    assert state == "away"
    assert is_online is True


def test_presence_resolution_marks_stale_away_as_offline():
    now = datetime.now(timezone.utc)
    state, is_online = router_admin._resolve_presence_state(
        raw_state="away",
        last_seen_at=now - timedelta(seconds=router_admin.PRESENCE_HEARTBEAT_GRACE_SECONDS + 5),
        now=now,
    )
    assert state == "offline"
    assert is_online is False


def test_presence_resolution_marks_fresh_online_as_online():
    now = datetime.now(timezone.utc)
    state, is_online = router_admin._resolve_presence_state(
        raw_state="online",
        last_seen_at=now - timedelta(seconds=30),
        now=now,
    )
    assert state == "online"
    assert is_online is True


def test_display_title_prefers_specific_position_title():
    user = account_models.User(
        staff_code="SC-1",
        email="demo@example.com",
        first_name="Demo",
        last_name="User",
        full_name="Demo User",
        hashed_password="hash",
        role=account_models.AccountRole.TECHNICIAN,
        position_title="Accountable Manager",
    )
    assert router_admin._display_title_for_user(user) == "Accountable Manager"


def test_display_title_falls_back_to_role_label():
    user = account_models.User(
        staff_code="SC-2",
        email="demo2@example.com",
        first_name="Demo",
        last_name="User",
        full_name="Demo User",
        hashed_password="hash",
        role=account_models.AccountRole.SAFETY_MANAGER,
        position_title=None,
    )
    assert router_admin._display_title_for_user(user) == "Safety Manager"
