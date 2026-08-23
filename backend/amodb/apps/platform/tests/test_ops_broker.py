from __future__ import annotations

import asyncio

from amodb.apps.platform.ops_broker import PreparedSnapshotBroker, RefreshBatch


def test_broker_refresh_rate_is_independent_of_subscriber_count():
    calls = 0

    def refresh(cursor, include_snapshot):
        nonlocal calls
        calls += 1
        snapshot = {"status": "HEALTHY", "value": calls} if include_snapshot else None
        return RefreshBatch(snapshot=snapshot, cursor=str(calls))

    async def scenario():
        broker = PreparedSnapshotBroker(
            refresh,
            poll_interval_seconds=0.02,
            snapshot_interval_seconds=0.04,
        )
        await broker.ensure_started()
        await broker.snapshot(timeout_seconds=1)

        async def consume_one():
            async for message in broker.stream():
                if message is not None:
                    return message

        await asyncio.gather(*(consume_one() for _ in range(100)))
        await asyncio.sleep(0.08)
        # Quiesce the broker before comparing its completed-refresh counter with
        # the callback counter. Sampling while asyncio.to_thread is in flight can
        # observe the callback's first instruction before the event-loop task has
        # published the corresponding health update, producing a false 4-vs-5
        # failure without any subscriber fan-out regression.
        await broker.stop()
        return broker.health()

    health = asyncio.run(scenario())
    assert calls < 20, "100 subscribers must not produce 100x refresh work"
    assert health["refresh_count"] == calls
    assert health["subscriber_count"] == 0


def test_broker_retains_last_good_snapshot_when_refresh_fails():
    calls = 0

    def refresh(cursor, include_snapshot):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise RuntimeError("telemetry source unavailable")
        return RefreshBatch(snapshot={"status": "HEALTHY", "marker": "last-good"}, cursor="1")

    async def scenario():
        broker = PreparedSnapshotBroker(
            refresh,
            poll_interval_seconds=0.02,
            snapshot_interval_seconds=0.04,
        )
        first = await broker.snapshot(timeout_seconds=1)
        await asyncio.sleep(0.08)
        second = await broker.snapshot(timeout_seconds=1)
        health = broker.health()
        await broker.stop()
        return first, second, health

    first, second, health = asyncio.run(scenario())
    assert first["marker"] == "last-good"
    assert second["marker"] == "last-good"
    assert health["refresh_failures"] >= 1
    assert health["status"] == "degraded"


def test_last_event_id_parser_is_backward_compatible_and_safe():
    assert PreparedSnapshotBroker.parse_sequence("ops:41") == 41
    assert PreparedSnapshotBroker.parse_sequence("42") == 42
    assert PreparedSnapshotBroker.parse_sequence("legacy-audit-cursor") == 0
    assert PreparedSnapshotBroker.parse_sequence(None) == 0
