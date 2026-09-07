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
import ipaddress
import os
import statistics
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

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
MIN_TEST_SECONDS = float(os.getenv("PLATFORM_NET_MIN_TEST_SECONDS", "8"))
MAX_TEST_SECONDS = float(os.getenv("PLATFORM_NET_MAX_TEST_SECONDS", "14"))
MAX_TRANSFER_BYTES = int(os.getenv("PLATFORM_NET_MAX_TRANSFER_BYTES", str(1024 * 1024 * 1024)))
LATENCY_SAMPLES = int(os.getenv("PLATFORM_NET_LATENCY_SAMPLES", "9"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _download_url(host: str, size: int) -> str:
    return f"https://{host}/__down?bytes={size}"


def _upload_url(host: str) -> str:
    return f"https://{host}/__up"


def _validated_host(value: str) -> str:
    """Allow public HTTPS speed-test hosts without exposing a generic SSRF probe."""
    clean = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlparse(clean if "://" in clean else f"//{clean}")
    if parsed.scheme and parsed.scheme != "https":
        raise ValueError("Speed-test host must use HTTPS")
    if not parsed.hostname or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Speed-test host must be a public hostname without a path")
    hostname = parsed.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".local"):
        raise ValueError("Speed-test host must be public")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved):
        raise ValueError("Speed-test host must be public")
    return parsed.netloc or hostname


def _http_transfer(url: str, *, payload: bytes | None = None) -> tuple[int, dict[str, str]]:
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST" if payload is not None else "GET",
        headers={"Cache-Control": "no-cache", "Content-Type": "application/octet-stream"},
    )
    received = 0
    with urllib.request.urlopen(request, timeout=max(2.0, HTTP_TIMEOUT)) as response:
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            received += len(chunk)
        headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
    return received, headers


def _jitter(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    return sum(abs(values[index] - values[index - 1]) for index in range(1, len(values))) / (len(values) - 1)


def _is_stable(values: list[float], *, window: int = 4, maximum_cv: float = 0.08) -> bool:
    """True when recent throughput samples have settled within a useful band."""
    if len(values) < window:
        return False
    recent = values[-window:]
    mean = statistics.fmean(recent)
    return mean > 0 and statistics.pstdev(recent) / mean <= maximum_cv


def _transfer_series(
    *,
    host: str,
    direction: str,
    block_bytes: int,
    progress: Callable[[dict[str, Any]], None] | None,
) -> dict[str, Any]:
    started = time.perf_counter()
    total_bytes = 0
    samples: list[float] = []
    last_headers: dict[str, str] = {}
    payload = b"0" * block_bytes if direction == "upload" else None
    while True:
        sample_started = time.perf_counter()
        if direction == "download":
            transferred, last_headers = _http_transfer(_download_url(host, block_bytes))
        else:
            _, last_headers = _http_transfer(_upload_url(host), payload=payload)
            transferred = block_bytes
        sample_elapsed = max(1e-3, time.perf_counter() - sample_started)
        samples.append(transferred * 8 / sample_elapsed)
        total_bytes += transferred
        elapsed = max(1e-3, time.perf_counter() - started)
        stable = _is_stable(samples)
        if progress:
            progress({
                "phase": direction,
                "elapsed_seconds": round(elapsed, 2),
                "bytes": total_bytes,
                "current_bps": round(total_bytes * 8 / elapsed, 2),
                "samples": len(samples),
                "stable": stable,
            })
        enough_time = elapsed >= max(3.0, MIN_TEST_SECONDS)
        capped = elapsed >= max(MIN_TEST_SECONDS, MAX_TEST_SECONDS) or total_bytes >= max(block_bytes, MAX_TRANSFER_BYTES)
        if (enough_time and stable) or capped:
            return {
                "bps": round(total_bytes * 8 / elapsed, 2),
                "bytes": total_bytes,
                "duration_seconds": round(elapsed, 2),
                "samples": len(samples),
                "stable": stable,
                "capped": capped and not (enough_time and stable),
                "headers": last_headers,
            }


def run_internet_speedtest(
    *,
    download_bytes: int = DEFAULT_DOWNLOAD_BYTES,
    upload_bytes: int = DEFAULT_UPLOAD_BYTES,
    host: str = DEFAULT_SPEEDTEST_HOST,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Measure a warmed, duration-bound server-to-edge connection.

    Results are application-level goodput, not a certification of the physical
    access circuit.  Each direction runs until the minimum duration and a
    stable recent sample window are both satisfied, subject to safety caps.
    """
    host = _validated_host(host)
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
        if progress:
            progress({"phase": "latency", "samples": 0})
        _http_transfer(_download_url(host, 1000))  # connection/TLS warm-up
        latencies: list[float] = []
        failures = 0
        for index in range(max(5, LATENCY_SAMPLES)):
            started = time.perf_counter()
            try:
                _http_transfer(_download_url(host, 1000))
                latencies.append((time.perf_counter() - started) * 1000.0)
            except Exception:
                failures += 1
            if progress:
                progress({"phase": "latency", "samples": index + 1, "total_samples": max(5, LATENCY_SAMPLES)})
        if not latencies:
            raise RuntimeError("The public speed-test edge did not return a latency sample")
        result["latency_ms"] = round(statistics.median(latencies), 2)
        jitter = _jitter(latencies)
        result["jitter_ms"] = round(jitter, 2) if jitter is not None else None

        download = _transfer_series(
            host=host,
            direction="download",
            block_bytes=max(1_000_000, min(int(download_bytes), 64 * 1024 * 1024)),
            progress=progress,
        )
        upload = _transfer_series(
            host=host,
            direction="upload",
            block_bytes=max(1_000_000, min(int(upload_bytes), 32 * 1024 * 1024)),
            progress=progress,
        )
        ray = download["headers"].get("cf-ray") or upload["headers"].get("cf-ray")
        location = ray.rsplit("-", 1)[-1].upper() if ray and "-" in ray else None
        duration_ok = download["duration_seconds"] >= MIN_TEST_SECONDS and upload["duration_seconds"] >= MIN_TEST_SECONDS
        stable = bool(download["stable"] and upload["stable"])
        result.update({
            "download_bytes": download["bytes"],
            "download_bps": download["bps"],
            "upload_bytes": upload["bytes"],
            "upload_bps": upload["bps"],
            "ok": True,
            "details": {
                "engine": "adaptive-http-goodput-v2",
                "edge_location": location,
                "packet_loss_percent": round(failures / max(5, LATENCY_SAMPLES) * 100, 2),
                "download": {key: value for key, value in download.items() if key != "headers"},
                "upload": {key: value for key, value in upload.items() if key != "headers"},
                "confidence": "high" if duration_ok and stable else "standard" if duration_ok else "limited",
            },
        })
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
        db.execute(text("SELECT 1")).scalar()  # discard connection/pool warm-up
        latencies: list[float] = []
        for _ in range(9):
            started = time.perf_counter()
            db.execute(text("SELECT 1")).scalar()
            latencies.append((time.perf_counter() - started) * 1000.0)
        result["latency_ms"] = round(statistics.median(latencies), 2)
        jitter = _jitter(latencies)
        result["jitter_ms"] = round(jitter, 2) if jitter is not None else None

        payload_bytes = max(1024, min(int(payload_bytes), 16 * 1024 * 1024))
        download_rates: list[float] = []
        download_total = 0
        for _ in range(5):
            started = time.perf_counter()
            row = db.execute(text("SELECT repeat('x', :n)"), {"n": payload_bytes}).scalar()
            elapsed = max(1e-3, time.perf_counter() - started)
            received = len(row or "")
            download_total += received
            download_rates.append(received * 8 / elapsed)
        result["download_bytes"] = download_total
        result["download_bps"] = round(statistics.median(download_rates), 2)

        payload = "x" * payload_bytes
        upload_rates: list[float] = []
        for _ in range(5):
            started = time.perf_counter()
            db.execute(text("SELECT length(:p)"), {"p": payload}).scalar()
            elapsed = max(1e-3, time.perf_counter() - started)
            upload_rates.append(payload_bytes * 8 / elapsed)
        result["upload_bytes"] = payload_bytes * len(upload_rates)
        result["upload_bps"] = round(statistics.median(upload_rates), 2)
        result["details"] = {
            "engine": "median-db-goodput-v2",
            "latency_samples": len(latencies),
            "download_samples": len(download_rates),
            "upload_samples": len(upload_rates),
        }
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
                "target": r.target,
                "error": r.error,
                "details": r.details_json,
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
