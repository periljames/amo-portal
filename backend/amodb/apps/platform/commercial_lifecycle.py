from __future__ import annotations

import logging
import os
import threading

from fastapi import APIRouter

from amodb.database import WriteSessionLocal, close_session_safely

from .commercial_integrity import _apply_due_cancellations

logger = logging.getLogger(__name__)

_INSTALLED = False
_STOP_EVENT = threading.Event()
_LIFECYCLE_THREAD: threading.Thread | None = None


def _apply_due_cancellations_safely() -> int:
    db = WriteSessionLocal()
    try:
        return _apply_due_cancellations(db, commit=True)
    except Exception:
        db.rollback()
        logger.warning("Unable to apply due commercial subscription transitions.", exc_info=True)
        return 0
    finally:
        close_session_safely(db)


def install_commercial_lifecycle(router: APIRouter) -> None:
    """Persist scheduled subscription transitions independently of read traffic."""

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    @router.on_event("startup")
    def start_commercial_lifecycle_thread() -> None:
        global _LIFECYCLE_THREAD

        interval = max(
            5.0,
            float(os.getenv("COMMERCIAL_LIFECYCLE_INTERVAL_SEC", "30") or "30"),
        )
        _STOP_EVENT.clear()
        _apply_due_cancellations_safely()

        def loop() -> None:
            while not _STOP_EVENT.wait(interval):
                applied = _apply_due_cancellations_safely()
                if applied:
                    logger.info("Applied %s due commercial subscription transition(s).", applied)

        if _LIFECYCLE_THREAD is None or not _LIFECYCLE_THREAD.is_alive():
            _LIFECYCLE_THREAD = threading.Thread(
                target=loop,
                name="commercial-subscription-lifecycle",
                daemon=True,
            )
            _LIFECYCLE_THREAD.start()

    @router.on_event("shutdown")
    def stop_commercial_lifecycle_thread() -> None:
        global _LIFECYCLE_THREAD

        _STOP_EVENT.set()
        thread = _LIFECYCLE_THREAD
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        _LIFECYCLE_THREAD = None
        _apply_due_cancellations_safely()


__all__ = ["install_commercial_lifecycle"]
