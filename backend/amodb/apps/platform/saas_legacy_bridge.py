from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from . import models as platform_models
from . import saas_queue
from .command_registry import get_definition


_INSTALLED = False
_ORIGINAL_EXECUTE: Callable[..., None] | None = None


def install_legacy_command_queue() -> None:
    """Route existing platform command endpoints through the durable queue.

    Existing frontend/API contracts continue returning ``PlatformCommandJob``
    records. Only execution changes: requests persist a queue item and return;
    workers later invoke the original allowlisted command implementation.
    """

    global _INSTALLED, _ORIGINAL_EXECUTE
    if _INSTALLED:
        return

    from . import services

    original_create = services.create_command_job
    original_execute = services.execute_command_job
    _ORIGINAL_EXECUTE = original_execute

    def queue_legacy_execution(db: Session, job: platform_models.PlatformCommandJob, *, actor_id: str) -> None:
        if job.status in {"RUNNING", "SUCCEEDED", "CANCELLED"}:
            return
        job.status = "QUEUED"
        services.add_job_event(db, job, "QUEUED", "Command queued for asynchronous worker execution.")
        saas_queue.enqueue_job(
            db,
            job_type="PLATFORM_COMMAND_JOB",
            queue_name="platform",
            tenant_id=job.tenant_id,
            payload={"legacy_job_id": job.id, "actor_id": actor_id},
            idempotency_key=f"legacy:{job.id}:{int(job.attempt_count or 0)}",
            correlation_id=job.id,
            created_by=actor_id,
            max_attempts=max(1, int(job.max_retries or 0) + 1),
            priority=20 if job.risk_level in {"HIGH", "CRITICAL"} else 80,
            commit=False,
        )

    def create_command_job(db: Session, *, payload: dict[str, Any], actor_id: str) -> platform_models.PlatformCommandJob:
        name = str(payload.get("command_name") or "").strip().upper()
        definition = get_definition(name)
        if not definition:
            return original_create(db, payload=payload, actor_id=actor_id)
        tenant_id = payload.get("tenant_id")
        reason = payload.get("reason")
        if definition.requires_tenant_id and not tenant_id:
            raise ValueError("This command requires tenant_id.")
        if definition.requires_reason and not str(reason or "").strip():
            raise ValueError("A reason is required for this command.")

        status = "NEEDS_APPROVAL" if definition.requires_approval and not payload.get("approved") else "PENDING"
        job = platform_models.PlatformCommandJob(
            command_name=definition.command_name,
            risk_level=definition.risk_level,
            status=status,
            tenant_id=tenant_id,
            actor_user_id=actor_id,
            requested_by_user_id=actor_id,
            reason=reason,
            idempotency_key=payload.get("idempotency_key"),
            input_json=payload.get("input") or {},
            dry_run=bool(payload.get("dry_run", False)),
            max_retries=definition.max_retries,
            timeout_seconds=definition.timeout_seconds,
        )
        db.add(job)
        db.flush()
        services.add_job_event(db, job, status, "Command job created.")
        services.audit(
            db,
            actor_user_id=actor_id,
            action="platform.command.created",
            tenant_id=tenant_id,
            entity_type="platform_command_job",
            entity_id=job.id,
            reason=reason,
            details={"command_name": definition.command_name, "risk_level": definition.risk_level, "execution": "durable_queue"},
        )
        if status == "PENDING":
            queue_legacy_execution(db, job, actor_id=actor_id)
        db.commit()
        db.refresh(job)
        return job

    services.create_command_job = create_command_job
    services.execute_command_job = queue_legacy_execution
    _INSTALLED = True


def execute_legacy_command_in_worker(
    db: Session,
    *,
    legacy_job_id: str,
    actor_id: str,
) -> dict[str, Any]:
    if _ORIGINAL_EXECUTE is None:
        install_legacy_command_queue()
    job = db.get(platform_models.PlatformCommandJob, legacy_job_id)
    if not job:
        raise ValueError("Legacy platform command job not found")
    if job.status == "SUCCEEDED":
        return {"legacy_job_id": job.id, "status": job.status, "result": job.output_json or {}}
    assert _ORIGINAL_EXECUTE is not None
    _ORIGINAL_EXECUTE(db, job, actor_id=actor_id)
    db.flush()
    if job.status in {"FAILED", "UNSUPPORTED"}:
        raise RuntimeError(job.error_detail or (job.output_json or {}).get("detail") or f"Legacy command ended with {job.status}")
    return {"legacy_job_id": job.id, "status": job.status, "result": job.output_json or {}}
