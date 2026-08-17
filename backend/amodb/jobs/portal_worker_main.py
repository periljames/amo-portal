"""Production entry point for independently scalable durable-job workers.

Examples::

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

from .portal_job_supervisor import PortalJobSupervisor, _families


def _available() -> set[str]:
    return {family.name for family in _families()}


def _child_main(selected: set[str]) -> None:
    """Run one isolated worker process with one thread per selected family."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
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
        "--families",
        default=os.getenv("PORTAL_WORKER_FAMILIES", "all"),
        help="Comma-separated family names, or 'all'",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=int(os.getenv("PORTAL_WORKER_CONCURRENCY", "1")),
        help="Worker processes per selected family (overridable with PORTAL_WORKER_PROCESS_POOLS)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    available = _available()
    requested = {value.strip() for value in args.families.split(",") if value.strip()}
    selected = available if not requested or "all" in requested else requested
    unknown = selected - available
    if unknown:
        parser.error(f"Unknown worker families: {', '.join(sorted(unknown))}. Available: {', '.join(sorted(available))}")

    context = multiprocessing.get_context("spawn")
    processes: list[multiprocessing.Process] = []
    for family, size in _pool_sizes(selected, max(1, min(args.concurrency, 64))).items():
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
