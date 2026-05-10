from __future__ import annotations

import math
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple

from sqlalchemy.orm import Session

from . import models

_BUCKETS: dict[Tuple[datetime, str, str, str | None, bool], dict[str, Any]] = defaultdict(dict)
_LOCK = threading.Lock()
_MAX_SAMPLES = 200


def _bucket_start(ts: datetime | None = None) -> datetime:
    ts = ts or datetime.now(timezone.utc)
    return ts.replace(second=0, microsecond=0)


def _pct(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil((percentile / 100) * len(ordered)) - 1))
    return round(float(ordered[idx]), 2)


def record_route_metric(*, method: str, route: str, status_code: int, duration_ms: float, tenant_id: str | None = None, is_platform_route: bool = False, timeout: bool = False) -> None:
    key = (_bucket_start(), method.upper(), route[:255] or "unknown", tenant_id, bool(is_platform_route))
    with _LOCK:
        row = _BUCKETS.setdefault(key, {
            "request_count": 0,
            "success_count": 0,
            "client_error_count": 0,
            "server_error_count": 0,
            "timeout_count": 0,
            "total_duration_ms": 0.0,
            "min_duration_ms": None,
            "max_duration_ms": None,
            "samples": [],
        })
        row["request_count"] += 1
        if 200 <= status_code < 400:
            row["success_count"] += 1
        elif 400 <= status_code < 500:
            row["client_error_count"] += 1
        elif status_code >= 500:
            row["server_error_count"] += 1
        if timeout:
            row["timeout_count"] += 1
        row["total_duration_ms"] += float(duration_ms)
        row["min_duration_ms"] = duration_ms if row["min_duration_ms"] is None else min(row["min_duration_ms"], duration_ms)
        row["max_duration_ms"] = duration_ms if row["max_duration_ms"] is None else max(row["max_duration_ms"], duration_ms)
        samples = row["samples"]
        if len(samples) < _MAX_SAMPLES:
            samples.append(float(duration_ms))
        elif row["request_count"] % 10 == 0:
            samples[row["request_count"] % _MAX_SAMPLES] = float(duration_ms)


def live_summary() -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=60)
    total = success = client = server = timeouts = 0
    durations: list[float] = []
    routes: list[dict[str, Any]] = []
    tenants: dict[str, int] = {}
    with _LOCK:
        items = list(_BUCKETS.items())
    for (bucket, method, route, tenant_id, is_platform_route), row in items:
        if bucket < cutoff:
            continue
        request_count = int(row.get("request_count") or 0)
        total += request_count
        success += int(row.get("success_count") or 0)
        client += int(row.get("client_error_count") or 0)
        server += int(row.get("server_error_count") or 0)
        timeouts += int(row.get("timeout_count") or 0)
        durations.extend([float(v) for v in row.get("samples") or []])
        if tenant_id:
            tenants[tenant_id] = tenants.get(tenant_id, 0) + request_count
        routes.append({
            "bucket_start": bucket.isoformat(),
            "method": method,
            "route": route,
            "tenant_id": tenant_id,
            "is_platform_route": is_platform_route,
            "request_count": request_count,
            "server_error_count": int(row.get("server_error_count") or 0),
            "avg_latency_ms": round((float(row.get("total_duration_ms") or 0) / request_count), 2) if request_count else None,
            "p95_latency_ms": _pct([float(v) for v in row.get("samples") or []], 95),
            "p99_latency_ms": _pct([float(v) for v in row.get("samples") or []], 99),
        })
    error_count = client + server + timeouts
    return {
        "requests_last_60m": total,
        "requests_per_minute": round(total / 60, 2),
        "success_count": success,
        "failure_count": error_count,
        "error_rate": round(error_count / total, 4) if total else 0.0,
        "p95_latency_ms": _pct(durations, 95),
        "p99_latency_ms": _pct(durations, 99),
        "slowest_routes": sorted(routes, key=lambda r: r.get("p95_latency_ms") or 0, reverse=True)[:10],
        "noisiest_tenants": sorted([{"tenant_id": k, "requests": v} for k, v in tenants.items()], key=lambda x: x["requests"], reverse=True)[:10],
    }


def flush_route_metrics(db: Session) -> dict[str, int]:
    with _LOCK:
        payload = dict(_BUCKETS)
        _BUCKETS.clear()
    written = 0
    for (bucket, method, route, tenant_id, is_platform_route), row in payload.items():
        request_count = int(row.get("request_count") or 0)
        if request_count <= 0:
            continue
        samples = [float(v) for v in row.get("samples") or []]
        metric = models.PlatformRouteMetric1m(
            bucket_start=bucket,
            method=method,
            route=route,
            tenant_id=tenant_id,
            is_platform_route=is_platform_route,
            request_count=request_count,
            success_count=int(row.get("success_count") or 0),
            client_error_count=int(row.get("client_error_count") or 0),
            server_error_count=int(row.get("server_error_count") or 0),
            timeout_count=int(row.get("timeout_count") or 0),
            total_duration_ms=float(row.get("total_duration_ms") or 0),
            min_duration_ms=row.get("min_duration_ms"),
            max_duration_ms=row.get("max_duration_ms"),
            p50_latency_ms=_pct(samples, 50),
            p95_latency_ms=_pct(samples, 95),
            p99_latency_ms=_pct(samples, 99),
            avg_latency_ms=round((float(row.get("total_duration_ms") or 0) / request_count), 2),
            requests_per_minute=float(request_count),
            errors_per_minute=float(int(row.get("client_error_count") or 0) + int(row.get("server_error_count") or 0) + int(row.get("timeout_count") or 0)),
        )
        db.add(metric)
        written += 1
    db.commit()
    return {"written": written}
