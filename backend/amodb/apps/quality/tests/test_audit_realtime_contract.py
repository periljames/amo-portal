from __future__ import annotations

from amodb.apps.events.broker import EventBroker, EventEnvelope


def event(event_id: str, amo_id: str) -> EventEnvelope:
    return EventEnvelope(
        id=event_id,
        type="qms.audit.checklist_item.updated",
        entityType="qms.audit.checklist_item",
        entityId=f"item-{event_id}",
        action="UPDATED",
        timestamp="2026-08-16T12:00:00+00:00",
        actor={"userId": "auditor-1"},
        metadata={"amoId": amo_id, "module": "quality", "auditId": "audit-1"},
    )


def test_replay_returns_only_events_after_last_seen_in_original_order() -> None:
    broker = EventBroker(replay_size=10)
    broker.publish(event("e1", "tenant-a"))
    broker.publish(event("e2", "tenant-a"))
    broker.publish(event("e3", "tenant-a"))

    replay, reset_required = broker.replay_since(last_event_id="e1", amo_id="tenant-a")
    assert reset_required is False
    assert [row.id for row in replay] == ["e2", "e3"]


def test_replay_is_tenant_filtered_after_reconnect() -> None:
    broker = EventBroker(replay_size=10)
    broker.publish(event("e1", "tenant-a"))
    broker.publish(event("e2", "tenant-b"))
    broker.publish(event("e3", "tenant-a"))

    replay, reset_required = broker.replay_since(last_event_id="e1", amo_id="tenant-a")
    assert reset_required is False
    assert [row.id for row in replay] == ["e3"]


def test_out_of_window_last_event_id_requires_reset() -> None:
    broker = EventBroker(replay_size=2)
    broker.publish(event("e1", "tenant-a"))
    broker.publish(event("e2", "tenant-a"))
    broker.publish(event("e3", "tenant-a"))

    replay, reset_required = broker.replay_since(last_event_id="e1", amo_id="tenant-a")
    assert replay == []
    assert reset_required is True


def test_live_subscription_receives_committed_event_envelope() -> None:
    broker = EventBroker(replay_size=4)
    subscription = broker.subscribe()
    try:
        broker.publish(event("e1", "tenant-a"))
        received = subscription.get_nowait()
        assert received.id == "e1"
        assert received.metadata["amoId"] == "tenant-a"
    finally:
        broker.unsubscribe(subscription)
