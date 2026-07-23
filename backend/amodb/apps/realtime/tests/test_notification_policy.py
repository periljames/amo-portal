from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from amodb.apps.realtime import notification_policy


def test_overnight_quiet_hours_use_the_users_timezone():
    # 20:30 UTC is 23:30 in Nairobi.
    now = datetime(2026, 7, 22, 20, 30, tzinfo=timezone.utc)
    assert notification_policy.is_quiet_now(
        start="22:00",
        end="06:00",
        timezone_name="Africa/Nairobi",
        now=now,
    ) is True


def test_daytime_window_and_equal_boundaries():
    now = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    assert notification_policy.is_quiet_now(
        start="09:00",
        end="17:00",
        timezone_name="UTC",
        now=now,
    ) is True
    assert notification_policy.is_quiet_now(
        start="09:00",
        end="09:00",
        timezone_name="UTC",
        now=now,
    ) is False


def test_invalid_clock_and_timezone_are_rejected():
    with pytest.raises(HTTPException, match="HH:MM"):
        notification_policy.validate_clock("25:99", field_name="quiet_hours_start")
    with pytest.raises(HTTPException, match="IANA timezone"):
        notification_policy.validate_timezone("Mars/Olympus")
