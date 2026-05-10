from __future__ import annotations

import os
import socket
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import metrics


def _timed(label: str, fn) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        value = fn()
        return {"name": label, "ok": True, "duration_ms": round((time.perf_counter() - started) * 1000, 2), "detail": value}
    except Exception as exc:
        return {"name": label, "ok": False, "duration_ms": round((time.perf_counter() - started) * 1000, 2), "error": exc.__class__.__name__, "detail": str(exc)[:500]}


def run_health_probe(db: Session, *, include_network: bool = True) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    checks.append(_timed("database_select_1", lambda: db.execute(text("SELECT 1")).scalar()))

    def storage_test():
        base = Path(os.getenv("PLATFORM_DIAGNOSTICS_TMP_DIR") or tempfile.gettempdir())
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"amodb-platform-probe-{int(time.time() * 1000)}.tmp"
        payload = b"amodb-platform-probe"
        path.write_bytes(payload)
        read_back = path.read_bytes()
        path.unlink(missing_ok=True)
        return {"bytes": len(read_back), "path": str(base)}

    checks.append(_timed("storage_write_read_delete", storage_test))

    if include_network:
        url = os.getenv("PLATFORM_INTERNET_PROBE_URL", "https://example.com")
        checks.append(_timed("internet_head", lambda: urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=3).status))

    smtp_host = os.getenv("SMTP_HOST") or os.getenv("PLATFORM_SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT") or os.getenv("PLATFORM_SMTP_PORT") or "25")
    if smtp_host:
        def smtp_tcp():
            with socket.create_connection((smtp_host, smtp_port), timeout=3):
                return {"host": smtp_host, "port": smtp_port, "reachable": True}
        checks.append(_timed("smtp_tcp", smtp_tcp))
    else:
        checks.append({"name": "smtp_tcp", "ok": None, "duration_ms": 0, "detail": "SMTP not configured"})

    throughput = metrics.live_summary()
    checks.append({"name": "route_metrics_live", "ok": True, "duration_ms": 0, "detail": throughput})
    failed = [row for row in checks if row.get("ok") is False]
    status = "HEALTHY" if not failed else ("DEGRADED" if len(failed) < 2 else "CRITICAL")
    return {
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "throughput": throughput,
    }
