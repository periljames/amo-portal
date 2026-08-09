from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Callable


@dataclass(frozen=True)
class RefreshBatch:
    """One prepared control-plane refresh produced independently of browsers."""

    snapshot: dict[str, Any] | None
    events: tuple[tuple[str, dict[str, Any]], ...] = ()
    cursor: str | None = None


@dataclass(frozen=True)
class PreparedMessage:
    sequence: int
    event: str
    payload: dict[str, Any]
    created_at: str


RefreshFunction = Callable[[str | None, bool], RefreshBatch]


class PreparedSnapshotBroker:
    """Refresh once, fan out many.

    The refresh function is called on a fixed cadence in a background task. SSE
    subscribers only consume the bounded in-memory replay buffer; adding browser
    sessions cannot increase database polling frequency.
    """

    def __init__(
        self,
        refresh: RefreshFunction,
        *,
        poll_interval_seconds: float = 2.0,
        snapshot_interval_seconds: float = 10.0,
        replay_limit: int = 512,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if snapshot_interval_seconds < poll_interval_seconds:
            raise ValueError("snapshot_interval_seconds must be >= poll_interval_seconds")
        self._refresh = refresh
        self._poll_interval = float(poll_interval_seconds)
        self._snapshot_interval = float(snapshot_interval_seconds)
        self._messages: deque[PreparedMessage] = deque(maxlen=max(32, int(replay_limit)))
        self._condition = asyncio.Condition()
        self._start_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._cursor: str | None = None
        self._sequence = 0
        self._latest_snapshot: dict[str, Any] | None = None
        self._latest_snapshot_at: str | None = None
        self._last_success_at: str | None = None
        self._last_error: str | None = None
        self._refresh_count = 0
        self._refresh_failures = 0
        self._subscriber_count = 0
        self._running = False

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def ensure_started(self) -> None:
        async with self._start_lock:
            if self._task and not self._task.done():
                return
            self._task = asyncio.create_task(self._run(), name="platform-ops-prepared-snapshot-broker")

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if not task:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _publish(self, event: str, payload: dict[str, Any]) -> PreparedMessage:
        async with self._condition:
            self._sequence += 1
            message = PreparedMessage(
                sequence=self._sequence,
                event=event,
                payload=payload,
                created_at=self._now(),
            )
            self._messages.append(message)
            self._condition.notify_all()
            return message

    async def _run(self) -> None:
        self._running = True
        loop = asyncio.get_running_loop()
        next_snapshot_at = 0.0
        try:
            while True:
                include_snapshot = loop.time() >= next_snapshot_at or self._latest_snapshot is None
                try:
                    batch = await asyncio.to_thread(self._refresh, self._cursor, include_snapshot)
                    self._refresh_count += 1
                    self._last_success_at = self._now()
                    self._last_error = None
                    if batch.cursor is not None:
                        self._cursor = batch.cursor
                    for event_name, event_payload in batch.events:
                        await self._publish(event_name, event_payload)
                    if batch.snapshot is not None:
                        prepared = dict(batch.snapshot)
                        prepared.setdefault("generated_at", self._now())
                        prepared["prepared_snapshot"] = True
                        prepared["data_mode"] = str(prepared.get("data_mode") or "REAL").upper()
                        prepared["data_provenance"] = {
                            "source": "platform-ops-gateway",
                            "synthetic": prepared["data_mode"] == "DEMO",
                            "prepared": True,
                        }
                        self._latest_snapshot = prepared
                        self._latest_snapshot_at = self._now()
                        await self._publish(
                            "snapshot",
                            {
                                "type": "platform.snapshot",
                                "snapshot": prepared,
                                "created_at": self._latest_snapshot_at,
                            },
                        )
                        next_snapshot_at = loop.time() + self._snapshot_interval
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # failure isolation is intentional
                    self._refresh_failures += 1
                    self._last_error = f"{type(exc).__name__}: {exc}"
                    await self._publish(
                        "gateway.degraded",
                        {
                            "type": "platform.gateway.degraded",
                            "stale_snapshot_available": self._latest_snapshot is not None,
                            "refresh_failures": self._refresh_failures,
                            "created_at": self._now(),
                        },
                    )
                await asyncio.sleep(self._poll_interval)
        finally:
            self._running = False

    async def snapshot(self, timeout_seconds: float = 5.0) -> dict[str, Any]:
        await self.ensure_started()
        if self._latest_snapshot is not None:
            return dict(self._latest_snapshot)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.1, timeout_seconds)
        while self._latest_snapshot is None and loop.time() < deadline:
            remaining = max(0.05, deadline - loop.time())
            try:
                async with self._condition:
                    await asyncio.wait_for(self._condition.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                break
        if self._latest_snapshot is None:
            return {
                "status": "UNAVAILABLE",
                "data_mode": "REAL",
                "prepared_snapshot": False,
                "generated_at": self._now(),
                "data_provenance": {
                    "source": "platform-ops-gateway",
                    "synthetic": False,
                    "prepared": False,
                },
            }
        return dict(self._latest_snapshot)

    @staticmethod
    def parse_sequence(last_event_id: str | None) -> int:
        raw = str(last_event_id or "").strip()
        if raw.startswith("ops:"):
            raw = raw[4:]
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return 0

    async def stream(self, last_event_id: str | None = None) -> AsyncGenerator[PreparedMessage | None, None]:
        await self.ensure_started()
        cursor = self.parse_sequence(last_event_id)
        self._subscriber_count += 1
        try:
            if cursor == 0:
                snapshots = [message for message in self._messages if message.event == "snapshot"]
                if snapshots:
                    cursor = max(0, snapshots[-1].sequence - 1)
            while True:
                pending = [message for message in self._messages if message.sequence > cursor]
                if pending:
                    for message in pending:
                        cursor = message.sequence
                        yield message
                    continue
                try:
                    async with self._condition:
                        await asyncio.wait_for(self._condition.wait(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield None
        finally:
            self._subscriber_count = max(0, self._subscriber_count - 1)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok" if self._running and not self._last_error else ("degraded" if self._running else "starting"),
            "running": self._running,
            "prepared_snapshot": self._latest_snapshot is not None,
            "latest_snapshot_at": self._latest_snapshot_at,
            "last_success_at": self._last_success_at,
            "last_error": self._last_error,
            "refresh_count": self._refresh_count,
            "refresh_failures": self._refresh_failures,
            "subscriber_count": self._subscriber_count,
            "replay_depth": len(self._messages),
            "sequence": self._sequence,
            "poll_interval_seconds": self._poll_interval,
            "snapshot_interval_seconds": self._snapshot_interval,
        }
