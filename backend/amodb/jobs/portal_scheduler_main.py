"""Dedicated scheduled-worker process.

Scheduled automation is isolated from Uvicorn and durable queue workers so a
slow maintenance task cannot consume the user-facing API connection pool.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import time
from pathlib import Path


def _load_env_file(path_value: str | None) -> None:
    if not path_value:
        return
    from dotenv import load_dotenv

    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Environment file not found: {path}")
    load_dotenv(path, override=False)


def _configure_scheduled_db_pool() -> None:
    if (os.getenv("DB_EXTERNAL_POOLER") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return
    os.environ["DB_POOL_SIZE"] = os.getenv("PORTAL_SCHEDULED_DB_POOL_SIZE", "2")
    os.environ["DB_MAX_OVERFLOW"] = os.getenv("PORTAL_SCHEDULED_DB_MAX_OVERFLOW", "1")
    os.environ["DB_POOL_TIMEOUT"] = os.getenv("PORTAL_SCHEDULED_DB_POOL_TIMEOUT", "3")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AMO Portal scheduled automation")
    parser.add_argument(
        "--env-file",
        default=os.getenv("PORTAL_ENV_FILE"),
        help="Optional dotenv file loaded before database modules are imported",
    )
    args = parser.parse_args()

    _load_env_file(args.env_file)
    _configure_scheduled_db_pool()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    # Import after pool isolation: these modules create/use SQLAlchemy sessions.
    from amodb.apps.quality.planner_schedule_router import start_quality_planner_scheduler, stop_quality_planner_scheduler
    from amodb.apps.reliability import advanced_scheduler as reliability_scheduler
    from amodb.jobs.portal_job_supervisor import PortalJobSupervisor

    stopping = False

    def stop(_signum=None, _frame=None) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    supervisor = PortalJobSupervisor(
        mode="scheduled",
        selected_families={"training-plans", "training-notifications"},
        concurrency=1,
    )
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
