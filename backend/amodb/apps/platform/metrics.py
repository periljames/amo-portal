from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Tuple

from sqlalchemy import case, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from . import models

logger = logging.getLogger(__name__)

_BUCKETS: dict[Tuple[datetime, str, str, str | None, bool], dict[str, Any]] = defaultdict(dict)
_LOCK = threading.Lock()
_MAX_SAMPLES = 200
_PERSISTED_CACHE_TTL_SECONDS = 10.0
_PERSISTED_CACHE: dict[str, Any] = {"at": 0.0, "minutes": 0, "rows": []}

_AUTO_FLUSH_LOCK = threading.Lock()
_AUTO_FLUSH_IN_FLIGHT = False
_AUTO_FLUSH_INTERVAL_SECONDS = max(5.0, float(os.getenv("PLATFORM_METRICS_FLUSH_INTERVAL_SEC", "30") or "30"))
_LAST_AUTO_FLUSH_AT = time.monotonic()

_NETWORK_LOCK = threading.Lock()
_NETWORK_LAST: dict[str, Any] | None = None
_NETWORK_HISTORY: deque[dict[str, Any]] = deque(maxlen=1_440)
_NETWORK_MIN_SAMPLE_SECONDS = 0.75


def _bucket_start(ts: datetime | None = None) -> datetime:
    ts = ts or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).replace(second=0, microsecond=0)


def _pct(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil((percentile / 100) * len(ordered)) - 1))
    return round(float(ordered[idx]), 2)


def _as_utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _weighted(values: list[tuple[float | None, int]]) -> float | None:
    usable = [(float(value), max(1, int(weight))) for value, weight in values if value is not None]
    if not usable:
        return None
    total_weight = sum(weight for _, weight in usable)
    return round(sum(value * weight for value, weight in usable) / total_weight, 2)


def _new_bucket_row() -> dict[str, Any]:
    return {
        "request_count": 0,
        "success_count": 0,
        "client_error_count": 0,
        "server_error_count": 0,
        "timeout_count": 0,
        "total_duration_ms": 0.0,
        "min_duration_ms": None,
        "max_duration_ms": None,
        "samples": [],
    }


def _merge_bucket_rows(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    for key in ("request_count", "success_count", "client_error_count", "server_error_count", "timeout_count"):
        target[key] = int(target.get(key) or 0) + int(source.get(key) or 0)
    target["total_duration_ms"] = float(target.get("total_duration_ms") or 0) + float(source.get("total_duration_ms") or 0)
    source_min = source.get("min_duration_ms")
    target_min = target.get("min_duration_ms")
    if source_min is not None:
        target["min_duration_ms"] = source_min if target_min is None else min(float(target_min), float(source_min))
    source_max = source.get("max_duration_ms")
    target_max = target.get("max_duration_ms")
    if source_max is not None:
        target["max_duration_ms"] = source_max if target_max is None else max(float(target_max), float(source_max))
    samples = [float(value) for value in target.get("samples") or []]
    samples.extend(float(value) for value in source.get("samples") or [])
    target["samples"] = samples[-_MAX_SAMPLES:]
    return target


def _drain_route_metrics(*, include_current: bool = False) -> dict[Tuple[datetime, str, str, str | None, bool], dict[str, Any]]:
    current_bucket = _bucket_start()
    with _LOCK:
        keys = [
            key
            for key in _BUCKETS
            if include_current or key[0] < current_bucket
        ]
        payload = {key: _BUCKETS.pop(key) for key in keys}
        if payload:
            _PERSISTED_CACHE.update({"at": 0.0, "minutes": 0, "rows": []})
    return payload


def _restore_route_metrics(payload: dict[Tuple[datetime, str, str, str | None, bool], dict[str, Any]]) -> None:
    if not payload:
        return
    with _LOCK:
        for key, row in payload.items():
            target = _BUCKETS.setdefault(key, _new_bucket_row())
            _merge_bucket_rows(target, row)


def _auto_flush_worker() -> None:
    global _AUTO_FLUSH_IN_FLIGHT
    db = None
    try:
        from amodb.database import WriteSessionLocal

        db = WriteSessionLocal()
        flush_route_metrics(db, include_current=False)
    except Exception:
        logger.warning("Unable to persist platform route metrics from the API process.", exc_info=True)
    finally:
        if db is not None:
            db.close()
        with _AUTO_FLUSH_LOCK:
            _AUTO_FLUSH_IN_FLIGHT = False


def _schedule_auto_flush() -> None:
    global _AUTO_FLUSH_IN_FLIGHT
    global _LAST_AUTO_FLUSH_AT

    now = time.monotonic()
    with _AUTO_FLUSH_LOCK:
        if _AUTO_FLUSH_IN_FLIGHT or now - _LAST_AUTO_FLUSH_AT < _AUTO_FLUSH_INTERVAL_SECONDS:
            return
        _AUTO_FLUSH_IN_FLIGHT = True
        _LAST_AUTO_FLUSH_AT = now
    threading.Thread(
        target=_auto_flush_worker,
        name="platform-metrics-flush",
        daemon=True,
    ).start()


def record_route_metric(
    *,
    method: str,
    route: str,
    status_code: int,
    duration_ms: float,
    tenant_id: str | None = None,
    actor_user_id: str | None = None,
    is_platform_route: bool = False,
    timeout: bool = False,
) -> None:
    del actor_user_id  # Retained for backwards-compatible callers and tests.
    key = (_bucket_start(), method.upper(), route[:255] or "unknown", tenant_id, bool(is_platform_route))
    with _LOCK:
        row = _BUCKETS.setdefault(key, _new_bucket_row())
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
    _schedule_auto_flush()


def _read_network_totals() -> dict[str, Any] | None:
    proc_net_dev = Path("/proc/net/dev")
    if proc_net_dev.exists():
        ingress = egress = interfaces = 0
        try:
            for line in proc_net_dev.read_text(encoding="utf-8").splitlines()[2:]:
                if ":" not in line:
                    continue
                name, payload = line.split(":", 1)
                interface = name.strip()
                if interface.lower() == "lo":
                    continue
                fields = payload.split()
                if len(fields) < 16:
                    continue
                ingress += int(fields[0])
                egress += int(fields[8])
                interfaces += 1
            if interfaces:
                return {
                    "ingress_bytes_total": ingress,
                    "egress_bytes_total": egress,
                    "interface_count": interfaces,
                    "source": "linux:/proc/net/dev",
                }
        except (OSError, ValueError):
            pass

    try:
        import psutil  # type: ignore[import-not-found]

        counters = psutil.net_io_counters(pernic=True)
        ingress = egress = interfaces = 0
        for name, values in counters.items():
            lower = str(name).strip().lower()
            if lower == "lo" or lower.startswith("loopback"):
                continue
            ingress += int(values.bytes_recv)
            egress += int(values.bytes_sent)
            interfaces += 1
        if interfaces:
            return {
                "ingress_bytes_total": ingress,
                "egress_bytes_total": egress,
                "interface_count": interfaces,
                "source": "psutil:host-interfaces",
            }
    except Exception:
        pass
    return None


def _sample_network() -> dict[str, Any]:
    global _NETWORK_LAST

    now = datetime.now(timezone.utc)
    monotonic_now = time.monotonic()
    totals = _read_network_totals()
    with _NETWORK_LOCK:
        if totals is None:
            latest = _NETWORK_HISTORY[-1] if _NETWORK_HISTORY else None
            return latest or {
                "at": now.isoformat(),
                "available": False,
                "warming_up": False,
                "source": "unavailable",
                "scope": "host_interfaces",
                "ingress_bytes_per_second": None,
                "egress_bytes_per_second": None,
                "total_bytes_per_second": None,
            }

        if _NETWORK_LAST and monotonic_now - float(_NETWORK_LAST["monotonic"]) < _NETWORK_MIN_SAMPLE_SECONDS:
            return _NETWORK_HISTORY[-1] if _NETWORK_HISTORY else {
                **totals,
                "at": now.isoformat(),
                "available": True,
                "warming_up": True,
                "scope": "host_interfaces",
                "ingress_bytes_per_second": None,
                "egress_bytes_per_second": None,
                "total_bytes_per_second": None,
            }

        ingress_rate: float | None = None
        egress_rate: float | None = None
        elapsed: float | None = None
        if _NETWORK_LAST:
            elapsed = max(0.001, monotonic_now - float(_NETWORK_LAST["monotonic"]))
            ingress_delta = int(totals["ingress_bytes_total"]) - int(_NETWORK_LAST["ingress_bytes_total"])
            egress_delta = int(totals["egress_bytes_total"]) - int(_NETWORK_LAST["egress_bytes_total"])
            if ingress_delta >= 0 and egress_delta >= 0:
                ingress_rate = round(ingress_delta / elapsed, 2)
                egress_rate = round(egress_delta / elapsed, 2)

        sample = {
            **totals,
            "at": now.isoformat(),
            "monotonic": monotonic_now,
            "available": True,
            "warming_up": ingress_rate is None or egress_rate is None,
            "scope": "host_interfaces",
            "sample_interval_seconds": round(elapsed, 2) if elapsed is not None else None,
            "ingress_bytes_per_second": ingress_rate,
            "egress_bytes_per_second": egress_rate,
            "total_bytes_per_second": round((ingress_rate or 0) + (egress_rate or 0), 2) if ingress_rate is not None and egress_rate is not None else None,
        }
        _NETWORK_LAST = {
            **totals,
            "monotonic": monotonic_now,
        }
        _NETWORK_HISTORY.append(sample)
        return sample


def _downsample(items: list[dict[str, Any]], maximum: int = 120) -> list[dict[str, Any]]:
    if len(items) <= maximum:
        return items
    step = max(1, math.ceil(len(items) / maximum))
    reduced = items[::step]
    if reduced[-1] is not items[-1]:
        reduced.append(items[-1])
    return reduced[-maximum:]


def _network_summary(minutes: int) -> dict[str, Any]:
    latest = _sample_network()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    with _NETWORK_LOCK:
        samples = [
            dict(item)
            for item in _NETWORK_HISTORY
            if (_as_utc(item.get("at")) or cutoff) >= cutoff
        ]

    valid = [item for item in samples if item.get("total_bytes_per_second") is not None]
    current_total = latest.get("total_bytes_per_second")
    current_ingress = latest.get("ingress_bytes_per_second")
    current_egress = latest.get("egress_bytes_per_second")
    peak = max((float(item["total_bytes_per_second"]) for item in valid), default=None)
    average = round(
        sum(float(item["total_bytes_per_second"]) for item in valid) / len(valid),
        2,
    ) if valid else None

    transfer_bytes = 0
    if len(samples) >= 2:
        first = samples[0]
        last = samples[-1]
        ingress_delta = int(last.get("ingress_bytes_total") or 0) - int(first.get("ingress_bytes_total") or 0)
        egress_delta = int(last.get("egress_bytes_total") or 0) - int(first.get("egress_bytes_total") or 0)
        transfer_bytes = max(0, ingress_delta) + max(0, egress_delta)

    public_series = [
        {
            "at": item.get("at"),
            "ingress_bytes_per_second": item.get("ingress_bytes_per_second"),
            "egress_bytes_per_second": item.get("egress_bytes_per_second"),
            "total_bytes_per_second": item.get("total_bytes_per_second"),
        }
        for item in _downsample(samples)
    ]
    return {
        "available": bool(latest.get("available")),
        "warming_up": bool(latest.get("warming_up")),
        "scope": "host_interfaces",
        "source": latest.get("source") or "unavailable",
        "interface_count": int(latest.get("interface_count") or 0),
        "current_ingress_bytes_per_second": current_ingress,
        "current_egress_bytes_per_second": current_egress,
        "current_total_bytes_per_second": current_total,
        "peak_total_bytes_per_second": round(peak, 2) if peak is not None else None,
        "average_total_bytes_per_second": average,
        "transfer_bytes_window": transfer_bytes,
        "window_minutes": minutes,
        "sample_count": len(valid),
        "sample_interval_seconds": latest.get("sample_interval_seconds"),
        "series": public_series,
        "note": "Host-interface traffic includes the API process and any other traffic using the same host interfaces.",
    }


def _persisted_rows(minutes: int) -> list[dict[str, Any]]:
    now_monotonic = time.monotonic()
    with _LOCK:
        if (
            int(_PERSISTED_CACHE.get("minutes") or 0) == minutes
            and now_monotonic - float(_PERSISTED_CACHE.get("at") or 0.0) <= _PERSISTED_CACHE_TTL_SECONDS
        ):
            return [dict(row) for row in _PERSISTED_CACHE.get("rows") or []]

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    rows: list[dict[str, Any]] = []
    db = None
    try:
        from amodb.database import ReadSessionLocal

        db = ReadSessionLocal()
        query_rows = (
            db.query(models.PlatformRouteMetric1m)
            .filter(models.PlatformRouteMetric1m.bucket_start >= cutoff)
            .order_by(models.PlatformRouteMetric1m.bucket_start.asc())
            .all()
        )
        rows = [
            {
                "bucket_start": _as_utc(row.bucket_start),
                "method": row.method,
                "route": row.route,
                "tenant_id": row.tenant_id,
                "is_platform_route": bool(row.is_platform_route),
                "request_count": int(row.request_count or 0),
                "success_count": int(row.success_count or 0),
                "client_error_count": int(row.client_error_count or 0),
                "server_error_count": int(row.server_error_count or 0),
                "timeout_count": int(row.timeout_count or 0),
                "total_duration_ms": float(row.total_duration_ms or 0),
                "avg_latency_ms": row.avg_latency_ms,
                "p95_latency_ms": row.p95_latency_ms,
                "p99_latency_ms": row.p99_latency_ms,
                "samples": [],
                "source": "persisted",
            }
            for row in query_rows
        ]
    except Exception:
        rows = []
    finally:
        if db is not None:
            db.close()

    with _LOCK:
        _PERSISTED_CACHE.update({"at": now_monotonic, "minutes": minutes, "rows": rows})
    return [dict(row) for row in rows]


def _live_rows(cutoff: datetime) -> list[dict[str, Any]]:
    with _LOCK:
        items = list(_BUCKETS.items())
    rows: list[dict[str, Any]] = []
    for (bucket, method, route, tenant_id, is_platform_route), row in items:
        bucket_utc = _as_utc(bucket)
        if bucket_utc is None or bucket_utc < cutoff:
            continue
        request_count = int(row.get("request_count") or 0)
        rows.append({
            "bucket_start": bucket_utc,
            "method": method,
            "route": route,
            "tenant_id": tenant_id,
            "is_platform_route": is_platform_route,
            "request_count": request_count,
            "success_count": int(row.get("success_count") or 0),
            "client_error_count": int(row.get("client_error_count") or 0),
            "server_error_count": int(row.get("server_error_count") or 0),
            "timeout_count": int(row.get("timeout_count") or 0),
            "total_duration_ms": float(row.get("total_duration_ms") or 0),
            "avg_latency_ms": round((float(row.get("total_duration_ms") or 0) / request_count), 2) if request_count else None,
            "p95_latency_ms": _pct([float(value) for value in row.get("samples") or []], 95),
            "p99_latency_ms": _pct([float(value) for value in row.get("samples") or []], 99),
            "samples": [float(value) for value in row.get("samples") or []],
            "source": "live",
        })
    return rows


def _trend_series(rows: list[dict[str, Any]], minutes: int) -> list[dict[str, Any]]:
    end = _bucket_start()
    start = end - timedelta(minutes=minutes - 1)
    buckets: dict[datetime, dict[str, Any]] = {}
    for row in rows:
        bucket = _bucket_start(_as_utc(row.get("bucket_start")) or end)
        if bucket < start or bucket > end:
            continue
        aggregate = buckets.setdefault(bucket, {
            "requests": 0,
            "errors": 0,
            "timeouts": 0,
            "p95": [],
            "p99": [],
            "avg": [],
        })
        request_count = int(row.get("request_count") or 0)
        errors = int(row.get("client_error_count") or 0) + int(row.get("server_error_count") or 0)
        aggregate["requests"] += request_count
        aggregate["errors"] += errors
        aggregate["timeouts"] += int(row.get("timeout_count") or 0)
        aggregate["p95"].append((row.get("p95_latency_ms"), request_count))
        aggregate["p99"].append((row.get("p99_latency_ms"), request_count))
        aggregate["avg"].append((row.get("avg_latency_ms"), request_count))

    series: list[dict[str, Any]] = []
    cursor = start
    while cursor <= end:
        aggregate = buckets.get(cursor) or {"requests": 0, "errors": 0, "timeouts": 0, "p95": [], "p99": [], "avg": []}
        requests = int(aggregate["requests"])
        errors = int(aggregate["errors"])
        series.append({
            "at": cursor.isoformat(),
            "requests": requests,
            "requests_per_minute": float(requests),
            "errors": errors,
            "timeouts": int(aggregate["timeouts"]),
            "error_rate": round(errors / requests, 4) if requests else 0.0,
            "avg_latency_ms": _weighted(aggregate["avg"]),
            "p95_latency_ms": _weighted(aggregate["p95"]),
            "p99_latency_ms": _weighted(aggregate["p99"]),
        })
        cursor += timedelta(minutes=1)
    return series


def live_summary(minutes: int = 60) -> dict[str, Any]:
    window_minutes = max(5, min(int(minutes or 60), 1_440))
    cutoff = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=window_minutes - 1)
    persisted_rows = _persisted_rows(window_minutes)
    live_rows = _live_rows(cutoff)
    rows = [row for row in persisted_rows if (_as_utc(row.get("bucket_start")) or cutoff) >= cutoff] + live_rows

    total = success = client = server = timeouts = 0
    route_aggregates: dict[tuple[str, str, str | None, bool], dict[str, Any]] = {}
    tenants: dict[str, int] = {}
    for row in rows:
        request_count = int(row.get("request_count") or 0)
        total += request_count
        success += int(row.get("success_count") or 0)
        client += int(row.get("client_error_count") or 0)
        server += int(row.get("server_error_count") or 0)
        timeouts += int(row.get("timeout_count") or 0)
        tenant_id = row.get("tenant_id")
        if tenant_id:
            tenants[str(tenant_id)] = tenants.get(str(tenant_id), 0) + request_count

        key = (
            str(row.get("method") or "GET"),
            str(row.get("route") or "unknown"),
            str(tenant_id) if tenant_id else None,
            bool(row.get("is_platform_route")),
        )
        aggregate = route_aggregates.setdefault(key, {
            "request_count": 0,
            "server_error_count": 0,
            "p95": [],
            "p99": [],
            "avg": [],
        })
        aggregate["request_count"] += request_count
        aggregate["server_error_count"] += int(row.get("server_error_count") or 0)
        aggregate["p95"].append((row.get("p95_latency_ms"), request_count))
        aggregate["p99"].append((row.get("p99_latency_ms"), request_count))
        aggregate["avg"].append((row.get("avg_latency_ms"), request_count))

    routes: list[dict[str, Any]] = []
    for (method, route, tenant_id, is_platform_route), aggregate in route_aggregates.items():
        routes.append({
            "method": method,
            "route": route,
            "tenant_id": tenant_id,
            "is_platform_route": is_platform_route,
            "request_count": int(aggregate["request_count"]),
            "server_error_count": int(aggregate["server_error_count"]),
            "avg_latency_ms": _weighted(aggregate["avg"]),
            "p95_latency_ms": _weighted(aggregate["p95"]),
            "p99_latency_ms": _weighted(aggregate["p99"]),
        })

    error_count = client + server
    trend = _trend_series(rows, window_minutes)
    global_p95 = _weighted([
        (row.get("p95_latency_ms"), int(row.get("request_count") or 0)) for row in rows
    ])
    global_p99 = _weighted([
        (row.get("p99_latency_ms"), int(row.get("request_count") or 0)) for row in rows
    ])

    current_requests_per_minute = float(trend[-1]["requests_per_minute"]) if trend else 0.0
    peak_requests_per_minute = max((float(point["requests_per_minute"]) for point in trend), default=0.0)

    return {
        "window_minutes": window_minutes,
        "requests_last_60m": total if window_minutes == 60 else None,
        "requests_in_window": total,
        "requests_per_minute": round(total / window_minutes, 2),
        "current_requests_per_minute": current_requests_per_minute,
        "peak_requests_per_minute": peak_requests_per_minute,
        "success_count": success,
        "failure_count": error_count,
        "timeout_count": timeouts,
        "error_rate": round(error_count / total, 4) if total else 0.0,
        "p95_latency_ms": global_p95,
        "p99_latency_ms": global_p99,
        "trend_series": trend,
        "bandwidth": _network_summary(window_minutes),
        "metric_coverage": {
            "persisted_route_rows": len(persisted_rows),
            "live_route_rows": len(live_rows),
            "points": len(trend),
            "oldest_at": trend[0]["at"] if trend else None,
            "newest_at": trend[-1]["at"] if trend else None,
        },
        "slowest_routes": sorted(routes, key=lambda row: row.get("p95_latency_ms") or 0, reverse=True)[:10],
        "noisiest_tenants": sorted(
            [{"tenant_id": key, "requests": value} for key, value in tenants.items()],
            key=lambda item: item["requests"],
            reverse=True,
        )[:10],
    }


def _latency_upsert_expression(table, excluded, column_name: str, new_request_count):
    existing_value = getattr(table.c, column_name)
    incoming_value = getattr(excluded, column_name)
    return case(
        (incoming_value.is_(None), existing_value),
        (existing_value.is_(None), incoming_value),
        else_=(
            (existing_value * table.c.request_count)
            + (incoming_value * excluded.request_count)
        ) / func.nullif(new_request_count, 0),
    )


def _minimum_upsert_expression(existing, incoming):
    return case(
        (incoming.is_(None), existing),
        (existing.is_(None), incoming),
        else_=func.least(existing, incoming),
    )


def _maximum_upsert_expression(existing, incoming):
    return case(
        (incoming.is_(None), existing),
        (existing.is_(None), incoming),
        else_=func.greatest(existing, incoming),
    )


def flush_route_metrics(db: Session, *, include_current: bool = False) -> dict[str, int]:
    payload = _drain_route_metrics(include_current=include_current)
    if not payload:
        return {"written": 0}

    table = models.PlatformRouteMetric1m.__table__
    written = 0
    try:
        for (bucket, method, route, tenant_id, is_platform_route), row in payload.items():
            request_count = int(row.get("request_count") or 0)
            if request_count <= 0:
                continue
            samples = [float(value) for value in row.get("samples") or []]
            error_count = int(row.get("client_error_count") or 0) + int(row.get("server_error_count") or 0)
            values = {
                "id": getattr(models.PlatformRouteMetric1m, "id").default.arg() if getattr(models.PlatformRouteMetric1m, "id").default else None,
                "bucket_start": bucket,
                "method": method,
                "route": route,
                "tenant_id": tenant_id,
                "is_platform_route": is_platform_route,
                "request_count": request_count,
                "success_count": int(row.get("success_count") or 0),
                "client_error_count": int(row.get("client_error_count") or 0),
                "server_error_count": int(row.get("server_error_count") or 0),
                "timeout_count": int(row.get("timeout_count") or 0),
                "total_duration_ms": float(row.get("total_duration_ms") or 0),
                "min_duration_ms": row.get("min_duration_ms"),
                "max_duration_ms": row.get("max_duration_ms"),
                "p50_latency_ms": _pct(samples, 50),
                "p95_latency_ms": _pct(samples, 95),
                "p99_latency_ms": _pct(samples, 99),
                "avg_latency_ms": round((float(row.get("total_duration_ms") or 0) / request_count), 2),
                "requests_per_minute": float(request_count),
                "errors_per_minute": float(error_count),
            }
            if values["id"] is None:
                values.pop("id")
            statement = pg_insert(table).values(**values)
            excluded = statement.excluded
            new_request_count = table.c.request_count + excluded.request_count
            statement = statement.on_conflict_do_update(
                index_elements=[
                    table.c.bucket_start,
                    table.c.method,
                    table.c.route,
                    table.c.tenant_id,
                    table.c.is_platform_route,
                ],
                set_={
                    "request_count": new_request_count,
                    "success_count": table.c.success_count + excluded.success_count,
                    "client_error_count": table.c.client_error_count + excluded.client_error_count,
                    "server_error_count": table.c.server_error_count + excluded.server_error_count,
                    "timeout_count": table.c.timeout_count + excluded.timeout_count,
                    "total_duration_ms": table.c.total_duration_ms + excluded.total_duration_ms,
                    "min_duration_ms": _minimum_upsert_expression(table.c.min_duration_ms, excluded.min_duration_ms),
                    "max_duration_ms": _maximum_upsert_expression(table.c.max_duration_ms, excluded.max_duration_ms),
                    "p50_latency_ms": _latency_upsert_expression(table, excluded, "p50_latency_ms", new_request_count),
                    "p95_latency_ms": _latency_upsert_expression(table, excluded, "p95_latency_ms", new_request_count),
                    "p99_latency_ms": _latency_upsert_expression(table, excluded, "p99_latency_ms", new_request_count),
                    "avg_latency_ms": (
                        (table.c.total_duration_ms + excluded.total_duration_ms)
                        / func.nullif(new_request_count, 0)
                    ),
                    "requests_per_minute": new_request_count,
                    "errors_per_minute": table.c.errors_per_minute + excluded.errors_per_minute,
                },
            )
            db.execute(statement)
            written += 1
        db.commit()
    except Exception:
        db.rollback()
        _restore_route_metrics(payload)
        raise
    with _LOCK:
        _PERSISTED_CACHE.update({"at": 0.0, "minutes": 0, "rows": []})
    return {"written": written}


def flush_current_process_metrics() -> dict[str, int]:
    db = None
    try:
        from amodb.database import WriteSessionLocal

        db = WriteSessionLocal()
        return flush_route_metrics(db, include_current=True)
    finally:
        if db is not None:
            db.close()
