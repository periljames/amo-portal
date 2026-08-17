"""Independently scalable durable-job worker processes.

The HTTP API must not share its SQLAlchemy pool with background queues.  This
entry point runs each selected worker family in a spawned process with a small,
bounded worker-specific pool.

Examples::

    python -m amodb.jobs.portal_worker_main --env-file ..\.env.development
    python -m amodb.jobs.portal_worker_main --families workforce --concurrency 4
    python -m amodb.jobs.portal_worker_main --families training-workbooks,training-reports
"""
from __future__ import annotations

import argparse
import logging
import multiprocessing
import os
import signal
import time
from pathlib import Path


DEFAULT_FAMILIES = "workforce,saas,training-workbooks,training-reports,document-indexing"


def _load_env_file(path_value: str | None) -> None:
    if not path_value:
        return
    from dotenv import load_dotenv

    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Environment file not found: {path}")
    load_dotenv(path, override=False)


def _configure_worker_db_pool() -> None:
    """Apply a worker-only local pool before database.py creates its engines."""

    if (os.getenv("DB_EXTERNAL_POOLER") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return
    os.environ["DB_POOL_SIZE"] = os.getenv("PORTAL_WORKER_DB_POOL_SIZE", "2")
    os.environ["DB_MAX_OVERFLOW"] = os.getenv("PORTAL_WORKER_DB_MAX_OVERFLOW", "1")
    os.environ["DB_POOL_TIMEOUT"] = os.getenv("PORTAL_WORKER_DB_POOL_TIMEOUT", "3")


def _available() -> set[str]:
    # Import lazily so --env-file is processed before database.py is imported.
    from .portal_job_supervisor import _families

    return {family.name for family in _families()}


def _child_main(selected: set[str]) -> None:
    """Run one isolated worker process with one thread per selected family."""

    _configure_worker_db_pool()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    # database.py is imported by the supervisor, so this must stay below the
    # worker-pool override above.
    from .portal_job_supervisor import PortalJobSupervisor

    supervisor = PortalJobSupervisor(mode="dedicated", selected_families=selected, concurrency=1)
    supervisor.start()
    stopping = False

    def stop(_signum=None, _frame=None) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while not stopping:
            if not supervisor.status()["running"]:
                raise RuntimeError("Selected worker stopped unexpectedly")
            time.sleep(1)
    finally:
        supervisor.stop()


def _pool_sizes(selected: set[str], default_size: int) -> dict[str, int]:
    """Return per-family process counts from ``family=count`` configuration."""

    sizes = {family: default_size for family in selected}
    raw = (os.getenv("PORTAL_WORKER_PROCESS_POOLS") or "").strip()
    for entry in raw.split(","):
        if not entry.strip() or "=" not in entry:
            continue
        family, value = (part.strip() for part in entry.split("=", 1))
        if family not in selected:
            continue
        try:
            sizes[family] = max(1, min(int(value), 64))
        except ValueError:
            raise ValueError(f"Invalid process count for {family}: {value}") from None
    return sizes


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AMO Portal durable worker families")
    parser.add_argument(
        "--env-file",
        default=os.getenv("PORTAL_ENV_FILE"),
        help="Optional dotenv file loaded before database modules are imported",
    )
    parser.add_argument(
        "--families",
        default=None,
        help="Comma-separated family names, or 'all'",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="Worker processes per selected family (overridable with PORTAL_WORKER_PROCESS_POOLS)",
    )
    args = parser.parse_args()

    _load_env_file(args.env_file)
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    families_value = args.families or os.getenv("PORTAL_WORKER_FAMILIES", DEFAULT_FAMILIES)
    concurrency = args.concurrency
    if concurrency is None:
        concurrency = int(os.getenv("PORTAL_WORKER_CONCURRENCY", "1"))
    concurrency = max(1, min(concurrency, 64))

    available = _available()
    requested = {value.strip() for value in families_value.split(",") if value.strip()}
    selected = available if not requested or "all" in requested else requested
    unknown = selected - available
    if unknown:
        parser.error(f"Unknown worker families: {', '.join(sorted(unknown))}. Available: {', '.join(sorted(available))}")

    context = multiprocessing.get_context("spawn")
    processes: list[multiprocessing.Process] = []
    for family, size in _pool_sizes(selected, concurrency).items():
        for slot in range(size):
            process = context.Process(
                target=_child_main,
                args=({family},),
                name=f"portal-{family}-{slot + 1}",
            )
            process.start()
            processes.append(process)

    stopping = False

    def stop(_signum=None, _frame=None) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while not stopping:
            failed = [process for process in processes if process.exitcode not in (None, 0)]
            if failed:
                names = ", ".join(process.name for process in failed)
                raise RuntimeError(f"Worker process failed: {names}")
            time.sleep(1)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
        for process in processes:
            process.join(timeout=10)


if __name__ == "__main__":
    main()
