from __future__ import annotations

import copy
import json
import math
import os
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


@dataclass(frozen=True)
class QuerySpec:
    expression: str
    unit: str
    max_lookback_seconds: int
    min_step_seconds: int
    max_samples: int = 1500
    timeout_seconds: float = 1.5
    cache_ttl_seconds: float = 5.0


# Expressions are repository-owned and never accepted from the browser. Labels are
# deliberately infrastructure/service bounded; tenant/user/document identifiers are
# forbidden in this registry and asserted in CI.
QUERY_REGISTRY: dict[str, QuerySpec] = {
    # Host CPU / scheduler.
    "host_cpu_utilization": QuerySpec('100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)', "percent", 30 * 86400, 15),
    "host_cpu_user": QuerySpec('avg by(instance) (rate(node_cpu_seconds_total{mode="user"}[5m])) * 100', "percent", 30 * 86400, 15),
    "host_cpu_system": QuerySpec('avg by(instance) (rate(node_cpu_seconds_total{mode="system"}[5m])) * 100', "percent", 30 * 86400, 15),
    "host_cpu_iowait": QuerySpec('avg by(instance) (rate(node_cpu_seconds_total{mode="iowait"}[5m])) * 100', "percent", 30 * 86400, 15),
    "host_cpu_steal": QuerySpec('avg by(instance) (rate(node_cpu_seconds_total{mode="steal"}[5m])) * 100', "percent", 30 * 86400, 15),
    "host_cpu_per_core": QuerySpec('100 - (avg by(instance,cpu) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)', "percent", 7 * 86400, 15),
    "host_cpu_count": QuerySpec('count without(cpu,mode) (node_cpu_seconds_total{mode="idle"})', "cores", 30 * 86400, 60),
    "host_load_1m": QuerySpec("node_load1", "load", 30 * 86400, 15),
    "host_load_5m": QuerySpec("node_load5", "load", 30 * 86400, 15),
    "host_load_15m": QuerySpec("node_load15", "load", 30 * 86400, 15),
    "host_procs_running": QuerySpec("node_procs_running", "processes", 30 * 86400, 30),
    "host_procs_blocked": QuerySpec("node_procs_blocked", "processes", 30 * 86400, 30),

    # Host memory / VM pressure.
    "host_memory_utilization": QuerySpec('(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100', "percent", 30 * 86400, 15),
    "host_memory_available": QuerySpec("node_memory_MemAvailable_bytes", "bytes", 30 * 86400, 15),
    "host_page_cache": QuerySpec("node_memory_Cached_bytes + node_memory_SReclaimable_bytes", "bytes", 30 * 86400, 30),
    "host_swap_utilization": QuerySpec('(1 - (node_memory_SwapFree_bytes / clamp_min(node_memory_SwapTotal_bytes, 1))) * 100', "percent", 30 * 86400, 30),
    "host_swap_in": QuerySpec("rate(node_vmstat_pswpin[5m])", "pages_per_second", 30 * 86400, 30),
    "host_swap_out": QuerySpec("rate(node_vmstat_pswpout[5m])", "pages_per_second", 30 * 86400, 30),
    "host_oom_kills": QuerySpec("increase(node_vmstat_oom_kill[5m])", "events", 30 * 86400, 60),

    # Filesystem / block device.
    "filesystem_utilization": QuerySpec('100 * (1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs"}))', "percent", 30 * 86400, 30),
    "filesystem_free": QuerySpec('node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs"}', "bytes", 30 * 86400, 30),
    "filesystem_inode_utilization": QuerySpec('100 * (1 - (node_filesystem_files_free{fstype!~"tmpfs|overlay|squashfs"} / clamp_min(node_filesystem_files{fstype!~"tmpfs|overlay|squashfs"}, 1)))', "percent", 30 * 86400, 30),
    "disk_read_throughput": QuerySpec('sum by(instance) (rate(node_disk_read_bytes_total{device!~"loop.*|ram.*"}[5m]))', "bytes_per_second", 30 * 86400, 30),
    "disk_write_throughput": QuerySpec('sum by(instance) (rate(node_disk_written_bytes_total{device!~"loop.*|ram.*"}[5m]))', "bytes_per_second", 30 * 86400, 30),
    "disk_read_latency": QuerySpec('sum by(instance) (rate(node_disk_read_time_seconds_total{device!~"loop.*|ram.*"}[5m])) / clamp_min(sum by(instance) (rate(node_disk_reads_completed_total{device!~"loop.*|ram.*"}[5m])), 0.001)', "seconds", 30 * 86400, 30),
    "disk_write_latency": QuerySpec('sum by(instance) (rate(node_disk_write_time_seconds_total{device!~"loop.*|ram.*"}[5m])) / clamp_min(sum by(instance) (rate(node_disk_writes_completed_total{device!~"loop.*|ram.*"}[5m])), 0.001)', "seconds", 30 * 86400, 30),
    "disk_io_utilization": QuerySpec('sum by(instance) (rate(node_disk_io_time_seconds_total{device!~"loop.*|ram.*"}[5m])) * 100', "percent", 30 * 86400, 30),

    # Network / TCP.
    "network_ingress": QuerySpec('sum by(instance) (rate(node_network_receive_bytes_total{device!="lo"}[5m]))', "bytes_per_second", 30 * 86400, 15),
    "network_egress": QuerySpec('sum by(instance) (rate(node_network_transmit_bytes_total{device!="lo"}[5m]))', "bytes_per_second", 30 * 86400, 15),
    "network_errors": QuerySpec('sum by(instance) (rate(node_network_receive_errs_total{device!="lo"}[5m]) + rate(node_network_transmit_errs_total{device!="lo"}[5m]))', "errors_per_second", 30 * 86400, 30),
    "network_drops": QuerySpec('sum by(instance) (rate(node_network_receive_drop_total{device!="lo"}[5m]) + rate(node_network_transmit_drop_total{device!="lo"}[5m]))', "drops_per_second", 30 * 86400, 30),
    "tcp_established": QuerySpec("node_netstat_Tcp_CurrEstab", "connections", 30 * 86400, 30),
    "tcp_inuse": QuerySpec("node_sockstat_TCP_inuse", "sockets", 30 * 86400, 30),
    "tcp_timewait": QuerySpec("node_sockstat_TCP_tw", "sockets", 30 * 86400, 30),

    # Host lifecycle.
    "host_uptime": QuerySpec("time() - node_boot_time_seconds", "seconds", 30 * 86400, 60),
    "host_boot_time": QuerySpec("node_boot_time_seconds", "epoch_seconds", 30 * 86400, 60),

    # Container / process boundary from cAdvisor.
    "container_cpu": QuerySpec('sum by(instance,name) (rate(container_cpu_usage_seconds_total{name!=""}[5m])) * 100', "percent", 7 * 86400, 30),
    "container_memory": QuerySpec('sum by(instance,name) (container_memory_working_set_bytes{name!=""})', "bytes", 7 * 86400, 30),
    "container_block_read": QuerySpec('sum by(instance,name) (rate(container_fs_reads_bytes_total{name!=""}[5m]))', "bytes_per_second", 7 * 86400, 30),
    "container_block_write": QuerySpec('sum by(instance,name) (rate(container_fs_writes_bytes_total{name!=""}[5m]))', "bytes_per_second", 7 * 86400, 30),
    "container_uptime": QuerySpec('time() - container_start_time_seconds{name!=""}', "seconds", 7 * 86400, 60),
    "container_restarts_1h": QuerySpec('changes(container_start_time_seconds{name!=""}[1h])', "restarts", 7 * 86400, 60),

    # Component scrape health.
    "target_up": QuerySpec('up{job=~"node-exporter|cadvisor|otel-hub|prometheus|alertmanager"}', "boolean", 30 * 86400, 15),

    # Application / SQLAlchemy pool metrics exported by OpenTelemetry.
    "process_cpu": QuerySpec("amo_process_cpu_percent", "percent", 7 * 86400, 15),
    "process_memory_rss": QuerySpec("amo_process_memory_rss_bytes", "bytes", 7 * 86400, 15),
    "db_pool_checked_out": QuerySpec("amo_db_pool_checked_out", "connections", 30 * 86400, 30),
    "db_pool_idle": QuerySpec("amo_db_pool_idle", "connections", 30 * 86400, 30),
    "db_pool_size": QuerySpec("amo_db_pool_size", "connections", 30 * 86400, 30),
    "db_pool_overflow": QuerySpec("amo_db_pool_overflow", "connections", 30 * 86400, 30),
    "db_pool_utilization": QuerySpec('100 * amo_db_pool_checked_out / clamp_min(amo_db_pool_size + clamp_min(amo_db_pool_overflow, 0), 1)', "percent", 30 * 86400, 30),

    # PostgreSQL semantic health metrics exported by the application. These queries
    # never expose SQL text or tenant identifiers.
    "db_active_connections": QuerySpec("amo_db_active_connections", "connections", 30 * 86400, 30),
    "db_max_connections": QuerySpec("amo_db_max_connections", "connections", 30 * 86400, 60),
    "db_connection_utilization": QuerySpec("100 * amo_db_active_connections / clamp_min(amo_db_max_connections, 1)", "percent", 30 * 86400, 30),
    "db_waiting_connections": QuerySpec("amo_db_waiting_connections", "connections", 30 * 86400, 30),
    "db_lock_waiters": QuerySpec("amo_db_lock_waiters", "connections", 30 * 86400, 30),
    "db_deadlocks_total": QuerySpec("amo_db_deadlocks_total", "deadlocks", 30 * 86400, 60),
    "db_commits_total": QuerySpec("amo_db_commits_total", "transactions", 30 * 86400, 30),
    "db_rollbacks_total": QuerySpec("amo_db_rollbacks_total", "transactions", 30 * 86400, 30),
    "db_transaction_rate": QuerySpec("rate(amo_db_commits_total[5m]) + rate(amo_db_rollbacks_total[5m])", "transactions_per_second", 30 * 86400, 30),
    "db_size": QuerySpec("amo_db_size_bytes", "bytes", 30 * 86400, 60),
    "db_replica_lag": QuerySpec("amo_db_replica_lag_seconds", "seconds", 30 * 86400, 30),
    "db_long_queries": QuerySpec("amo_db_long_running_queries", "queries", 30 * 86400, 30),

    # API SLO metrics are low-cardinality, window-labelled observations calculated
    # from the platform route-metric rollup.
    "api_request_rate_5m": QuerySpec('amo_api_request_rate_per_second{window="5m"}', "requests_per_second", 30 * 86400, 15),
    "api_error_rate_5m": QuerySpec('amo_api_error_rate{window="5m"}', "ratio", 30 * 86400, 15),
    "api_error_rate_1h": QuerySpec('amo_api_error_rate{window="1h"}', "ratio", 30 * 86400, 30),
    "api_p95_latency_5m": QuerySpec('amo_api_p95_latency_ms{window="5m"}', "milliseconds", 30 * 86400, 15),
    "api_p99_latency_5m": QuerySpec('amo_api_p99_latency_ms{window="5m"}', "milliseconds", 30 * 86400, 15),

    # Background work / providers.
    "queue_depth": QuerySpec("amo_job_queue_depth", "jobs", 30 * 86400, 30),
    "queue_oldest_age": QuerySpec("amo_job_queue_oldest_age_seconds", "seconds", 30 * 86400, 30),
    "worker_freshness": QuerySpec("amo_worker_last_seen_age_seconds", "seconds", 30 * 86400, 30),
    "provider_failure_rate": QuerySpec('sum by(job_type) (rate(amo_job_result_total{job_status=~"FAILED|ERROR|UNSUPPORTED"}[5m]))', "failures_per_second", 7 * 86400, 30),
}

WINDOWS: dict[str, tuple[int, int]] = {
    "15m": (15 * 60, 15),
    "1h": (60 * 60, 30),
    "6h": (6 * 60 * 60, 120),
    "24h": (24 * 60 * 60, 300),
    "7d": (7 * 86400, 1800),
    "30d": (30 * 86400, 7200),
}

_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_LAST_GOOD: dict[str, dict[str, Any]] = {}
_QUERY_SEMAPHORE = threading.BoundedSemaphore(max(1, min(16, int(os.getenv("PLATFORM_OPS_QUERY_CONCURRENCY", "4") or "4"))))


def _query_url() -> str:
    return (os.getenv("OBSERVABILITY_QUERY_URL") or os.getenv("PLATFORM_OPS_PROMETHEUS_URL") or "").strip().rstrip("/")


def _cache_get(key: str, ttl: float) -> dict[str, Any] | None:
    now = time.monotonic()
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if not item or now - item[0] > ttl:
            return None
        return copy.deepcopy(item[1])


def _cache_success(key: str, payload: dict[str, Any]) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), copy.deepcopy(payload))
        _LAST_GOOD[key] = copy.deepcopy(payload)


def _stale_or_unavailable(key: str, *, error: Exception | str) -> dict[str, Any]:
    with _CACHE_LOCK:
        last = copy.deepcopy(_LAST_GOOD.get(key))
    message = str(error)[:300]
    if last is None:
        return {"available": False, "stale": True, "error": message, "series": [], "source": "prometheus"}
    last["stale"] = True
    last["error"] = message
    sampled_at = float(last.get("sampled_at_epoch") or time.time())
    last["age_seconds"] = max(0.0, round(time.time() - sampled_at, 3))
    return last


def registry_contract() -> dict[str, Any]:
    return {
        name: {
            "unit": spec.unit,
            "max_lookback_seconds": spec.max_lookback_seconds,
            "min_step_seconds": spec.min_step_seconds,
            "max_samples": spec.max_samples,
            "timeout_seconds": spec.timeout_seconds,
            "cache_ttl_seconds": spec.cache_ttl_seconds,
        }
        for name, spec in QUERY_REGISTRY.items()
    }


def _request(path: str, params: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    base = _query_url()
    if not base:
        raise RuntimeError("Observability query backend is not configured")
    acquired = _QUERY_SEMAPHORE.acquire(timeout=max(0.1, timeout))
    if not acquired:
        raise TimeoutError("Observability query concurrency limit reached")
    try:
        with urlopen(f"{base}{path}?{urlencode(params)}", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        _QUERY_SEMAPHORE.release()
    if payload.get("status") != "success":
        raise RuntimeError(str(payload.get("error") or "Prometheus query failed"))
    return payload


def _normalise_series(result: list[dict[str, Any]], *, max_samples: int) -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    remaining = max_samples
    for item in result[:100]:
        if remaining <= 0:
            break
        metric = {str(k): str(v)[:256] for k, v in (item.get("metric") or {}).items() if k not in {"authorization", "token", "password"}}
        if "values" in item:
            raw_values = item.get("values") or []
            take = min(len(raw_values), remaining)
            values = [[float(ts), float(value)] for ts, value in raw_values[-take:]]
            remaining -= len(values)
            series.append({"labels": metric, "values": values})
        else:
            value = item.get("value") or []
            if len(value) >= 2 and remaining > 0:
                series.append({"labels": metric, "value": [float(value[0]), float(value[1])]})
                remaining -= 1
    return series


def query_instant(name: str) -> dict[str, Any]:
    spec = QUERY_REGISTRY.get(name)
    if spec is None:
        raise KeyError(f"Unknown observability query: {name}")
    cache_key = f"instant:{name}"
    cached = _cache_get(cache_key, spec.cache_ttl_seconds)
    if cached is not None:
        cached["cache"] = "hit"
        return cached
    try:
        payload = _request("/api/v1/query", {"query": spec.expression}, timeout=spec.timeout_seconds)
        result = (((payload or {}).get("data") or {}).get("result") or [])
        now = time.time()
        output = {
            "query": name,
            "unit": spec.unit,
            "available": True,
            "stale": False,
            "sampled_at_epoch": now,
            "age_seconds": 0.0,
            "source": "prometheus",
            "cache": "miss",
            "series": _normalise_series(result, max_samples=spec.max_samples),
        }
        _cache_success(cache_key, output)
        return output
    except Exception as exc:
        return _stale_or_unavailable(cache_key, error=exc)


def query_range(name: str, window: str, *, end_epoch: float | None = None) -> dict[str, Any]:
    spec = QUERY_REGISTRY.get(name)
    if spec is None:
        raise KeyError(f"Unknown observability query: {name}")
    if window not in WINDOWS:
        raise ValueError(f"Unsupported range {window}; choose one of {', '.join(WINDOWS)}")
    lookback, recommended_step = WINDOWS[window]
    if lookback > spec.max_lookback_seconds:
        raise ValueError(f"{name} supports at most {spec.max_lookback_seconds} seconds of history")
    step = max(spec.min_step_seconds, recommended_step, int(math.ceil(lookback / max(1, spec.max_samples))))
    end = float(end_epoch or time.time())
    start = end - lookback
    cache_bucket = int(end // max(1, step))
    cache_key = f"range:{name}:{window}:{cache_bucket}"
    cached = _cache_get(cache_key, spec.cache_ttl_seconds)
    if cached is not None:
        cached["cache"] = "hit"
        return cached
    try:
        payload = _request(
            "/api/v1/query_range",
            {"query": spec.expression, "start": start, "end": end, "step": step},
            timeout=spec.timeout_seconds,
        )
        result = (((payload or {}).get("data") or {}).get("result") or [])
        output = {
            "query": name,
            "range": window,
            "unit": spec.unit,
            "available": True,
            "stale": False,
            "sampled_at_epoch": end,
            "age_seconds": max(0.0, time.time() - end),
            "source": "prometheus",
            "cache": "miss",
            "step_seconds": step,
            "max_samples": spec.max_samples,
            "series": _normalise_series(result, max_samples=spec.max_samples),
        }
        _cache_success(cache_key, output)
        return output
    except Exception as exc:
        return _stale_or_unavailable(cache_key, error=exc)
