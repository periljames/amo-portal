from __future__ import annotations

import threading
from dataclasses import dataclass

from amodb.database import WriteSessionLocal, close_session_safely

from . import saas_models as models
from . import saas_queue


@dataclass(frozen=True)
class LeaseIdentity:
    job_id: str
    worker_id: str
    lease_token: str


class LeaseHeartbeat:
    """Renew a job lease independently from the worker's transaction/session."""

    def __init__(
        self,
        job: models.SaaSJob,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        if not job.lease_token:
            raise saas_queue.LeaseLostError("Cannot start heartbeat without a lease token")
        self.identity = LeaseIdentity(
            job_id=str(job.id),
            worker_id=worker_id[:128],
            lease_token=str(job.lease_token),
        )
        self.lease_seconds = max(30, min(int(lease_seconds), 3600))
        self.interval_seconds = max(5.0, min(float(self.lease_seconds) / 3.0, 30.0))
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None

    def __enter__(self) -> "LeaseHeartbeat":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        def _run() -> None:
            while not self._stop.wait(self.interval_seconds):
                db = WriteSessionLocal()
                try:
                    job = db.get(models.SaaSJob, self.identity.job_id)
                    if job is None:
                        raise saas_queue.LeaseLostError("Job disappeared during heartbeat")
                    # Use the original fence even if this session observes a newer claim.
                    job.locked_by = self.identity.worker_id
                    job.lease_token = self.identity.lease_token
                    saas_queue.heartbeat_job(
                        db,
                        job,
                        worker_id=self.identity.worker_id,
                        lease_seconds=self.lease_seconds,
                    )
                except Exception as exc:
                    self.last_error = str(exc)
                    self._lost.set()
                    return
                finally:
                    close_session_safely(db)

        self._thread = threading.Thread(
            target=_run,
            name=f"saas-lease-{self.identity.job_id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(1.0, self.interval_seconds + 1.0))
        self._thread = None

    def raise_if_lost(self) -> None:
        if self._lost.is_set():
            raise saas_queue.LeaseLostError(
                self.last_error or "Job lease was lost during processing"
            )
