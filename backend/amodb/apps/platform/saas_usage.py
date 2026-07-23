from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import services as account_services
from amodb.database import WriteSessionLocal, close_session_safely
from amodb.user_id import generate_user_id


_INSTALLED = False
_ORIGINAL_RECORD_USAGE = account_services.record_usage
_STOP_EVENT = threading.Event()
_FLUSH_THREAD: threading.Thread | None = None


def atomic_record_usage(
    db: Session,
    *,
    amo_id: str,
    meter_key: str,
    quantity: int,
    license_id: Optional[str] = None,
    at: Optional[datetime] = None,
    attach_license: bool = True,
    commit: bool = True,
) -> account_models.UsageMeter:
    """Increment one meter without a read/modify/write race.

    PostgreSQL uses a single ``INSERT .. ON CONFLICT .. DO UPDATE`` statement,
    which safely combines increments from many API and worker processes. Test
    and development databases retain the existing ORM implementation.
    """

    if quantity < 0:
        raise ValueError("Quantity must be non-negative.")
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return _ORIGINAL_RECORD_USAGE(
            db,
            amo_id=amo_id,
            meter_key=meter_key,
            quantity=quantity,
            license_id=license_id,
            at=at,
            attach_license=attach_license,
            commit=commit,
        )

    recorded_at = at or datetime.now(timezone.utc)
    resolved_license_id = license_id
    if attach_license and not resolved_license_id:
        current = account_services.get_current_subscription(db, amo_id=amo_id)
        resolved_license_id = current.id if current else None

    meter_id = db.execute(
        text(
            """
            INSERT INTO usage_meters (
                id, amo_id, license_id, meter_key, used_units,
                last_recorded_at, created_at, updated_at
            ) VALUES (
                :id, :amo_id, :license_id, :meter_key, :quantity,
                :recorded_at, :recorded_at, :recorded_at
            )
            ON CONFLICT (amo_id, meter_key)
            DO UPDATE SET
                used_units = usage_meters.used_units + EXCLUDED.used_units,
                license_id = COALESCE(usage_meters.license_id, EXCLUDED.license_id),
                last_recorded_at = EXCLUDED.last_recorded_at,
                updated_at = EXCLUDED.updated_at
            RETURNING id
            """
        ),
        {
            "id": generate_user_id(),
            "amo_id": amo_id,
            "license_id": resolved_license_id,
            "meter_key": meter_key,
            "quantity": int(quantity),
            "recorded_at": recorded_at,
        },
    ).scalar_one()
    if commit:
        db.commit()
    else:
        db.flush()
    meter = db.get(account_models.UsageMeter, meter_id)
    if meter is None:
        raise RuntimeError("Usage meter upsert completed but the row could not be reloaded")
    return meter


def _install_atomic_function() -> None:
    account_services.record_usage = atomic_record_usage


def install_usage_meter_hardening(router: APIRouter) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_atomic_function()

    @router.on_event("startup")
    def start_usage_flush_thread() -> None:
        global _FLUSH_THREAD
        from amodb import main as application

        # Keep request work to an in-memory increment. The daemon owns all
        # periodic database flushes for this API process.
        def enqueue_only(amo_id: str) -> None:
            if not amo_id:
                return
            with application._api_usage_lock:
                application._api_usage_pending[amo_id] = application._api_usage_pending.get(amo_id, 0) + 1

        def flush_with_requeue() -> None:
            """Persist one batch and restore it atomically after transient failure."""

            with application._api_usage_lock:
                if not application._api_usage_pending:
                    return
                payload_to_flush = dict(application._api_usage_pending)
                application._api_usage_pending.clear()
                application._api_usage_last_flush = time.monotonic()

            db = WriteSessionLocal()
            try:
                for pending_amo_id, quantity in payload_to_flush.items():
                    if quantity <= 0:
                        continue
                    account_services.record_usage(
                        db,
                        amo_id=pending_amo_id,
                        meter_key=account_services.METER_KEY_API_CALLS,
                        quantity=quantity,
                        commit=False,
                    )
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
                with application._api_usage_lock:
                    for pending_amo_id, quantity in payload_to_flush.items():
                        application._api_usage_pending[pending_amo_id] = (
                            application._api_usage_pending.get(pending_amo_id, 0) + quantity
                        )
            finally:
                close_session_safely(db)

        application._queue_api_usage = enqueue_only
        application._flush_api_usage_metrics = flush_with_requeue
        _STOP_EVENT.clear()
        interval = max(0.5, float(os.getenv("API_USAGE_FLUSH_INTERVAL_SEC", "5") or "5"))

        def loop() -> None:
            while not _STOP_EVENT.wait(interval):
                application._flush_api_usage_metrics()

        if _FLUSH_THREAD is None or not _FLUSH_THREAD.is_alive():
            _FLUSH_THREAD = threading.Thread(
                target=loop,
                name="api-usage-flush",
                daemon=True,
            )
            _FLUSH_THREAD.start()

    @router.on_event("shutdown")
    def stop_usage_flush_thread() -> None:
        from amodb import main as application

        _STOP_EVENT.set()
        if _FLUSH_THREAD and _FLUSH_THREAD.is_alive():
            _FLUSH_THREAD.join(timeout=2.0)
        application._flush_api_usage_metrics()

    _INSTALLED = True
