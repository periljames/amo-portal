from __future__ import annotations

import base64
import copy
import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from .ops_logic import normalise_mode
from .ops_query_registry import QUERY_REGISTRY, query_instant, query_range, registry_contract
from .router import require_platform_superuser


_RATE_LOCK = threading.Lock()
_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_RATE_PER_MINUTE = max(30, min(1200, int(os.getenv("PLATFORM_OPS_RATE_LIMIT_PER_MINUTE", "240") or "240")))
_NODE_ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,128}$")


def _guard(request: Request, user=Depends(require_platform_superuser)):
    actor = str(getattr(user, "id", "platform"))
    key = f"{actor}:{request.url.path}"
    now = time.monotonic()
    with _RATE_LOCK:
        bucket = _RATE_BUCKETS[key]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= _RATE_PER_MINUTE:
            raise HTTPException(status_code=429, detail="Platform Operations rate limit exceeded")
        bucket.append(now)
    return user


router = APIRouter(prefix="/ops/v1", tags=["platform-operations-api"], dependencies=[Depends(_guard)])


def _snapshot(mode: str) -> dict[str, Any]:
    from .ops_gateway import REFRESH_SECONDS, snapshot_store

    selected = normalise_mode(mode)
    value = snapshot_store.get(selected)
    if value is None:
        raise HTTPException(status_code=503, detail={"code": "OPS_SNAPSHOT_WARMING", **snapshot_store.status()})
    output = copy.deepcopy(value)
    generated_raw = output.get("generated_at")
    age = None
    try:
        generated = datetime.fromisoformat(str(generated_raw).replace("Z", "+00:00"))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        age = max(0.0, (datetime.now(timezone.utc) - generated).total_seconds())
    except Exception:
        pass
    store_status = snapshot_store.status()
    stale = bool(store_status.get("last_error")) or (age is not None and age > max(REFRESH_SECONDS * 2.5, 30.0))
    output["freshness"] = {
        "stale": stale,
        "age_seconds": None if age is None else round(age, 3),
        "last_error": store_status.get("last_error"),
        "source": "prepared-snapshot-cache",
    }
    return output


def _filter_instance(payload: dict[str, Any], node_id: str) -> dict[str, Any]:
    if not _NODE_ID_RE.fullmatch(node_id):
        raise HTTPException(status_code=422, detail="Invalid node identifier")
    output = copy.deepcopy(payload)
    output["series"] = [row for row in payload.get("series") or [] if (row.get("labels") or {}).get("instance") == node_id]
    return output


def _metric_current(payload: dict[str, Any]) -> dict[str, Any]:
    items = []
    for row in payload.get("series") or []:
        value = row.get("value")
        items.append({"labels": row.get("labels") or {}, "value": None if not value else value[1], "timestamp": None if not value else value[0]})
    return {**{key: payload.get(key) for key in ("query", "unit", "available", "stale", "age_seconds", "source", "error") if key in payload}, "items": items}


def _encode_cursor(generation: str, offset: int) -> str:
    raw = json.dumps({"g": generation, "o": offset}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str | None) -> tuple[str | None, int]:
    if not value:
        return None, 0
    try:
        padding = "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode((value + padding).encode()).decode())
        return str(payload.get("g") or ""), max(0, int(payload.get("o") or 0))
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid tenant fleet cursor") from exc


@router.get("/bootstrap")
def bootstrap(data_mode: str = Query("REAL")):
    snapshot = _snapshot(data_mode)
    return {
        "snapshot": snapshot,
        "query_registry": registry_contract(),
        "supported_ranges": ["15m", "1h", "6h", "24h", "7d", "30d"],
        "arbitrary_promql": False,
    }


@router.get("/live")
async def live(request: Request, data_mode: str = Query("REAL")):
    mode = normalise_mode(data_mode)

    async def stream():
        last_generation = None
        while not await request.is_disconnected():
            try:
                value = _snapshot(mode)
                generation = value.get("generated_at")
                if generation != last_generation or (value.get("freshness") or {}).get("stale"):
                    last_generation = generation
                    payload = json.dumps({"type": "platform.snapshot", "snapshot": value, "created_at": generation}, default=str, separators=(",", ":"))
                    yield f"event: snapshot\ndata: {payload}\n\n"
                else:
                    yield ": keepalive\n\n"
            except HTTPException as exc:
                payload = json.dumps({"type": "platform.snapshot.unavailable", "detail": exc.detail}, default=str, separators=(",", ":"))
                yield f"event: degraded\ndata: {payload}\n\n"
            await __import__("asyncio").sleep(2)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


@router.get("/nodes")
def nodes():
    metrics = {name: _metric_current(query_instant(name)) for name in ("host_cpu_utilization", "host_memory_utilization", "host_load_1m", "host_cpu_iowait", "target_up")}
    by_node: dict[str, dict[str, Any]] = {}
    for name, payload in metrics.items():
        for item in payload.get("items") or []:
            labels = item.get("labels") or {}
            node = labels.get("instance")
            if not node:
                continue
            row = by_node.setdefault(node, {"node_id": node, "source": "prometheus"})
            row[name] = item.get("value")
            if name == "target_up":
                row.setdefault("targets", []).append({"job": labels.get("job"), "up": item.get("value")})
    return {"items": sorted(by_node.values(), key=lambda item: item["node_id"]), "metrics": metrics}


@router.get("/nodes/{node_id}")
def node_detail(node_id: str):
    payloads = {}
    for name in ("host_cpu_utilization", "host_memory_utilization", "host_memory_available", "host_swap_utilization", "host_load_1m", "host_cpu_iowait", "network_ingress", "network_egress", "network_errors", "network_drops", "filesystem_utilization", "filesystem_inode_utilization"):
        payloads[name] = _metric_current(_filter_instance(query_instant(name), node_id))
    return {"node_id": node_id, "metrics": payloads}


@router.get("/nodes/{node_id}/timeseries")
def node_timeseries(node_id: str, metric: str = Query("host_cpu_utilization"), range: str = Query("1h")):
    allowed = {
        "host_cpu_utilization", "host_cpu_iowait", "host_load_1m", "host_memory_utilization",
        "host_memory_available", "host_swap_utilization", "filesystem_utilization", "filesystem_free",
        "filesystem_inode_utilization", "network_ingress", "network_egress", "network_errors", "network_drops",
    }
    if metric not in allowed:
        raise HTTPException(status_code=422, detail="Metric is not available for node timeseries")
    try:
        return _filter_instance(query_range(metric, range), node_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/services")
def services():
    return {
        "cpu": _metric_current(query_instant("container_cpu")),
        "memory": _metric_current(query_instant("container_memory")),
        "targets": _metric_current(query_instant("target_up")),
    }


@router.get("/network")
def network():
    return {name: _metric_current(query_instant(name)) for name in ("network_ingress", "network_egress", "network_errors", "network_drops")}


@router.get("/storage")
def storage():
    return {name: _metric_current(query_instant(name)) for name in ("filesystem_utilization", "filesystem_free", "filesystem_inode_utilization")}


@router.get("/database")
def database(data_mode: str = Query("REAL")):
    snapshot = _snapshot(data_mode)
    return {
        "capacity": snapshot.get("capacity") or {},
        "checked_out": _metric_current(query_instant("db_pool_checked_out")),
        "idle": _metric_current(query_instant("db_pool_idle")),
    }


@router.get("/database/timeseries")
def database_timeseries(metric: str = Query("db_pool_checked_out"), range: str = Query("1h")):
    if metric not in {"db_pool_checked_out", "db_pool_idle"}:
        raise HTTPException(status_code=422, detail="Unsupported database timeseries metric")
    try:
        return query_range(metric, range)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/queues")
def queues(data_mode: str = Query("REAL")):
    snapshot = _snapshot(data_mode)
    return {
        "summary": {"depth": (snapshot.get("overview") or {}).get("queue_depth")},
        "depth_metric": _metric_current(query_instant("queue_depth")),
        "oldest_age_metric": _metric_current(query_instant("queue_oldest_age")),
        "worker_freshness": _metric_current(query_instant("worker_freshness")),
        "jobs": snapshot.get("jobs") or {},
    }


@router.get("/slo")
def slo(data_mode: str = Query("REAL")):
    return _snapshot(data_mode).get("slo") or {}


@router.get("/capacity")
def capacity(data_mode: str = Query("REAL")):
    return _snapshot(data_mode).get("capacity") or {}


@router.get("/routes/slow")
def slow_routes(data_mode: str = Query("REAL"), limit: int = Query(25, ge=1, le=100)):
    routes = list((_snapshot(data_mode).get("slo") or {}).get("routes") or [])
    routes.sort(key=lambda row: -(float(row.get("p95_latency_ms") or 0)))
    return {"items": routes[:limit]}


@router.get("/routes/errors")
def error_routes(data_mode: str = Query("REAL"), limit: int = Query(25, ge=1, le=100)):
    routes = list((_snapshot(data_mode).get("slo") or {}).get("routes") or [])
    routes.sort(key=lambda row: -(float(row.get("error_rate") or 0)))
    return {"items": routes[:limit]}


@router.get("/incidents")
def incidents(data_mode: str = Query("REAL")):
    return _snapshot(data_mode).get("incidents") or {"open": 0, "items": []}


@router.get("/tenant-health")
def tenant_health(
    data_mode: str = Query("REAL"),
    health: str | None = Query(None),
    active: bool | None = Query(None),
    q: str | None = Query(None),
    min_users: int | None = Query(None, ge=0),
    max_users: int | None = Query(None, ge=0),
    sort: str = Query("health"),
    limit: int = Query(100, ge=1, le=200),
    cursor: str | None = Query(None),
):
    snapshot = _snapshot(data_mode)
    generation = str(snapshot.get("generated_at") or "")
    cursor_generation, offset = _decode_cursor(cursor)
    if cursor_generation and cursor_generation != generation:
        raise HTTPException(status_code=409, detail="Tenant fleet snapshot changed; restart pagination from the first page")
    items = list((snapshot.get("fleet") or {}).get("items") or [])
    if health:
        wanted = health.strip().upper()
        items = [row for row in items if str((row.get("health") or {}).get("status") or "").upper() == wanted]
    if active is not None:
        items = [row for row in items if bool(row.get("active")) is active]
    if q:
        needle = q.strip().lower()
        items = [row for row in items if needle in " ".join(str(row.get(key) or "").lower() for key in ("name", "amo_code", "country"))]
    if min_users is not None:
        items = [row for row in items if int(row.get("users") or 0) >= min_users]
    if max_users is not None:
        items = [row for row in items if int(row.get("users") or 0) <= max_users]
    if sort == "name":
        items.sort(key=lambda row: str(row.get("name") or "").lower())
    elif sort == "traffic":
        items.sort(key=lambda row: -int(row.get("requests_window") or 0))
    elif sort == "users":
        items.sort(key=lambda row: -int(row.get("users") or 0))
    else:
        rank = {"CRITICAL": 0, "WARN": 1, "WATCH": 1, "DEGRADED": 1, "HEALTHY": 2}
        items.sort(key=lambda row: (rank.get(str((row.get("health") or {}).get("status") or ""), 3), str(row.get("name") or "").lower()))
    page = items[offset: offset + limit]
    next_offset = offset + len(page)
    return {
        "items": page,
        "total": len(items),
        "limit": limit,
        "next_cursor": _encode_cursor(generation, next_offset) if next_offset < len(items) else None,
        "snapshot_generated_at": generation,
    }


@router.get("/tenant-health/{tenant_id}")
def tenant_health_one(tenant_id: str, data_mode: str = Query("REAL")):
    snapshot = _snapshot(data_mode)
    for row in (snapshot.get("fleet") or {}).get("items") or []:
        if str(row.get("tenant_id")) == tenant_id:
            return row
    raise HTTPException(status_code=404, detail="Tenant not found in selected environment")


@router.get("/product-analytics")
def product_analytics(data_mode: str = Query("REAL")):
    return _snapshot(data_mode).get("product") or {}


@router.get("/commercial-analytics")
def commercial_analytics(data_mode: str = Query("REAL")):
    return _snapshot(data_mode).get("commercial") or {}


@router.get("/query-registry")
def query_registry():
    return {"queries": registry_contract(), "arbitrary_promql": False}
