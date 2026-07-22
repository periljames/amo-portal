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


# router_admin owns legacy workspace helpers. Replace their policy before the
# FastAPI router is included so all account surfaces use the same semantics.
router_admin.PRESENCE_HEARTBEAT_GRACE_SECONDS = PRESENCE_FRESH_SECONDS
router_admin._resolve_presence_state = resolve_presence_state
