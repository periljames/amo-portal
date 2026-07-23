from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import router_admin

PRESENCE_FRESH_SECONDS = max(
    45,
    int(os.getenv("PRESENCE_HEARTBEAT_GRACE_SECONDS", "90")),
)


def resolve_presence_state(
    *,
    raw_state: str,
    last_seen_at: Optional[datetime],
    now: datetime,
) -> tuple[str, bool]:
    state = str(raw_state or "offline").lower()
    current_time = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    last_seen = last_seen_at
    if last_seen is not None and last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    fresh = bool(
        last_seen
        and last_seen >= current_time - timedelta(seconds=PRESENCE_FRESH_SECONDS)
    )
    if not fresh:
        return "offline", False
    return ("away", True) if state == "away" else ("online", True)


_legacy_presence_display = router_admin._presence_display_for_user


def presence_display_for_user(*, user, presence, availability_status=None):
    """Preserve the distinct Away label even though away users are connected."""
    if (
        user.is_active
        and availability_status != "ON_LEAVE"
        and presence.state == "away"
        and presence.last_seen_at
    ):
        last_seen = presence.last_seen_at
        return router_admin.schemas.UserPresenceDisplayRead(
            status_label="Away",
            last_seen_label="Away",
            last_seen_at=last_seen,
            last_seen_at_display=(
                last_seen.isoformat() if hasattr(last_seen, "isoformat") else str(last_seen)
            ),
        )
    return _legacy_presence_display(
        user=user,
        presence=presence,
        availability_status=availability_status,
    )


# router_admin owns legacy workspace helpers. Replace their policies before the
# FastAPI router is included so all account surfaces use the same semantics.
router_admin.PRESENCE_HEARTBEAT_GRACE_SECONDS = PRESENCE_FRESH_SECONDS
router_admin._resolve_presence_state = resolve_presence_state
router_admin._presence_display_for_user = presence_display_for_user
