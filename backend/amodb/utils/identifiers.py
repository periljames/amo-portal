from __future__ import annotations

import os
import time
import uuid


def generate_uuid7() -> str:
    """
    Generate a UUIDv7 string (time-ordered).

    UUIDv7 layout per draft:
    - 48-bit Unix timestamp in milliseconds
    - 4-bit version (0b0111)
    - 74-bit randomness
    """
    ts_ms = int(time.time() * 1000)
    ts_bytes = ts_ms.to_bytes(6, "big", signed=False)
    rand_bytes = os.urandom(10)
    raw = bytearray(ts_bytes + rand_bytes)
    raw[6] = (raw[6] & 0x0F) | 0x70
    raw[8] = (raw[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(raw)))
