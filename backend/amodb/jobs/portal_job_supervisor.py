"""Durable-job runtime shared by embedded development and dedicated workers.

Production keeps workers outside Uvicorn so CPU-heavy jobs cannot starve API
requests or multiply its connection pool. Development may explicitly opt in to
embedded threads with ``PORTAL_EMBEDDED_JOB_WORKER=1``. Embedded execution is
also guarded by a bounded work semaphore so queue families cannot all contend
for the API database pool at once.
"""
from __future__ import annotations

import logging
import os
import random
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from amodb.apps.platform import models as platform_models
from amodb.database import WriteSessionLocal, close_session_safely, probe_database
from amodb.database_resilience import database_circuit, is_database_disconnect


logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def embedded_worker_enabled() -> bool:
    # Background queues are isolated by default. A small single-process
    # deployment may opt in explicitly, but it will still use bounded cycles.
    return _env_bool("PORTAL_EMBEDDED_JOB_WORKER", False)


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


def _identity() -> str:
    configured = (os.getenv("PORTAL_JOB_SUPERVISOR_ID") or "").strip()
    return (configured or f"{socket.gethostname()}:{os.getpid()}:portal")[:96]


def _activity(result: Any) -> int:
    if isinstance(result, bool):
        return int(result)
    if isinstance(result, int):
        return max(0, result)
    if isinstance(result, dict):
        return sum(max(0, int(value)) for value in result.values() if isinstance(value, (bool, int)))
    return 0


def _run_workforce_once() -> Any:
    from amodb.apps.workforce import worker_main

    return worker_main.run_once(operation_limit=2)


def _run_platform_commands_once() -> Any:
    from amodb.apps.platform import ops_worker

    return ops_worker.process_pending_batch()


def _run_saas_once() -> Any:
    from amodb.jobs import saas_worker_safe

    batch_size = max(1, min(int(os.getenv("PORTAL_SAAS_JOB_BATCH_SIZE", "5")), 50))
    return saas_worker_safe.run_once(
        batch_size=batch_size,
        worker_id=f"{_identity()}:saas",
    )


def _run_training_workbooks_once() -> Any:
    from amodb.apps.training import workbook_worker

    return workbook_worker.run_once(limit=2)


def _run_training_reports_once() -> Any:
    from amodb.jobs import training_report_jobs

    return training_report_jobs.run_once(limit=3)


def _run_document_indexing_once() -> Any:
    from amodb.apps.doc_control import knowledge_worker

    return knowledge_worker.run_once(limit=2)


def _run_training_plans_once() -> Any:
    from amodb.jobs import training_plan_automation

    return training_plan_automation.run_once()


def _run_training_notifications_once() -> Any:
    from amodb.jobs import training_notification_automation

    return training_notification_automation.run_once()


@dataclass(frozen=True)
class WorkerFamily:
    name: str
    poll_seconds: float
    run_once: Callable[[], Any]
    drain_backlog: bool = True


def _families() -> tuple[WorkerFamily, ...]:
    # Imports intentionally live inside each runner. A broken optional worker
    # family must be reported as DEGRADED without preventing the API (and all
    # other job families) from starting.
    return (
        WorkerFamily(
            "workforce",
            _bounded_float("WORKFORCE_WORKER_POLL_SECONDS", 1.0, 0.25, 30.0),
            _run_workforce_once,
        ),
        WorkerFamily(
            "platform-commands",
            _bounded_float("PLATFORM_OPS_WORKER_SECONDS", 2.0, 0.5, 30.0),
            _run_platform_commands_once,
        ),
        WorkerFamily(
            "saas",
            _bounded_float("SAAS_WORKER_POLL_SECONDS", 1.0, 0.25, 30.0),
            _run_saas_once,
        ),
        WorkerFamily(
            "training-workbooks",
            _bounded_float("TRAINING_WORKBOOK_WORKER_POLL_SECONDS", 2.0, 0.5, 30.0),
            _run_training_workbooks_once,
        ),
        WorkerFamily(
            "training-reports",
            _bounded_float("TRAINING_REPORT_JOB_INTERVAL_SECONDS", 5.0, 1.0, 300.0),
            _run_training_reports_once,
        ),
        WorkerFamily(
            "document-indexing",
            _bounded_float("DOCUMENT_INDEX_WORKER_POLL_SECONDS", 2.0, 0.5, 30.0),
            _run_document_indexing_once,
        ),
        WorkerFamily(
            "training-plans",
            _bounded_float("TRAINING_PLAN_AUTOMATION_INTERVAL_SECONDS", 3600.0, 300.0, 86_400.0),
            _run_training_plans_once,
            drain_backlog=False,
        ),
        WorkerFamily(
            "training-notifications",
            _bounded_float("TRAINING_NOTIFICATION_AUTOMATION_INTERVAL_SECONDS", 3600.0, 300.0, 86_400.0),
            _run_training_notifications_once,
            drain_backlog=False,
        ),
    )


class PortalJobSupervisor:
    def __init__(self, *, mode: str = "embedded", selected_families: set[str] | None = None, concurrency: int = 1) -> None:
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._heartbeat_seconds = _bounded_float("PORTAL_JOB_HEARTBEAT_SECONDS", 15.0, 5.0, 300.0)
        self._mode = mode
        self._selected_families = selected_families
        self._concurrency = max(1, min(int(concurrency), 32))
        max_active_cycles = (
            _bounded_int("PORTAL_EMBEDDED_JOB_MAX_ACTIVE_CYCLES", 2, 1, 16)
            if mode == "embedded"
            else max(1, self._concurrency)
        )
        self._work_slots = threading.BoundedSemaphore(max_active_cycles)
        self._max_active_cycles = max_active_cycles

    def start(self) -> bool:
        if self._mode == "embedded" and not embedded_worker_enabled():
            logger.info("Embedded durable-job workers are disabled")
            return False
        with self._lock:
            if any(thread.is_alive() for thread in self._threads.values()):
                return True
            self._stop.clear()
            self._threads = {}
            for family in _families():
                if self._selected_families and family.name not in self._selected_families:
                    continue
                for slot in range(self._concurrency):
                    thread_name = f"{family.name}:{slot + 1}" if self._concurrency > 1 else family.name
                    thread = threading.Thread(
                        target=self._run_family,
                        args=(family, slot + 1),
                        name=f"portal-job-{thread_name}",
                        daemon=True,
                    )
                    self._threads[thread_name] = thread
                    thread.start()
        logger.info(
            "Started %s durable-job workers (max active cycles=%s): %s",
            self._mode,
            self._max_active_cycles,
            ", ".join(sorted(self._threads)),
        )
        return True

    def _heartbeat(self, family: WorkerFamily, *, status: str, metadata: dict[str, Any], slot: int = 1) -> None:
        if not database_circuit.allow_request():
            return
        # Heartbeats are low-priority. Do not let a burst of heartbeat writes
        # bypass the same concurrency guard as real background work.
        if not self._work_slots.acquire(timeout=0.05):
            return
        db = None
        try:
            db = WriteSessionLocal()
            worker_name = f"{_identity()}:{self._mode}:{family.name}:{slot}"[:128]
            row = db.query(platform_models.PlatformWorkerHeartbeat).filter(
                platform_models.PlatformWorkerHeartbeat.worker_name == worker_name,
            ).first()
            if row is None:
                row = platform_models.PlatformWorkerHeartbeat(
                    worker_name=worker_name,
                    worker_type=f"portal-{self._mode}-job",
                )
                db.add(row)
            row.last_seen_at = platform_models.utcnow()
            row.status = status
            row.metadata_json = {
                "family": family.name,
                "poll_seconds": family.poll_seconds,
                "mode": self._mode,
                "slot": slot,
                "max_active_cycles": self._max_active_cycles,
                **metadata,
            }
            db.commit()
        except Exception as exc:
            if db is not None:
                try:
                    db.rollback()
                except Exception:
                    pass
            if is_database_disconnect(exc):
                database_circuit.mark_failure(exc)
            else:
                logger.debug("Could not record %s worker heartbeat", family.name, exc_info=True)
        finally:
            close_session_safely(db)
            self._work_slots.release()

    def _run_family(self, family: WorkerFamily, slot: int = 1) -> None:
        last_heartbeat = 0.0
        failure_streak = 0
        outage_logged = False
        while not self._stop.is_set():
            started = time.monotonic()
            status = "ONLINE"
            recovered_this_cycle = False
            metadata: dict[str, Any]
            activity = 0
            acquired = False
            try:
                if not database_circuit.allow_request() and not probe_database():
                    raise ConnectionError("DATABASE_UNAVAILABLE")

                # Bound total active queue families inside this process. This is
                # the key guard that keeps parallelism useful instead of turning
                # it into database-pool contention.
                acquired = self._work_slots.acquire(timeout=0.5)
                if not acquired:
                    self._stop.wait(0.05)
                    continue

                result = family.run_once()
                activity = _activity(result)
                metadata = {"last_result": result if isinstance(result, (dict, int, bool)) else str(result)}
                if outage_logged:
                    logger.info("Database recovered; %s worker resumed", family.name)
                    recovered_this_cycle = True
                outage_logged = False
                failure_streak = 0
            except Exception as exc:
                if is_database_disconnect(exc):
                    database_circuit.mark_failure(exc)
                status = "DEGRADED"
                metadata = {"last_error": f"{type(exc).__name__}: {str(exc)[:500]}"}
                failure_streak += 1
                if not outage_logged:
                    logger.warning("%s worker paused while a dependency is unavailable: %s", family.name, exc)
                    outage_logged = True
                elif failure_streak % 10 == 0:
                    logger.info("%s worker remains paused after %s checks", family.name, failure_streak)
            finally:
                if acquired:
                    self._work_slots.release()

            now = time.monotonic()
            if status == "ONLINE" and (recovered_this_cycle or now - last_heartbeat >= self._heartbeat_seconds):
                self._heartbeat(
                    family,
                    status=status,
                    metadata={**metadata, "last_cycle_seconds": round(now - started, 4)},
                    slot=slot,
                )
                last_heartbeat = now

            if status == "DEGRADED":
                base_delay = min(60.0, max(2.0, 2.0 ** min(failure_streak, 6)))
                delay = base_delay + random.uniform(0.0, min(2.0, base_delay * 0.15))
            else:
                delay = 0.05 if activity and family.drain_backlog else family.poll_seconds
            self._stop.wait(delay)

        self._heartbeat(family, status="OFFLINE", metadata={"reason": f"{self._mode} shutdown"}, slot=slot)

    def stop(self) -> None:
        self._stop.set()
        deadline = time.monotonic() + 2.5
        with self._lock:
            threads = list(self._threads.values())
        for thread in threads:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            thread.join(timeout=remaining)
        with self._lock:
            self._threads = {}

    def status(self) -> dict[str, Any]:
        with self._lock:
            threads = dict(self._threads)
        return {
            "enabled": embedded_worker_enabled() if self._mode == "embedded" else True,
            "mode": self._mode,
            "running": any(thread.is_alive() for thread in threads.values()),
            "families": {name: thread.is_alive() for name, thread in threads.items()},
            "max_active_cycles": self._max_active_cycles,
        }


supervisor = PortalJobSupervisor()
