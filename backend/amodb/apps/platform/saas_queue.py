from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import saas_models as models


TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "DEAD", "CANCELLED"}
CLAIMABLE_STATUSES = {"PENDING", "RETRY"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _scope(tenant_id: str | None) -> str:
    return tenant_id or "__platform__"


def add_event(
    db: Session,
    job: models.SaaSJob,
    status: str,
    message: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    db.add(
        models.SaaSJobEvent(
            job_id=job.id,
            status=status,
            message=message,
            data_json=data or {},
        )
    )


def enqueue_job(
    db: Session,
    *,
    job_type: str,
    payload: dict[str, Any] | None,
    idempotency_key: str,
    tenant_id: str | None = None,
    queue_name: str = "default",
    priority: int = 100,
    max_attempts: int = 5,
    available_at: datetime | None = None,
    correlation_id: str | None = None,
    created_by: str | None = None,
    commit: bool = True,
) -> models.SaaSJob:
    normalized_type = job_type.strip().upper()
    normalized_key = idempotency_key.strip()
    if not normalized_type:
        raise ValueError("job_type is required")
    if not normalized_key:
        raise ValueError("idempotency_key is required")

    existing = (
        db.query(models.SaaSJob)
        .filter(
            models.SaaSJob.job_type == normalized_type,
            models.SaaSJob.tenant_scope == _scope(tenant_id),
            models.SaaSJob.idempotency_key == normalized_key,
        )
        .first()
    )
    if existing:
        return existing

    job = models.SaaSJob(
        queue_name=(queue_name or "default").strip().lower(),
        job_type=normalized_type,
        tenant_id=tenant_id,
        tenant_scope=_scope(tenant_id),
        status="PENDING",
        priority=max(0, min(int(priority), 1000)),
        payload_json=payload or {},
        idempotency_key=normalized_key,
        correlation_id=correlation_id,
        max_attempts=max(1, min(int(max_attempts), 25)),
        available_at=available_at or utcnow(),
        created_by=created_by,
    )
    db.add(job)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(models.SaaSJob)
            .filter(
                models.SaaSJob.job_type == normalized_type,
                models.SaaSJob.tenant_scope == _scope(tenant_id),
                models.SaaSJob.idempotency_key == normalized_key,
            )
            .first()
        )
        if existing:
            return existing
        raise
    add_event(db, job, "PENDING", "Job accepted by the durable queue.")
    if commit:
        db.commit()
        db.refresh(job)
    return job


def release_expired_leases(db: Session, *, now: datetime | None = None) -> int:
    now = now or utcnow()
    rows = (
        db.query(models.SaaSJob)
        .filter(
            models.SaaSJob.status == "RUNNING",
            models.SaaSJob.lease_expires_at.isnot(None),
            models.SaaSJob.lease_expires_at <= now,
        )
        .all()
    )
    for job in rows:
        if job.attempt_count >= job.max_attempts:
            job.status = "DEAD"
            job.finished_at = now
            add_event(db, job, "DEAD", "Worker lease expired and retry allowance was exhausted.")
        else:
            job.status = "RETRY"
            job.available_at = now + _retry_delay(job.attempt_count)
            job.locked_at = None
            job.locked_by = None
            job.lease_expires_at = None
            add_event(db, job, "RETRY", "Expired worker lease released for retry.")
    if rows:
        db.flush()
    return len(rows)


def claim_jobs(
    db: Session,
    *,
    worker_id: str,
    queue_names: Iterable[str] = ("default",),
    batch_size: int = 10,
    lease_seconds: int = 60,
    now: datetime | None = None,
) -> list[models.SaaSJob]:
    """Atomically lease jobs.

    PostgreSQL executes this query with ``FOR UPDATE SKIP LOCKED`` so many
    workers can claim from the same queue without serialising unrelated jobs.
    """

    now = now or utcnow()
    release_expired_leases(db, now=now)
    normalized_queues = [name.strip().lower() for name in queue_names if name and name.strip()]
    if not normalized_queues:
        normalized_queues = ["default"]

    query = (
        db.query(models.SaaSJob)
        .filter(
            models.SaaSJob.queue_name.in_(normalized_queues),
            models.SaaSJob.status.in_(CLAIMABLE_STATUSES),
            models.SaaSJob.available_at <= now,
            or_(models.SaaSJob.lease_expires_at.is_(None), models.SaaSJob.lease_expires_at <= now),
        )
        .order_by(models.SaaSJob.priority.asc(), models.SaaSJob.available_at.asc(), models.SaaSJob.created_at.asc())
        .limit(max(1, min(int(batch_size), 100)))
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    else:
        query = query.with_for_update()

    jobs = query.all()
    lease_until = now + timedelta(seconds=max(10, min(int(lease_seconds), 3600)))
    for job in jobs:
        job.status = "RUNNING"
        job.locked_at = now
        job.locked_by = worker_id[:128]
        job.lease_expires_at = lease_until
        job.attempt_count = int(job.attempt_count or 0) + 1
        add_event(db, job, "RUNNING", f"Claimed by worker {worker_id}.")
    db.commit()
    for job in jobs:
        db.refresh(job)
    return jobs


def heartbeat_job(
    db: Session,
    job: models.SaaSJob,
    *,
    worker_id: str,
    lease_seconds: int = 60,
) -> None:
    if job.status != "RUNNING" or job.locked_by != worker_id:
        raise ValueError("Job is not leased by this worker")
    job.lease_expires_at = utcnow() + timedelta(seconds=max(10, min(int(lease_seconds), 3600)))
    db.commit()


def complete_job(db: Session, job: models.SaaSJob, result: dict[str, Any] | None = None) -> None:
    job.status = "SUCCEEDED"
    job.result_json = result or {}
    job.last_error = None
    job.finished_at = utcnow()
    job.locked_at = None
    job.locked_by = None
    job.lease_expires_at = None
    add_event(db, job, "SUCCEEDED", "Job completed.", result)
    db.commit()


def _retry_delay(attempt_count: int) -> timedelta:
    # 5s, 15s, 45s, 135s ... capped at 30 minutes.
    seconds = min(1800, 5 * (3 ** max(0, int(attempt_count) - 1)))
    return timedelta(seconds=seconds)


def fail_job(
    db: Session,
    job: models.SaaSJob,
    error: BaseException | str,
    *,
    retryable: bool = True,
) -> None:
    message = str(error)[:4000]
    now = utcnow()
    job.last_error = message
    job.locked_at = None
    job.locked_by = None
    job.lease_expires_at = None
    if retryable and int(job.attempt_count or 0) < int(job.max_attempts or 1):
        job.status = "RETRY"
        job.available_at = now + _retry_delay(job.attempt_count)
        add_event(db, job, "RETRY", message, {"available_at": job.available_at.isoformat()})
    else:
        job.status = "DEAD" if retryable else "FAILED"
        job.finished_at = now
        add_event(db, job, job.status, message)
    db.commit()


def retry_job(db: Session, job: models.SaaSJob, *, actor_user_id: str | None = None) -> models.SaaSJob:
    if job.status not in TERMINAL_STATUSES | {"RETRY"}:
        raise ValueError("Only failed, dead, cancelled or retrying jobs can be retried")
    job.status = "PENDING"
    job.available_at = utcnow()
    job.finished_at = None
    job.last_error = None
    job.locked_at = None
    job.locked_by = None
    job.lease_expires_at = None
    if actor_user_id:
        job.created_by = actor_user_id
    add_event(db, job, "PENDING", "Job manually requeued.")
    db.commit()
    db.refresh(job)
    return job


def cancel_job(db: Session, job: models.SaaSJob, *, reason: str) -> models.SaaSJob:
    if job.status == "RUNNING":
        raise ValueError("A running job cannot be cancelled until its lease expires")
    if job.status in TERMINAL_STATUSES:
        return job
    job.status = "CANCELLED"
    job.finished_at = utcnow()
    job.last_error = reason[:4000]
    add_event(db, job, "CANCELLED", reason)
    db.commit()
    db.refresh(job)
    return job


def queue_summary(db: Session) -> dict[str, Any]:
    rows = db.query(models.SaaSJob.status, models.SaaSJob.queue_name).all()
    counts: dict[str, int] = {}
    queues: dict[str, int] = {}
    for status, queue_name in rows:
        counts[str(status)] = counts.get(str(status), 0) + 1
        if str(status) not in TERMINAL_STATUSES:
            queues[str(queue_name)] = queues.get(str(queue_name), 0) + 1
    oldest = (
        db.query(models.SaaSJob)
        .filter(models.SaaSJob.status.in_(CLAIMABLE_STATUSES))
        .order_by(models.SaaSJob.created_at.asc())
        .first()
    )
    now = utcnow()
    oldest_age = None
    if oldest and oldest.created_at:
        created = oldest.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        oldest_age = max(0, int((now - created).total_seconds()))
    return {
        "counts": counts,
        "queue_depth": sum(queues.values()),
        "queues": queues,
        "oldest_pending_age_seconds": oldest_age,
    }
