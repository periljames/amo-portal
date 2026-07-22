from __future__ import annotations

import argparse
import json
import os
import socket
import time

from amodb.apps.platform import saas_lease, saas_legacy_bridge, saas_queue
from amodb.database import WriteSessionLocal, close_session_safely


def worker_id() -> str:
    return os.getenv("PLATFORM_COMMAND_WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}:platform"


def run_once(*, batch_size: int = 1) -> dict:
    db = WriteSessionLocal()
    processed = 0
    failed = 0
    lease_lost = 0
    current_worker = worker_id()
    lease_seconds = int(os.getenv("PLATFORM_COMMAND_LEASE_SECONDS", "180"))
    try:
        jobs = saas_queue.claim_jobs(
            db,
            worker_id=current_worker,
            queue_names=("platform",),
            batch_size=batch_size,
            lease_seconds=lease_seconds,
        )
        for job in jobs:
            try:
                payload = job.payload_json or {}
                with saas_lease.LeaseHeartbeat(
                    job,
                    worker_id=current_worker,
                    lease_seconds=lease_seconds,
                ) as heartbeat:
                    result = saas_legacy_bridge.execute_legacy_command_in_worker(
                        db,
                        legacy_job_id=str(payload.get("legacy_job_id") or ""),
                        actor_id=str(payload.get("actor_id") or job.created_by or ""),
                    )
                    heartbeat.raise_if_lost()
                saas_queue.complete_job(db, job, result, worker_id=current_worker)
                processed += 1
            except saas_queue.LeaseLostError:
                db.rollback()
                lease_lost += 1
            except Exception as exc:
                try:
                    saas_queue.fail_job(
                        db,
                        job,
                        exc,
                        retryable=True,
                        worker_id=current_worker,
                    )
                except saas_queue.LeaseLostError:
                    db.rollback()
                    lease_lost += 1
                else:
                    failed += 1
        return {
            "worker_id": current_worker,
            "claimed": len(jobs),
            "processed": processed,
            "failed": failed,
            "lease_lost": lease_lost,
        }
    finally:
        close_session_safely(db)


def run_forever(*, batch_size: int = 1, poll_seconds: float = 1.0) -> None:
    while True:
        result = run_once(batch_size=batch_size)
        if result["claimed"] == 0:
            time.sleep(max(0.25, min(poll_seconds, 30.0)))


def main() -> None:
    parser = argparse.ArgumentParser(description="AMO Portal lease-fenced platform command worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("PLATFORM_COMMAND_BATCH_SIZE", "1")))
    parser.add_argument("--poll-seconds", type=float, default=float(os.getenv("PLATFORM_COMMAND_POLL_SECONDS", "1")))
    args = parser.parse_args()
    if args.once:
        print(json.dumps(run_once(batch_size=args.batch_size), default=str))
    else:
        run_forever(batch_size=args.batch_size, poll_seconds=args.poll_seconds)


if __name__ == "__main__":
    main()
