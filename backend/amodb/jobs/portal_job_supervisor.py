"""Embedded durable-job runtime for the tenant API process.

Small and single-process deployments commonly start only ``uvicorn amodb.main``.
Historically that left several valid database queues without a consumer.  This
supervisor runs the existing lease/row-lock protected workers in independent
daemon threads.  Dedicated worker deployments can disable it with
``PORTAL_EMBEDDED_JOB_WORKER=0``; running both modes during a rollout is safe.
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
    app_env = (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()
    return _env_bool("PORTAL_EMBEDDED_JOB_WORKER", app_env not in {"test", "testing", "ci"})


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
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
    )


class PortalJobSupervisor:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._database_outage_reported = False
        self._heartbeat_seconds = _bounded_float("PORTAL_JOB_HEARTBEAT_SECONDS", 15.0, 5.0, 300.0)

    def _report_database_outage(self) -> None:
        with self._lock:
            if self._database_outage_reported:
                return
            self._database_outage_reported = True
        logger.warning("Database unavailable; embedded workers paused until readiness recovers")

    def _report_database_recovery(self) -> None:
        with self._lock:
            if not self._database_outage_reported:
                return
            self._database_outage_reported = False
        logger.info("Database connectivity recovered; embedded job processing resumed")

    def start(self) -> bool:
        if not embedded_worker_enabled():
            logger.info("Embedded durable-job workers are disabled")
            return False
        with self._lock:
            if any(thread.is_alive() for thread in self._threads.values()):
                return True
            self._stop.clear()
            self._threads = {}
            for family in _families():
                thread = threading.Thread(
                    target=self._run_family,
                    args=(family,),
                    name=f"portal-job-{family.name}",
                    daemon=True,
                )
                self._threads[family.name] = thread
                thread.start()
        logger.info("Started embedded durable-job workers: %s", ", ".join(sorted(self._threads)))
        return True

    def _heartbeat(self, family: WorkerFamily, *, status: str, metadata: dict[str, Any]) -> None:
        if not database_circuit.allow_request():
            return
        db = WriteSessionLocal()
        try:
            worker_name = f"{_identity()}:{family.name}"[:128]
            row = db.query(platform_models.PlatformWorkerHeartbeat).filter(
                platform_models.PlatformWorkerHeartbeat.worker_name == worker_name,
            ).first()
            if row is None:
                row = platform_models.PlatformWorkerHeartbeat(
                    worker_name=worker_name,
                    worker_type="portal-embedded-job",
                )
                db.add(row)
            row.last_seen_at = platform_models.utcnow()
            row.status = status
            row.metadata_json = {
                "family": family.name,
                "poll_seconds": family.poll_seconds,
                "mode": "embedded",
                **metadata,
            }
            db.commit()
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            if is_database_disconnect(exc):
                database_circuit.mark_failure(exc)
                self._report_database_outage()
            else:
                logger.debug("Could not record %s worker heartbeat", family.name, exc_info=True)
        finally:
            close_session_safely(db)

    def _run_family(self, family: WorkerFamily) -> None:
        last_heartbeat = 0.0
        while not self._stop.is_set():
            started = time.monotonic()
            status = "ONLINE"
            metadata: dict[str, Any]
            activity = 0
            was_offline = not database_circuit.allow_request()
            if not probe_database():
                # All worker families share the same single-flight probe and
                # circuit.  During an outage they wait instead of multiplying
                # connection attempts and traceback noise.
                retry_after = database_circuit.retry_after_seconds()
                self._report_database_outage()
                self._stop.wait(retry_after + random.uniform(0.0, min(1.0, retry_after * 0.15)))
                continue
            if was_offline:
                self._report_database_recovery()
            try:
                result = family.run_once()
                activity = _activity(result)
                metadata = {"last_result": result if isinstance(result, (dict, int, bool)) else str(result)}
            except Exception as exc:
                if is_database_disconnect(exc):
                    database_circuit.mark_failure(exc)
                    self._report_database_outage()
                    retry_after = database_circuit.retry_after_seconds()
                    self._stop.wait(retry_after + random.uniform(0.0, min(1.0, retry_after * 0.15)))
                    continue
                status = "DEGRADED"
                metadata = {"last_error": f"{type(exc).__name__}: {str(exc)[:500]}"}
                logger.exception("Embedded %s worker cycle failed", family.name)

            now = time.monotonic()
            if status != "ONLINE" or now - last_heartbeat >= self._heartbeat_seconds:
                self._heartbeat(
                    family,
                    status=status,
                    metadata={**metadata, "last_cycle_seconds": round(now - started, 4)},
                )
                last_heartbeat = now

            # Drain backlogs without an artificial pause, but yield briefly so a
            # hot queue cannot monopolise CPU or the database pool.
            delay = 0.05 if activity and family.drain_backlog else family.poll_seconds
            self._stop.wait(delay)

        self._heartbeat(family, status="OFFLINE", metadata={"reason": "API shutdown"})

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
            "enabled": embedded_worker_enabled(),
            "running": any(thread.is_alive() for thread in threads.values()),
            "families": {name: thread.is_alive() for name, thread in threads.items()},
            "database": database_circuit.snapshot(),
        }


supervisor = PortalJobSupervisor()


def start_portal_job_supervisor() -> bool:
    return supervisor.start()


def stop_portal_job_supervisor() -> None:
    supervisor.stop()


def portal_job_supervisor_status() -> dict[str, Any]:
    return supervisor.status()
