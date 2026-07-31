from __future__ import annotations

import logging
import os
import threading

from fastapi import APIRouter

from . import metrics

logger = logging.getLogger(__name__)

_INSTALLED = False
_STOP_EVENT = threading.Event()
_FLUSH_THREAD: threading.Thread | None = None


def _flush_current_bucket_safely() -> None:
    try:
        metrics.flush_current_process_metrics()
    except Exception:
        logger.warning(
            "Unable to persist the current platform metric bucket.",
            exc_info=True,
        )


def install_platform_metrics_lifecycle(router: APIRouter) -> None:
    """Persist each API worker's current metric bucket on a real timer.

    Route metrics are process-local while requests are being recorded. Every
    API worker therefore owns a small lifecycle thread that writes its partial
    current bucket to shared PostgreSQL storage. The summary endpoint can then
    combine all workers instead of seeing only the worker that served it.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    @router.on_event("startup")
    def start_platform_metric_flush_thread() -> None:
        global _FLUSH_THREAD

        interval = max(
            2.0,
            float(
                os.getenv("PLATFORM_METRICS_CURRENT_FLUSH_INTERVAL_SEC", "10")
                or "10"
            ),
        )
        _STOP_EVENT.clear()

        def loop() -> None:
            while not _STOP_EVENT.wait(interval):
                _flush_current_bucket_safely()

        if _FLUSH_THREAD is None or not _FLUSH_THREAD.is_alive():
            _FLUSH_THREAD = threading.Thread(
                target=loop,
                name="platform-current-metrics-flush",
                daemon=True,
            )
            _FLUSH_THREAD.start()

    @router.on_event("shutdown")
    def stop_platform_metric_flush_thread() -> None:
        global _FLUSH_THREAD

        _STOP_EVENT.set()
        thread = _FLUSH_THREAD
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        _FLUSH_THREAD = None
        _flush_current_bucket_safely()
