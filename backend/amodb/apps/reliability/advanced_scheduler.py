from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import WriteSessionLocal, close_session_safely, probe_database
from amodb.database_resilience import database_circuit, is_database_disconnect

from . import advanced_models as domain
from . import advanced_services as services


logger = logging.getLogger(__name__)
_LOCK_KEY = 618_245_913
_stop_event = threading.Event()
_thread: threading.Thread | None = None
_state_lock = threading.Lock()


def _enabled() -> bool:
    value = (os.getenv("RELIABILITY_SCHEDULER_ENABLED") or "true").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _interval_seconds() -> int:
    try:
        return max(int(os.getenv("RELIABILITY_SCHEDULER_INTERVAL_SEC", "3600")), 60)
    except ValueError:
        return 3600


@contextmanager
def _advisory_lock(db: Session) -> Iterator[bool]:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        yield True
        return
    acquired = bool(db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _LOCK_KEY}).scalar())
    try:
        yield acquired
    finally:
        if acquired:
            try:
                db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _LOCK_KEY})
            except Exception:
                logger.debug("Reliability scheduler advisory unlock failed", exc_info=True)


def _accountable_actor_id(db: Session, *, amo_id: str) -> str | None:
    """Resolve the recorded owner whose approved setup authorises automation.

    Scheduled ingestion must not be attributed to an arbitrary active user. The
    actor is taken first from the tenant's active Reliability source ownership,
    then from the latest Reliability programme approval/creation trail.
    """
    source_row = (
        db.query(domain.ReliabilitySource.created_by_user_id)
        .filter(
            domain.ReliabilitySource.amo_id == amo_id,
            domain.ReliabilitySource.status == "ACTIVE",
            domain.ReliabilitySource.created_by_user_id.is_not(None),
        )
        .order_by(
            domain.ReliabilitySource.updated_at.desc(),
            domain.ReliabilitySource.id.desc(),
        )
        .first()
    )
    if source_row and source_row[0]:
        return str(source_row[0])

    programme_row = (
        db.query(
            domain.ReliabilityProgrammeVersion.approved_by_user_id,
            domain.ReliabilityProgrammeVersion.created_by_user_id,
        )
        .filter(domain.ReliabilityProgrammeVersion.amo_id == amo_id)
        .order_by(
            domain.ReliabilityProgrammeVersion.updated_at.desc(),
            domain.ReliabilityProgrammeVersion.id.desc(),
        )
        .first()
    )
    if programme_row:
        actor_user_id = programme_row[0] or programme_row[1]
        if actor_user_id:
            return str(actor_user_id)
    return None


def run_reliability_cycle() -> dict[str, int]:
    db = WriteSessionLocal()
    harvested = 0
    calculations = 0
    tenants = 0
    try:
        with _advisory_lock(db) as acquired:
            if not acquired:
                return {"tenants": 0, "harvested_batches": 0, "calculation_runs": 0}
            amo_ids = {
                str(row[0])
                for row in db.query(domain.ReliabilitySource.amo_id)
                .filter(domain.ReliabilitySource.status == "ACTIVE")
                .distinct()
                .all()
            }
            amo_ids.update(
                str(row[0])
                for row in db.query(domain.ReliabilityMetricDefinition.amo_id)
                .filter(domain.ReliabilityMetricDefinition.active.is_(True))
                .distinct()
                .all()
            )
            tenants = len(amo_ids)
            for amo_id in sorted(amo_ids):
                try:
                    actor_user_id = _accountable_actor_id(db, amo_id=amo_id)
                    if actor_user_id:
                        harvested += len(
                            services.harvest_internal_sources(
                                db,
                                amo_id=amo_id,
                                actor_user_id=actor_user_id,
                            )
                        )
                    else:
                        logger.warning(
                            "Reliability internal-source harvest skipped for tenant %s: "
                            "no accountable source or programme owner is recorded",
                            amo_id,
                        )
                    calculations += len(
                        services.run_due_metrics(
                            db,
                            amo_id=amo_id,
                            actor_user_id=actor_user_id,
                        )
                    )
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    logger.exception("Reliability scheduled cycle failed for tenant %s", amo_id)
    finally:
        close_session_safely(db)
    return {
        "tenants": tenants,
        "harvested_batches": harvested,
        "calculation_runs": calculations,
    }


def _worker() -> None:
    while not _stop_event.is_set():
        if not probe_database():
            _stop_event.wait(database_circuit.retry_after_seconds())
            continue
        try:
            result = run_reliability_cycle()
            logger.info("Reliability scheduler cycle completed: %s", result)
        except Exception as exc:
            if is_database_disconnect(exc):
                database_circuit.mark_failure(exc)
                _stop_event.wait(database_circuit.retry_after_seconds())
                continue
            logger.exception("Reliability scheduler cycle failed")
        _stop_event.wait(_interval_seconds())


def start_reliability_scheduler() -> None:
    global _thread
    if not _enabled():
        logger.info("Reliability scheduler is disabled by configuration")
        return
    with _state_lock:
        if _thread and _thread.is_alive():
            return
        _stop_event.clear()
        _thread = threading.Thread(
            target=_worker,
            name="reliability-scheduler",
            daemon=True,
        )
        _thread.start()


def stop_reliability_scheduler() -> None:
    global _thread
    with _state_lock:
        thread = _thread
        _stop_event.set()
        _thread = None
    if thread and thread.is_alive():
        thread.join(timeout=5)
