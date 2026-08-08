from __future__ import annotations

import asyncio
import os

from amodb.database import WriteSessionLocal, close_session_safely
from amodb.observability import operation_span

from . import models, services

WORKER_SECONDS = max(1.0, float(os.getenv("PLATFORM_OPS_WORKER_SECONDS", "2") or "2"))
WORKER_BATCH_SIZE = max(1, min(100, int(os.getenv("PLATFORM_OPS_WORKER_BATCH_SIZE", "10") or "10")))


def process_pending_batch() -> int:
    db = WriteSessionLocal()
    completed = 0
    try:
        rows = (
            db.query(models.PlatformCommandJob)
            .filter(models.PlatformCommandJob.status == "PENDING")
            .order_by(models.PlatformCommandJob.created_at.asc())
            .limit(WORKER_BATCH_SIZE)
            .with_for_update(skip_locked=True)
            .all()
        )
        for row in rows:
            actor = str(row.actor_user_id or row.requested_by_user_id or "")
            with operation_span("platform_ops.command.execute", command=row.command_name, tenant_id=row.tenant_id, job_id=row.id):
                services.execute_command_job(db, row, actor_id=actor)
            completed += 1
        db.commit()
        return completed
    except Exception:
        db.rollback()
        return completed
    finally:
        close_session_safely(db)


async def durable_command_worker(stop: asyncio.Event) -> None:
    while not stop.is_set():
        await asyncio.to_thread(process_pending_batch)
        try:
            await asyncio.wait_for(stop.wait(), timeout=WORKER_SECONDS)
        except TimeoutError:
            pass
