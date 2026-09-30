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
    from amodb.jobs import platform_monitor

    def _interval(name: str, default: float) -> float:
        try:
            return max(5.0, float(os.getenv(name, str(default))))
        except (TypeError, ValueError):
            return default

    infra_healthy_interval = _interval("PLATFORM_INFRA_HEALTHY_INTERVAL_SECONDS", 300.0)
    infra_degraded_interval = _interval("PLATFORM_INFRA_DEGRADED_INTERVAL_SECONDS", 60.0)
    infra_critical_interval = _interval("PLATFORM_INFRA_CRITICAL_INTERVAL_SECONDS", 30.0)
    infra_unknown_interval = _interval("PLATFORM_INFRA_UNKNOWN_INTERVAL_SECONDS", 120.0)
    health_interval = _interval("PLATFORM_HEALTH_PROBE_INTERVAL_SECONDS", 120.0)

    def _next_infrastructure_delay(result: dict | None) -> float:
        status = str((result or {}).get("status") or "UNKNOWN").upper()
        if status == "CRITICAL":
            return infra_critical_interval
        if status == "DEGRADED":
            return infra_degraded_interval
        if status == "OK":
            return infra_healthy_interval
        return infra_unknown_interval
    health_probe_network = (os.getenv("PLATFORM_HEALTH_PROBE_INCLUDE_NETWORK", "false") or "").strip().lower() in {"1", "true", "yes", "on"}
    # Network diagnostics use an adaptive low-load scheduler. A small sentinel
    # chooses the next interval, while bounded full throughput tests run only
    # for bootstrap, confirmed anomalies, or a slow periodic refresh.
    net_probe_enabled = (os.getenv("PLATFORM_NET_PROBE_ENABLED", "true") or "").strip().lower() in {"1", "true", "yes", "on"}
    net_retention_days = int(os.getenv("PLATFORM_NET_RETENTION_DAYS", "30"))
    net_probe_fallback = _interval("PLATFORM_NET_RECOVERY_INTERVAL_SECONDS", 900.0)

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

    # Prime the platform monitor immediately so the superadmin Operations and
    # System Infrastructure views have data on first load.
    initial_infrastructure = platform_monitor.capture_infrastructure_once()
    platform_monitor.capture_health_once(include_network=health_probe_network)
    next_infra = time.monotonic() + _next_infrastructure_delay(initial_infrastructure)
    next_health = time.monotonic() + health_interval
    next_net = time.monotonic() + (30.0 if net_probe_enabled else float("inf"))

    try:
        while not stopping:
            if not supervisor.status()["running"]:
                raise RuntimeError("Scheduled worker stopped unexpectedly")
            now = time.monotonic()
            if now >= next_infra:
                infrastructure = platform_monitor.capture_infrastructure_once()
                next_infra = now + _next_infrastructure_delay(infrastructure)
            if now >= next_health:
                platform_monitor.capture_health_once(include_network=health_probe_network)
                next_health = now + health_interval
            if net_probe_enabled and now >= next_net:
                probe = platform_monitor.run_adaptive_network_probe_once(prune_days=net_retention_days)
                delay = float((probe or {}).get("next_delay_seconds") or net_probe_fallback)
                next_net = now + max(30.0, delay)
            time.sleep(1)
    finally:
        supervisor.stop()
        stop_quality_planner_scheduler()
        reliability_scheduler.stop_reliability_scheduler()


if __name__ == "__main__":
    main()
