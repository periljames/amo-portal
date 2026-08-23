from __future__ import annotations

import uuid

from amodb.utils import identifiers


def test_generate_uuid7_is_strictly_ordered_within_one_millisecond(monkeypatch):
    fixed_time = 1_800_000_000.123
    fixed_timestamp_ms = int(fixed_time * 1000)
    monkeypatch.setattr(identifiers.time, "time", lambda: fixed_time)
    monkeypatch.setattr(identifiers, "_last_uuid7_timestamp_ms", fixed_timestamp_ms - 1)
    monkeypatch.setattr(identifiers, "_last_uuid7_random", -1)

    generated = [identifiers.generate_uuid7() for _ in range(100)]

    assert generated == sorted(generated)
    assert len(generated) == len(set(generated))
    assert all(uuid.UUID(value).version == 7 for value in generated)
    assert all(uuid.UUID(value).variant == uuid.RFC_4122 for value in generated)
