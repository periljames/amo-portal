from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional


@dataclass
class EventEnvelope:
    id: str
    type: str
    entityType: str
    entityId: str
    action: str
    timestamp: str
    actor: Optional[Dict[str, Any]]
    metadata: Dict[str, Any]

    def to_json(self) -> str:
        payload = {
            "id": self.id,
            "type": self.type,
            "entityType": self.entityType,
            "entityId": self.entityId,
            "action": self.action,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "metadata": self.metadata,
        }
        return json.dumps(payload, default=str)


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: set[queue.Queue[EventEnvelope]] = set()
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue[EventEnvelope]:
        q: queue.Queue[EventEnvelope] = queue.Queue(maxsize=200)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue[EventEnvelope]) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, event: EventEnvelope) -> None:
        with self._lock:
            subscribers: Iterable[queue.Queue[EventEnvelope]] = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                try:
                    _ = q.get_nowait()
                    q.put_nowait(event)
                except queue.Empty:
                    pass


broker = EventBroker()


def publish_event(event: EventEnvelope) -> None:
    broker.publish(event)


def format_sse(data: str, event: Optional[str] = None) -> str:
    lines = []
    if event:
        lines.append(f"event: {event}")
    for chunk in data.splitlines():
        lines.append(f"data: {chunk}")
    lines.append("")
    return "\n".join(lines) + "\n"


def keepalive_message() -> str:
    payload = json.dumps({"type": "heartbeat", "ts": time.time()})
    return format_sse(payload, event="heartbeat")
