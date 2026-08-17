"""Shared database availability circuit used by API and embedded workers.

The circuit deliberately keeps no business data.  It only prevents every
request and worker thread from opening another PostgreSQL connection while a
known outage is in progress.  One readiness probe is allowed at a time; a
successful probe closes the circuit immediately.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _bounded_float_alias(primary: str, legacy: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(primary)
    if raw is None or not raw.strip():
        raw = os.getenv(legacy)
    try:
        value = float(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


class DatabaseCircuitBreaker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._probe_lock = threading.Lock()
        self._state = "online"
        self._consecutive_failures = 0
        self._probe_failures = 0
        self._opened_at: float | None = None
        self._next_probe_at = 0.0
        self._last_failure_at: float | None = None
        self._last_success_at = time.time()
        self._last_error: str | None = None
        self._failure_threshold = _bounded_int("DB_CIRCUIT_FAILURE_THRESHOLD", 3, 1, 20)
        self._base_delay = _bounded_float_alias(
            "DB_CIRCUIT_BASE_RETRY_SECONDS", "DB_CIRCUIT_BASE_DELAY_SEC", 2.0, 0.25, 30.0
        )
        self._max_delay = _bounded_float_alias(
            "DB_CIRCUIT_MAX_RETRY_SECONDS", "DB_CIRCUIT_MAX_DELAY_SEC", 60.0, 2.0, 300.0
        )

    @staticmethod
    def _utc_iso(epoch: float | None) -> str | None:
        if epoch is None:
            return None
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()

    def _delay(self) -> float:
        exponent = max(0, min(self._probe_failures - 1, 8))
        return min(self._max_delay, self._base_delay * (2**exponent))

    def mark_failure(self, error: BaseException | str) -> bool:
        """Open the circuit and return True only for the outage transition."""
        now_mono = time.monotonic()
        now_epoch = time.time()
        message = str(error).strip()[:500] or type(error).__name__
        with self._lock:
            self._consecutive_failures += 1
            self._probe_failures += 1
            self._last_failure_at = now_epoch
            self._last_error = message
            transitioned = self._state == "online" and self._consecutive_failures >= self._failure_threshold
            if transitioned:
                self._state = "offline"
                self._opened_at = self._opened_at or now_epoch
            if self._state == "offline":
                self._next_probe_at = now_mono + self._delay()
            return transitioned

    def mark_success(self) -> bool:
        """Close the circuit and return True only for an outage recovery."""
        now_epoch = time.time()
        with self._lock:
            recovered = self._state != "online"
            self._state = "online"
            self._consecutive_failures = 0
            self._probe_failures = 0
            self._opened_at = None
            self._next_probe_at = 0.0
            self._last_error = None
            self._last_success_at = now_epoch
            return recovered

    def allow_request(self) -> bool:
        with self._lock:
            return self._state == "online"

    def begin_probe(self, *, force: bool = False) -> bool:
        now = time.monotonic()
        with self._lock:
            if not force and self._state != "online" and now < self._next_probe_at:
                return False
        return self._probe_lock.acquire(blocking=False)

    def end_probe(self) -> None:
        if self._probe_lock.locked():
            self._probe_lock.release()

    def retry_after_seconds(self) -> int:
        with self._lock:
            return max(1, int(max(0.0, self._next_probe_at - time.monotonic()) + 0.999))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self._state,
                "available": self._state == "online",
                "consecutive_failures": self._consecutive_failures,
                "failure_threshold": self._failure_threshold,
                "retry_after_seconds": max(
                    0,
                    int(max(0.0, self._next_probe_at - time.monotonic()) + 0.999),
                ),
                "opened_at": self._utc_iso(self._opened_at),
                "last_failure_at": self._utc_iso(self._last_failure_at),
                "last_success_at": self._utc_iso(self._last_success_at),
                "last_error": self._last_error,
            }


database_circuit = DatabaseCircuitBreaker()


def is_database_disconnect(error: BaseException) -> bool:
    message = str(error).lower()
    return any(
        fragment in message
        for fragment in (
            "connection timed out",
            "connection refused",
            "connection reset",
            "connection is closed",
            "connection already closed",
            "server closed the connection",
            "ssl connection has been closed",
            "could not connect to server",
            "no connection to the server",
            "terminating connection",
            "database system is starting up",
            "database system is in recovery mode",
        )
    )
