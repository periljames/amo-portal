"""Production concurrency helpers that keep synchronous maintenance I/O off ASGI loops."""
from __future__ import annotations

import logging
import os
import threading
import time
from types import ModuleType
from typing import Callable

logger = logging.getLogger(__name__)


class RuntimeMaintenanceCoordinator:
    """Flush request-usage metrics and refresh settings on a background thread.

    ``amodb.main`` intentionally keeps synchronous SQLAlchemy sessions for the
    application service layer. The HTTP middleware must therefore never perform
    those periodic maintenance queries directly on the asyncio event loop. This
    coordinator replaces only the two middleware-facing helpers with non-blocking
    cache/queue operations; authoritative writes still use the existing service
    functions and database sessions on a dedicated thread.
    """

    def __init__(self, core: ModuleType) -> None:
        self.core = core
        self._stop = threading.Event()
        self._wakeup = threading.Event()
        self._thread: threading.Thread | None = None
        self._sync_settings_reader: Callable[[], object | None] = core._get_platform_settings_cached
        self._installed = False

    def install(self) -> None:
        if self._installed:
            return
        self._installed = True
        self.core._queue_api_usage = self.queue_api_usage
        self.core._get_platform_settings_cached = self.cached_platform_settings
        self.core.app.add_event_handler("startup", self.start)
        self.core.app.add_event_handler("shutdown", self.stop)

    def cached_platform_settings(self):
        return self.core._platform_settings_cache.get("data")

    def queue_api_usage(self, amo_id: str) -> None:
        if not amo_id:
            return
        with self.core._api_usage_lock:
            pending = self.core._api_usage_pending
            pending[amo_id] = pending.get(amo_id, 0) + 1
            total = sum(pending.values())
        if total >= max(1, int(self.core._api_usage_flush_batch_size)):
            self._wakeup.set()

    def _flush_usage(self) -> None:
        with self.core._api_usage_lock:
            if not self.core._api_usage_pending:
                return
            payload = dict(self.core._api_usage_pending)
            self.core._api_usage_pending.clear()
            self.core._api_usage_last_flush = time.monotonic()

        db = self.core.WriteSessionLocal()
        try:
            for amo_id, quantity in payload.items():
                if quantity <= 0:
                    continue
                self.core.account_services.record_usage(
                    db,
                    amo_id=amo_id,
                    meter_key=self.core.account_services.METER_KEY_API_CALLS,
                    quantity=quantity,
                )
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            with self.core._api_usage_lock:
                for amo_id, quantity in payload.items():
                    self.core._api_usage_pending[amo_id] = self.core._api_usage_pending.get(amo_id, 0) + quantity
            logger.warning("Deferred API usage flush failed; batch re-queued", exc_info=True)
        finally:
            self.core.close_session_safely(db)

    def _refresh_platform_settings(self) -> None:
        try:
            self._sync_settings_reader()
        except Exception:
            logger.debug("Background platform settings refresh failed", exc_info=True)

    def _run(self) -> None:
        flush_interval = max(0.25, float(os.getenv("API_USAGE_FLUSH_INTERVAL_SEC", "5") or "5"))
        settings_interval = max(1.0, float(os.getenv("PLATFORM_SETTINGS_CACHE_TTL_SEC", "30") or "30"))
        next_flush = time.monotonic() + flush_interval
        next_settings = time.monotonic() + settings_interval

        while not self._stop.is_set():
            deadline = min(next_flush, next_settings)
            timeout = max(0.05, deadline - time.monotonic())
            self._wakeup.wait(timeout=timeout)
            self._wakeup.clear()
            if self._stop.is_set():
                break

            now = time.monotonic()
            if now >= next_flush:
                self._flush_usage()
                next_flush = now + flush_interval
            else:
                with self.core._api_usage_lock:
                    due_by_size = sum(self.core._api_usage_pending.values()) >= max(
                        1, int(self.core._api_usage_flush_batch_size)
                    )
                if due_by_size:
                    self._flush_usage()
                    next_flush = now + flush_interval

            if now >= next_settings:
                self._refresh_platform_settings()
                next_settings = now + settings_interval

        self._flush_usage()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._wakeup.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="portal-runtime-maintenance",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wakeup.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=max(1.0, float(os.getenv("AMODB_SHUTDOWN_STEP_TIMEOUT_SEC", "3") or "3")))
        self._thread = None
        # If a slow database flush outlived the bounded join, leave shutdown to
        # the existing engine-disposal guard rather than blocking indefinitely.


def install_runtime_concurrency(core: ModuleType) -> RuntimeMaintenanceCoordinator:
    coordinator = RuntimeMaintenanceCoordinator(core)
    coordinator.install()
    return coordinator
