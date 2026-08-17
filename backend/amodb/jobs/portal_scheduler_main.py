"""Dedicated scheduled-worker process.

Production runs this separately from Uvicorn and queue workers. Kubernetes
keeps one active replica; database-backed job receipts make every scheduled
task idempotent across restarts.
"""
from __future__ import annotations

import logging
import os
import signal
import time

from amodb.apps.quality.planner_schedule_router import start_quality_planner_scheduler, stop_quality_planner_scheduler
from amodb.apps.reliability import advanced_scheduler as reliability_scheduler
from amodb.jobs.portal_job_supervisor import PortalJobSupervisor


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    stopping = False

    def stop(_signum=None, _frame=None) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    supervisor = PortalJobSupervisor(mode="scheduled", selected_families={"training-plans"}, concurrency=1)
    reliability_scheduler.start_reliability_scheduler()
    start_quality_planner_scheduler()
    supervisor.start()
    try:
        while not stopping:
            if not supervisor.status()["running"]:
                raise RuntimeError("Scheduled worker stopped unexpectedly")
            time.sleep(1)
    finally:
        supervisor.stop()
        stop_quality_planner_scheduler()
        reliability_scheduler.stop_reliability_scheduler()


if __name__ == "__main__":
    main()
