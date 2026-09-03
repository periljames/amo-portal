"""Network diagnostics: measure and log throughput/latency for every leg.

Scenarios
---------
- ``client_portal``   browser  -> portal API      (measured in the browser, logged here)
- ``client_internet`` browser  -> public internet (measured in the browser, logged here)
- ``server_internet`` server   -> public internet (measured here; provider/ISP SLA)
- ``server_database`` server   -> PostgreSQL       (measured here; internal link)

Results are persisted to ``platform_network_probes`` and retained (default 30
days) so operators can see 24h / 7d / 30d trends and catch when a provider is
not delivering the agreed SLA capacity.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import models

logger = logging.getLogger(__name__)

SCENARIOS = ("client_portal", "client_internet", "server_internet", "server_database")

# Cloudflare's speed endpoints are public, CORS-enabled and unauthenticated, so
# the same target works from the browser and the server for an apples-to-apples
# comparison of both legs.
DEFAULT_SPEEDTEST_HOST = os.getenv("PLATFORM_NET_SPEEDTEST_HOST", "speed.cloudflare.com")
DEFAULT_DOWNLOAD_BYTES = int(os.getenv("PLATFORM_NET_DOWNLOAD_BYTES", str(25_000_000)))
DEFAULT_UPLOAD_BYTES = int(os.getenv("PLATFORM_NET_UPLOAD_BYTES", str(10_000_000)))
DEFAULT_DB_BYTES = int(os.getenv("PLATFORM_NET_DB_BYTES", str(4_000_000)))
RETENTION_DAYS = int(os.getenv("PLATFORM_NET_RETENTION_DAYS", "30"))
HTTP_TIMEOUT = float(os.getenv("PLATFORM_NET_HTTP_TIMEOUT_SEC", "30"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _download_url(host: str, size: int) -> str:
    return f"https://{host}/__down?bytes={size}"


def _upload_url(host: str) -> str:
    return f"https://{host}/__up"


def run_internet_speedtest(
    *,
    download_bytes: int = DEFAULT_DOWNLOAD_BYTES,
    upload_bytes: int = DEFAULT_UPLOAD_BYTES,
    host: str = DEFAULT_SPEEDTEST_HOST,
) -> dict[str, Any]:
    """Measure server -> internet latency/jitter and download/upload throughput."""
    import httpx

    result: dict[str, Any] = {
        "scenario": "server_internet",
        "target": host,
        "ok": False,
        "latency_ms": None,
        "jitter_ms": None,
        "download_bps": None,
        "upload_bps": None,
        "download_bytes": None,
        "upload_bytes": None,
        "error": None,
    }
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            # Latency + jitter from a burst of tiny downloads.
            latencies: list[float] = []
            for _ in range(5):
                started = time.perf_counter()
                client.get(_download_url(host, 1000))
                latencies.append((time.perf_counter() - started) * 1000.0)
            result["latency_ms"] = round(sum(latencies) / len(latencies), 2)
            if len(latencies) > 1:
                result["jitter_ms"] = round(
                    sum(abs(latencies[i] - latencies[i - 1]) for i in range(1, len(latencies))) / (len(latencies) - 1),
                    2,
                )

            # Download.
            started = time.perf_counter()
            resp = client.get(_download_url(host, download_bytes))
            received = len(resp.content)
            elapsed = max(1e-3, time.perf_counter() - started)
            result["download_bytes"] = received
            result["download_bps"] = round(received * 8 / elapsed, 2)

            # Upload.
            payload = b"0" * upload_bytes
            started = time.perf_counter()
            client.post(_upload_url(host), content=payload, headers={"Content-Type": "application/octet-stream"})
            elapsed = max(1e-3, time.perf_counter() - started)
            result["upload_bytes"] = upload_bytes
            result["upload_bps"] = round(upload_bytes * 8 / elapsed, 2)
            result["ok"] = True
    except Exception as exc:  # pragma: no cover - network dependent
        result["error"] = str(exc)[:500]
        logger.warning("server->internet speedtest failed: %s", exc)
    return result


def run_database_throughput(db: Session, *, payload_bytes: int = DEFAULT_DB_BYTES) -> dict[str, Any]:
    """Measure server <-> database latency and an app<->DB throughput proxy."""
    result: dict[str, Any] = {
        "scenario": "server_database",
        "target": "postgresql",
        "ok": False,
        "latency_ms": None,
        "jitter_ms": None,
        "download_bps": None,
        "upload_bps": None,
        "download_bytes": None,
        "upload_bytes": None,
        "error": None,
    }
    try:
        latencies: list[float] = []
        for _ in range(5):
            started = time.perf_counter()
            db.execute(text("SELECT 1")).scalar()
            latencies.append((time.perf_counter() - started) * 1000.0)
        result["latency_ms"] = round(sum(latencies) / len(latencies), 2)
        if len(latencies) > 1:
            result["jitter_ms"] = round(
                sum(abs(latencies[i] - latencies[i - 1]) for i in range(1, len(latencies))) / (len(latencies) - 1),
                2,
            )

        # Download proxy: server generates payload_bytes and streams to the app.
        started = time.perf_counter()
        row = db.execute(text("SELECT repeat('x', :n)"), {"n": payload_bytes}).scalar()
        elapsed = max(1e-3, time.perf_counter() - started)
        received = len(row or "")
        result["download_bytes"] = received
        result["download_bps"] = round(received * 8 / elapsed, 2)

        # Upload proxy: the app sends payload_bytes to the server.
        payload = "x" * payload_bytes
        started = time.perf_counter()
        db.execute(text("SELECT length(:p)"), {"p": payload}).scalar()
        elapsed = max(1e-3, time.perf_counter() - started)
        result["upload_bytes"] = payload_bytes
        result["upload_bps"] = round(payload_bytes * 8 / elapsed, 2)
        result["ok"] = True
    except Exception as exc:  # pragma: no cover
        result["error"] = str(exc)[:500]
        logger.warning("server<->database throughput failed: %s", exc)
    return result


def persist_probe(db: Session, *, scenario: str, source: str, data: dict[str, Any]) -> models.PlatformNetworkProbe:
    row = models.PlatformNetworkProbe(
        captured_at=_now(),
        scenario=scenario,
        source=source,
        target=data.get("target"),
        ok=bool(data.get("ok", False)),
        latency_ms=data.get("latency_ms"),
        jitter_ms=data.get("jitter_ms"),
        download_bps=data.get("download_bps"),
        upload_bps=data.get("upload_bps"),
        download_bytes=data.get("download_bytes"),
        upload_bytes=data.get("upload_bytes"),
        error=data.get("error"),
        details_json=data.get("details"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


_WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}


def _stats(values: list[float]) -> dict[str, Any]:
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return {"min": None, "avg": None, "max": None, "p95": None, "samples": 0}
    p95_index = min(len(clean) - 1, int(round(0.95 * (len(clean) - 1))))
    return {
        "min": round(clean[0], 2),
        "avg": round(sum(clean) / len(clean), 2),
        "max": round(clean[-1], 2),
        "p95": round(clean[p95_index], 2),
        "samples": len(clean),
    }


def history(
    db: Session,
    *,
    window: str = "24h",
    scenario: str | None = None,
    sla_download_mbps: float | None = None,
    max_points: int = 400,
) -> dict[str, Any]:
    window = window if window in _WINDOWS else "24h"
    since = _now() - _WINDOWS[window]
    query = db.query(models.PlatformNetworkProbe).filter(models.PlatformNetworkProbe.captured_at >= since)
    scenarios = [scenario] if scenario in SCENARIOS else list(SCENARIOS)
    query = query.filter(models.PlatformNetworkProbe.scenario.in_(scenarios))
    rows = query.order_by(models.PlatformNetworkProbe.captured_at.asc()).all()

    by_scenario: dict[str, list[models.PlatformNetworkProbe]] = {s: [] for s in scenarios}
    for row in rows:
        by_scenario.setdefault(row.scenario, []).append(row)

    payload: dict[str, Any] = {"window": window, "since": since.isoformat(), "scenarios": {}}
    for name, items in by_scenario.items():
        step = max(1, len(items) // max_points)
        points = [
            {
                "at": r.captured_at.isoformat() if r.captured_at else None,
                "latency_ms": r.latency_ms,
                "jitter_ms": r.jitter_ms,
                "download_mbps": round((r.download_bps or 0) / 1_000_000, 2) if r.download_bps is not None else None,
                "upload_mbps": round((r.upload_bps or 0) / 1_000_000, 2) if r.upload_bps is not None else None,
                "ok": r.ok,
                "source": r.source,
            }
            for r in items[::step]
        ]
        download_mbps_values = [(r.download_bps or 0) / 1_000_000 for r in items if r.download_bps is not None]
        breaches = 0
        if sla_download_mbps is not None:
            breaches = sum(1 for v in download_mbps_values if v < sla_download_mbps)
        payload["scenarios"][name] = {
            "points": points,
            "latency_ms": _stats([r.latency_ms for r in items]),
            "download_mbps": _stats(download_mbps_values),
            "upload_mbps": _stats([(r.upload_bps or 0) / 1_000_000 for r in items if r.upload_bps is not None]),
            "failures": sum(1 for r in items if not r.ok),
            "total": len(items),
            "sla_download_mbps": sla_download_mbps,
            "sla_breaches": breaches,
        }
    return payload


def prune(db: Session, *, days: int = RETENTION_DAYS) -> int:
    cutoff = _now() - timedelta(days=max(1, days))
    deleted = (
        db.query(models.PlatformNetworkProbe)
        .filter(models.PlatformNetworkProbe.captured_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(deleted or 0)
