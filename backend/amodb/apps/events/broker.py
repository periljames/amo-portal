from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Iterable, Optional


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
    def __init__(self, replay_size: int = 2000) -> None:
        self._subscribers: set[queue.Queue[EventEnvelope]] = set()
        self._history: Deque[EventEnvelope] = deque(maxlen=replay_size)
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue[EventEnvelope]:
        q: queue.Queue[EventEnvelope] = queue.Queue(maxsize=400)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue[EventEnvelope]) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def replay_since(self, *, last_event_id: str, amo_id: Optional[str]) -> tuple[list[EventEnvelope], bool]:
        with self._lock:
            history = list(self._history)
        if not history:
            return [], False
        ids = [event.id for event in history]
        if last_event_id not in ids:
            return [], True
        start_index = ids.index(last_event_id) + 1
        replay = history[start_index:]
        if amo_id:
            replay = [
                event
                for event in replay
                if str((event.metadata or {}).get("amoId", "")) == str(amo_id)
            ]
        return replay, False

    def publish(self, event: EventEnvelope) -> None:
        with self._lock:
            self._history.append(event)
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


def format_sse(data: str, event: Optional[str] = None, event_id: Optional[str] = None) -> str:
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    if event:
        lines.append(f"event: {event}")
    for chunk in data.splitlines():
        lines.append(f"data: {chunk}")
    lines.append("")
    return "\n".join(lines) + "\n"


def keepalive_message() -> str:
    payload = json.dumps({"type": "heartbeat", "ts": time.time()})
    return format_sse(payload, event="heartbeat")
