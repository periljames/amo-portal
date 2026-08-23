from __future__ import annotations

import os
import threading
import time
import uuid


_UUID7_RANDOM_BITS = 74
_UUID7_RANDOM_MASK = (1 << _UUID7_RANDOM_BITS) - 1
_UUID7_RAND_B_MASK = (1 << 62) - 1
_uuid7_lock = threading.Lock()
_last_uuid7_timestamp_ms = -1
_last_uuid7_random = -1


def _uuid7_from_parts(timestamp_ms: int, random_bits: int) -> uuid.UUID:
    rand_a = random_bits >> 62
    rand_b = random_bits & _UUID7_RAND_B_MASK
    value = (
        (timestamp_ms << 80)
        | (0x7 << 76)
        | (rand_a << 64)
        | (0b10 << 62)
        | rand_b
    )
    return uuid.UUID(int=value)


def generate_uuid7() -> str:
    """
    Generate a UUIDv7 string (time-ordered).

    UUIDv7 layout per draft:
    - 48-bit Unix timestamp in milliseconds
    - 4-bit version (0b0111)
    - 74-bit randomness

    The random field is incremented for calls in the same millisecond. This keeps
    identifiers strictly increasing within a process, which is required anywhere
    the UUID is used as a stable tie-breaker for timestamp-ordered rows.
    """
    global _last_uuid7_random, _last_uuid7_timestamp_ms

    timestamp_ms = int(time.time() * 1000)
    with _uuid7_lock:
        if timestamp_ms > _last_uuid7_timestamp_ms:
            random_bits = int.from_bytes(os.urandom(10), "big") & _UUID7_RANDOM_MASK
        else:
            timestamp_ms = _last_uuid7_timestamp_ms
            random_bits = _last_uuid7_random + 1
            if random_bits > _UUID7_RANDOM_MASK:
                timestamp_ms += 1
                random_bits = int.from_bytes(os.urandom(10), "big") & _UUID7_RANDOM_MASK

        _last_uuid7_timestamp_ms = timestamp_ms
        _last_uuid7_random = random_bits
        return str(_uuid7_from_parts(timestamp_ms, random_bits))
