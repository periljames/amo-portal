from __future__ import annotations

import asyncio
import os
import socket
import time

from amodb.database import WriteSessionLocal, close_session_safely
from amodb.observability import operation_span, record_job_execution

from . import models, platform_command_queue, saas_lease, saas_queue


WORKER_SECONDS = max(1.0, float(os.getenv("PLATFORM_OPS_WORKER_SECONDS", "2") or "2"))
WORKER_BATCH_SIZE = max(1, min(100, int(os.getenv("PLATFORM_OPS_WORKER_BATCH_SIZE", "10") or "10")))
LEASE_SECONDS = max(30, min(3600, int(os.getenv("PLATFORM_OPS_JOB_LEASE_SECONDS", "120") or "120")))


def worker_id() -> str:
    configured = (os.getenv("PLATFORM_OPS_WORKER_ID") or "").strip()
    if configured:
        return configured[:128]
    return f"{socket.gethostname()}:{os.getpid()}:platform-ops"[:128]


def _record_heartbeat(db, identity: str, *, status: str = "ONLINE", metadata: dict | None = None) -> None:
    row = db.query(models.PlatformWorkerHeartbeat).filter(models.PlatformWorkerHeartbeat.worker_name == identity).first()
    if row is None:
        row = models.PlatformWorkerHeartbeat(worker_name=identity, worker_type="platform-ops-command")
        db.add(row)
    row.last_seen_at = models.utcnow()
    row.status = status
    row.metadata_json = metadata or {}
    db.flush()


def _process_one(db, identity: str) -> bool:
    jobs = saas_queue.claim_jobs(
        db,
        worker_id=identity,
        queue_names=("platform",),
        batch_size=1,
        lease_seconds=LEASE_SECONDS,
    )
    if not jobs:
        return False

    job = jobs[0]
    started = time.perf_counter()
    outcome = "FAILED"
    try:
        with operation_span(
            "platform_ops.command.execute",
            job_type=job.job_type,
            queue_name=job.queue_name,
        ):
            with saas_lease.LeaseHeartbeat(
                job,
                worker_id=identity,
                lease_seconds=LEASE_SECONDS,
            ) as heartbeat:
                result = platform_command_queue.process_leased_job(db, job)
                heartbeat.raise_if_lost()
        saas_queue.complete_job(db, job, result, worker_id=identity)
        outcome = "SUCCEEDED"
    except saas_queue.LeaseLostError:
        outcome = "LEASE_LOST"
        db.rollback()
    except PermissionError as exc:
        outcome = "BLOCKED"
        try:
            saas_queue.fail_job(db, job, exc, retryable=False, worker_id=identity)
        except saas_queue.LeaseLostError:
            outcome = "LEASE_LOST"
            db.rollback()
    except Exception as exc:
        outcome = "FAILED"
        try:
            saas_queue.fail_job(
                db,
                job,
                exc,
                retryable=platform_command_queue.queue_job_is_retryable(job),
                worker_id=identity,
            )
        except saas_queue.LeaseLostError:
            outcome = "LEASE_LOST"
            db.rollback()
    finally:
        record_job_execution(
            job_type=job.job_type,
            status=outcome,
            duration_seconds=time.perf_counter() - started,
            retry_count=max(0, int(job.attempt_count or 0) - 1),
        )
    return True


def process_pending_batch() -> int:
    """Reconcile pending command rows and execute a bounded lease-fenced batch."""

    db = WriteSessionLocal()
    identity = worker_id()
    processed = 0
    try:
        _record_heartbeat(db, identity, metadata={"phase": "reconcile"})
        db.commit()
        platform_command_queue.reconcile_pending_jobs(db, limit=max(WORKER_BATCH_SIZE * 4, 20))

        for _ in range(WORKER_BATCH_SIZE):
            if not _process_one(db, identity):
                break
            processed += 1

        _record_heartbeat(
            db,
            identity,
            metadata={"processed_last_batch": processed, "lease_seconds": LEASE_SECONDS},
        )
        db.commit()
        return processed
    except Exception as exc:
        db.rollback()
        try:
            _record_heartbeat(db, identity, status="DEGRADED", metadata={"error": str(exc)[:300]})
            db.commit()
        except Exception:
            db.rollback()
        return processed
    finally:
        close_session_safely(db)


async def durable_command_worker(stop: asyncio.Event) -> None:
    while not stop.is_set():
        await asyncio.to_thread(process_pending_batch)
        try:
            await asyncio.wait_for(stop.wait(), timeout=WORKER_SECONDS)
        except TimeoutError:
            pass
