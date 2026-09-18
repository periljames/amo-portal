"""Bounded development counters and atomic, shared production auth limits."""
from __future__ import annotations

import hashlib
import math
import os
import threading
import time
from collections import OrderedDict
from functools import lru_cache

from fastapi import HTTPException

WINDOW_SECONDS = max(1, int(os.getenv("AUTH_RATE_LIMIT_WINDOW_SEC", "60")))
MAX_ATTEMPTS = max(1, int(os.getenv("AUTH_RATE_LIMIT_MAX_ATTEMPTS", "10")))
IP_MAX_ATTEMPTS = max(1, int(os.getenv("AUTH_RATE_LIMIT_IP_MAX_ATTEMPTS", "3000")))
MAX_KEYS = max(1, int(os.getenv("AUTH_RATE_LIMIT_MAX_KEYS", "50000")))
STATE: OrderedDict[str, tuple[float, int]] = OrderedDict()
LOCK = threading.Lock()

# The counter and expiry must be changed atomically across API processes.
SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('PEXPIRE', KEYS[1], ARGV[1]) end
return {count, redis.call('PTTL', KEYS[1])}
"""


@lru_cache(maxsize=1)
def _redis_client():
    url = os.getenv("AUTH_RATE_LIMIT_REDIS_URL", "").strip()
    if not url:
        if os.getenv("AUTH_RATE_LIMIT_REQUIRE_SHARED", "false").lower() in {"1", "true", "yes"}:
            raise RuntimeError("Shared authentication limiter is required")
        return None
    from redis import Redis

    return Redis.from_url(
        url, socket_connect_timeout=0.5, socket_timeout=0.5,
        max_connections=50, decode_responses=True,
    )


def enforce(subject: str, endpoint: str, limit: int = MAX_ATTEMPTS) -> None:
    # Neither identifiers nor refresh credentials belong in Redis key names.
    digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()
    key = f"amo:auth-limit:v1:{endpoint}:{digest}"
    try:
        client = _redis_client()
        if client is not None:
            count, ttl_ms = client.eval(SCRIPT, 1, key, WINDOW_SECONDS * 1000)
            retry_after = max(1, math.ceil(int(ttl_ms) / 1000))
        else:
            now = time.monotonic()
            with LOCK:
                # Entries are ordered by creation/expiry, not last access.
                while STATE and next(iter(STATE.values()))[0] <= now:
                    STATE.popitem(last=False)
                expires, count = STATE.get(key, (now + WINDOW_SECONDS, 0))
                if key not in STATE and len(STATE) >= MAX_KEYS:
                    raise RuntimeError("Authentication limiter capacity exhausted")
                count = min(count + 1, limit + 1)
                STATE[key] = (expires, count)
                retry_after = max(1, math.ceil(expires - now))
    except Exception as exc:
        # Do not silently multiply limits by falling back per-process on outage.
        raise HTTPException(503, "Authentication is temporarily unavailable.",
                            headers={"Retry-After": "5"}) from exc
    if count > limit:
        raise HTTPException(429, "Too many authentication attempts. Please try again shortly.",
                            headers={"Retry-After": str(retry_after)})
