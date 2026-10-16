import asyncio
import threading
from types import SimpleNamespace

from amodb.apps.events.broker import EventBroker, EventEnvelope
from amodb.apps.events import router


def event(identifier="one"):
    return EventEnvelope(identifier, "work.updated", "work", "task", "UPDATED", "2026-10-16T12:00:00Z")


def test_publish_from_worker_delivers_to_concurrent_async_subscribers():
    async def run():
        broker = EventBroker()
        subscribers = [broker.subscribe_async() for _ in range(200)]
        publisher = threading.Thread(target=broker.publish, args=(event(),))
        publisher.start()
        publisher.join()
        received = await asyncio.wait_for(asyncio.gather(*(q.get() for q in subscribers)), 2)
        assert all(row.id == "one" for row in received)
        for q in subscribers:
            broker.unsubscribe_async(q)
        assert not broker._async_subscribers
    asyncio.run(run())


def test_slow_subscriber_is_bounded_and_preserves_latest_event():
    async def run():
        broker = EventBroker()
        q = broker.subscribe_async()
        for index in range(450):
            broker.publish(event(str(index)))
        await asyncio.sleep(0)
        assert q.qsize() == 400
        assert q.get_nowait().id == "50"
        while q.qsize() > 1:
            q.get_nowait()
        assert q.get_nowait().id == "449"
    asyncio.run(run())


def test_stream_bootstrap_does_not_run_sql_on_event_loop(monkeypatch):
    loop_thread = threading.get_ident()
    def bootstrap(_request):
        assert threading.get_ident() != loop_thread
        return SimpleNamespace(amo_id="amo"), [], None, set()
    monkeypatch.setattr(router, "_prepare_stream_bootstrap", bootstrap)
    assert asyncio.run(router.stream_events(SimpleNamespace())).media_type == "text/event-stream"
