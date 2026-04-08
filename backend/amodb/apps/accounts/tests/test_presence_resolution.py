from __future__ import annotations

from datetime import datetime, timedelta, timezone

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

