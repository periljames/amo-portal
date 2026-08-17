"""Run the complete Venspera development runtime from one terminal.

The development runtime mirrors the production topology closely enough to keep
interactive API traffic isolated from background work while still making every
queue consumer immediately available.  It starts and supervises:

- portal API (8080)
- Platform Operations gateway (8090)
- durable queue workers
- scheduled automation
- Document Control evidence-pack worker
- Platform Operations command worker
- rostering automation
- Vite frontend (5173)

All child processes receive the same .env.development values.  Process-specific
DB pool overrides are applied before Python imports SQLAlchemy so background
workers cannot consume the user-facing API pool.
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


@dataclass
class Service:
    name: str
    command: list[str]
    cwd: Path
    env_overrides: dict[str, str] = field(default_factory=dict)
    port: int | None = None
    process: subprocess.Popen[str] | None = None
    restart_count: int = 0
    next_restart_at: float = 0.0


_STOP = threading.Event()
_PRINT_LOCK = threading.Lock()


def _print(message: str) -> None:
    with _PRINT_LOCK:
        print(message, flush=True)


def _load_environment(path: Path) -> dict[str, str]:
    if not path.exists():
        raise SystemExit(
            f"Environment file not found: {path}\n"
            "Create .env.development first; secrets stay local and are ignored by Git."
        )

    env = os.environ.copy()
    for key, value in dotenv_values(path).items():
        if value is not None:
            env[str(key)] = str(value)

    # The local env file is authoritative for secrets. These development-only
    # runtime switches are safe to force and prevent localhost auth/worker bugs.
    env["APP_ENV"] = "development"
    env["PORTAL_ENV_FILE"] = str(path)
    env["PORTAL_EMBEDDED_JOB_WORKER"] = "false"
    env["PORTAL_EMBEDDED_SCHEDULED_WORKER"] = "false"
    env["DOCUMENT_EVIDENCE_PACK_EMBEDDED_WORKER"] = "false"
    env["PORTAL_REFRESH_COOKIE_SECURE"] = "false"

    if not env.get("DATABASE_URL") and env.get("DATABASE_WRITE_URL"):
        env["DATABASE_URL"] = env["DATABASE_WRITE_URL"]

    # Keep report generation hot. These are wait times only when queues are
    # empty; active backlogs drain without the idle delay.
    env.setdefault("TRAINING_REPORT_JOB_INTERVAL_SECONDS", "1")
    env.setdefault("DOCUMENT_EVIDENCE_PACK_WORKER_POLL_SECONDS", "0.5")
    env.setdefault("DOCUMENT_INDEX_WORKER_POLL_SECONDS", "1")

    # Runtime counts are consumed by the fail-fast connection budget check.
    env.setdefault("PORTAL_API_PROCESS_COUNT", "1")
    env.setdefault("PORTAL_WORKER_PROCESS_COUNT", "5")
    env.setdefault("PORTAL_SCHEDULED_PROCESS_COUNT", "1")
    env.setdefault("DOCUMENT_EVIDENCE_PACK_PROCESS_COUNT", "1")
    env.setdefault("PLATFORM_OPS_GATEWAY_PROCESS_COUNT", "1")
    env.setdefault("PLATFORM_OPS_WORKER_PROCESS_COUNT", "1")
    env.setdefault("ROSTER_AUTOMATION_PROCESS_COUNT", "1")

    required = ("SECRET_KEY", "REFRESH_TOKEN_PEPPER", "DATABASE_WRITE_URL")
    missing = [name for name in required if not env.get(name, "").strip()]
    if missing:
        raise SystemExit(
            "Missing required development settings in .env.development: "
            + ", ".join(missing)
        )

    return env


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _python_executable() -> str:
    # If this launcher is already running from the project venv, preserve it.
    return sys.executable


def _npm_executable() -> str:
    candidate = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not candidate:
        candidate = shutil.which("npm")
    if not candidate:
        raise SystemExit("npm was not found on PATH; install Node/npm or start with --no-frontend.")
    return candidate


def _service_environment(base: Mapping[str, str], overrides: Mapping[str, str]) -> dict[str, str]:
    env = dict(base)
    env.update({key: str(value) for key, value in overrides.items()})
    return env


def _reader(service: Service, stream) -> None:
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            _print(f"[{service.name:<12}] {line.rstrip()}")
    except Exception:
        return


def _spawn(service: Service, base_env: Mapping[str, str]) -> None:
    env = _service_environment(base_env, service.env_overrides)
    kwargs: dict = {
        "cwd": str(service.cwd),
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    process = subprocess.Popen(service.command, **kwargs)
    service.process = process
    service.restart_count += 1
    service.next_restart_at = 0.0
    _print(f"[runtime     ] started {service.name} (pid={process.pid})")
    if process.stdout is not None:
        threading.Thread(target=_reader, args=(service, process.stdout), daemon=True).start()


def _terminate_tree(service: Service) -> None:
    process = service.process
    if process is None or process.poll() is not None:
        return

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except Exception:
        try:
            process.terminate()
        except Exception:
            pass


def _services(base_env: Mapping[str, str], include_frontend: bool) -> list[Service]:
    python = _python_executable()

    api_pool = base_env.get("PORTAL_DB_POOL_SIZE", base_env.get("DB_POOL_SIZE", "20"))
    api_overflow = base_env.get("PORTAL_DB_MAX_OVERFLOW", base_env.get("DB_MAX_OVERFLOW", "10"))
    api_timeout = base_env.get("PORTAL_DB_POOL_TIMEOUT", base_env.get("DB_POOL_TIMEOUT", "5"))

    services = [
        Service(
            "api",
            [python, "-m", "uvicorn", "amodb.main:app", "--host", "127.0.0.1", "--port", "8080", "--reload"],
            BACKEND,
            {
                "DB_POOL_SIZE": api_pool,
                "DB_MAX_OVERFLOW": api_overflow,
                "DB_POOL_TIMEOUT": api_timeout,
            },
            8080,
        ),
        Service(
            "ops-gateway",
            [python, "-m", "uvicorn", "amodb.platform_ops_main:app", "--host", "127.0.0.1", "--port", "8090", "--reload"],
            BACKEND,
            {
                "DB_POOL_SIZE": base_env.get("PLATFORM_OPS_DB_POOL_SIZE", "3"),
                "DB_MAX_OVERFLOW": base_env.get("PLATFORM_OPS_DB_MAX_OVERFLOW", "2"),
                "DB_POOL_TIMEOUT": base_env.get("PLATFORM_OPS_DB_POOL_TIMEOUT", "3"),
                "DB_READ_ONLY_TRANSACTIONS": "true",
            },
            8090,
        ),
        Service(
            "jobs",
            [python, "-m", "amodb.jobs.portal_worker_main"],
            BACKEND,
        ),
        Service(
            "scheduler",
            [python, "-m", "amodb.jobs.portal_scheduler_main"],
            BACKEND,
        ),
        Service(
            "evidence",
            [python, "-m", "amodb.apps.doc_control.evidence_pack_worker_main", "--poll-seconds", base_env.get("DOCUMENT_EVIDENCE_PACK_WORKER_POLL_SECONDS", "0.5")],
            BACKEND,
        ),
        Service(
            "ops-worker",
            [python, "-m", "amodb.platform_ops_worker_main"],
            BACKEND,
            {
                "DB_POOL_SIZE": base_env.get("PLATFORM_OPS_WORKER_DB_POOL_SIZE", "2"),
                "DB_MAX_OVERFLOW": base_env.get("PLATFORM_OPS_WORKER_DB_MAX_OVERFLOW", "1"),
                "DB_POOL_TIMEOUT": base_env.get("PLATFORM_OPS_WORKER_DB_POOL_TIMEOUT", "3"),
            },
        ),
        Service(
            "rostering",
            [python, "-m", "amodb.jobs.rostering_automation", "--loop"],
            BACKEND,
            {
                "DB_POOL_SIZE": base_env.get("ROSTER_AUTOMATION_DB_POOL_SIZE", "1"),
                "DB_MAX_OVERFLOW": base_env.get("ROSTER_AUTOMATION_DB_MAX_OVERFLOW", "1"),
                "DB_POOL_TIMEOUT": base_env.get("ROSTER_AUTOMATION_DB_POOL_TIMEOUT", "3"),
            },
        ),
    ]

    if include_frontend:
        services.append(
            Service(
                "frontend",
                [_npm_executable(), "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"],
                FRONTEND,
                port=5173,
            )
        )
    return services


def _print_topology(services: list[Service], env_file: Path) -> None:
    _print("[runtime     ] Venspera development runtime")
    _print(f"[runtime     ] env: {env_file}")
    _print("[runtime     ] API jobs are isolated, but all workers stay continuously available.")
    for service in services:
        suffix = f" :{service.port}" if service.port else ""
        _print(f"[runtime     ]   - {service.name}{suffix}")
    _print("[runtime     ] Ctrl+C stops the complete runtime.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the complete Venspera development runtime")
    parser.add_argument(
        "--env-file",
        default=".env.development",
        help="dotenv path relative to the repository root (default: .env.development)",
    )
    parser.add_argument("--no-frontend", action="store_true", help="Do not start Vite")
    args = parser.parse_args()

    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = ROOT / env_file
    env_file = env_file.resolve()

    base_env = _load_environment(env_file)
    services = _services(base_env, include_frontend=not args.no_frontend)

    occupied = [service for service in services if service.port and _port_in_use(service.port)]
    if occupied:
        names = ", ".join(f"{service.name}:{service.port}" for service in occupied)
        raise SystemExit(
            "Required development ports are already in use: " + names + "\n"
            "Stop the old dev runtime before starting the supervised runtime."
        )

    _print_topology(services, env_file)

    def request_stop(_signum=None, _frame=None) -> None:
        _STOP.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    for service in services:
        _spawn(service, base_env)
        time.sleep(0.15)

    try:
        while not _STOP.is_set():
            now = time.monotonic()
            for service in services:
                process = service.process
                if process is None:
                    continue
                exit_code = process.poll()
                if exit_code is None:
                    continue

                if service.next_restart_at <= 0:
                    delay = min(10.0, 0.5 * (2 ** min(service.restart_count - 1, 5)))
                    service.next_restart_at = now + delay
                    _print(
                        f"[runtime     ] {service.name} exited with {exit_code}; "
                        f"restarting in {delay:.1f}s"
                    )
                elif now >= service.next_restart_at:
                    _spawn(service, base_env)
            time.sleep(0.25)
    finally:
        _STOP.set()
        _print("[runtime     ] stopping services...")
        for service in reversed(services):
            _terminate_tree(service)
        _print("[runtime     ] stopped")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
