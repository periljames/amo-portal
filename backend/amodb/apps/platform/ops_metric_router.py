from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from .ops_query_registry import QUERY_REGISTRY, query_instant, query_range
from .router import require_platform_superuser


router = APIRouter(prefix="/ops/v1", tags=["platform-operations-metrics"], dependencies=[Depends(require_platform_superuser)])

HOST_METRICS = (
    "host_cpu_utilization", "host_cpu_user", "host_cpu_system", "host_cpu_iowait", "host_cpu_steal",
    "host_cpu_count", "host_load_1m", "host_load_5m", "host_load_15m", "host_procs_running", "host_procs_blocked",
    "host_memory_utilization", "host_memory_available", "host_page_cache", "host_swap_utilization", "host_swap_in", "host_swap_out", "host_oom_kills",
    "host_uptime", "host_boot_time",
)
STORAGE_METRICS = (
    "filesystem_utilization", "filesystem_free", "filesystem_inode_utilization",
    "disk_read_throughput", "disk_write_throughput", "disk_read_latency", "disk_write_latency", "disk_io_utilization",
)
NETWORK_METRICS = (
    "network_ingress", "network_egress", "network_errors", "network_drops", "tcp_established", "tcp_inuse", "tcp_timewait",
)
CONTAINER_METRICS = (
    "container_cpu", "container_memory", "container_block_read", "container_block_write", "container_uptime", "container_restarts_1h",
)
DATABASE_METRICS = (
    "db_pool_checked_out", "db_pool_idle", "db_pool_size", "db_pool_overflow", "db_pool_utilization",
    "db_active_connections", "db_max_connections", "db_connection_utilization", "db_waiting_connections", "db_lock_waiters",
    "db_deadlocks_total", "db_commits_total", "db_rollbacks_total", "db_transaction_rate", "db_size", "db_replica_lag", "db_long_queries",
)
API_METRICS = (
    "api_request_rate_5m", "api_error_rate_5m", "api_error_rate_1h", "api_p95_latency_5m", "api_p99_latency_5m",
)
WORKER_METRICS = ("queue_depth", "queue_oldest_age", "worker_freshness", "provider_failure_rate")


def _require_metric(name: str) -> str:
    if name not in QUERY_REGISTRY:
        raise HTTPException(status_code=404, detail="Unknown operations metric")
    return name


def _current(names: tuple[str, ...]) -> dict[str, Any]:
    return {name: query_instant(name) for name in names}


@router.get("/metrics/{metric_name}")
def metric(metric_name: str):
    return query_instant(_require_metric(metric_name))


@router.get("/metrics/{metric_name}/timeseries")
def metric_timeseries(metric_name: str, range: str = Query("1h")):
    name = _require_metric(metric_name)
    try:
        return query_range(name, range)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/infrastructure/summary")
def infrastructure_summary():
    return {
        "host": _current(HOST_METRICS),
        "storage": _current(STORAGE_METRICS),
        "network": _current(NETWORK_METRICS),
        "containers": _current(CONTAINER_METRICS),
        "database": _current(DATABASE_METRICS),
        "api": _current(API_METRICS),
        "workers": _current(WORKER_METRICS),
        "source": "bounded-observability-query-registry",
        "arbitrary_promql": False,
    }


@router.get("/database/health")
def database_health():
    return {
        "metrics": _current(DATABASE_METRICS),
        "source": "application-otel-and-prometheus",
        "contains_query_text": False,
    }


@router.get("/services/runtime")
def service_runtime():
    return {
        "process": _current(("process_cpu", "process_memory_rss")),
        "containers": _current(CONTAINER_METRICS),
        "workers": _current(WORKER_METRICS),
        "source": "application-otel-cadvisor-prometheus",
    }
