from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable


def normalise_mode(value: str | None) -> str:
    mode = str(value or "REAL").strip().upper()
    if mode not in {"REAL", "DEMO"}:
        raise ValueError("data_mode must be REAL or DEMO")
    return mode


def safe_ratio(numerator: float | int | None, denominator: float | int | None) -> float:
    n = float(numerator or 0)
    d = float(denominator or 0)
    return 0.0 if d <= 0 else n / d


def slo_summary(
    rows: Iterable[dict[str, Any]],
    *,
    availability_target: float = 0.999,
    latency_target_ms: float = 750.0,
) -> dict[str, Any]:
    requests = 0
    server_errors = 0
    timeouts = 0
    worst_p95: float | None = None
    worst_p99: float | None = None
    by_route: dict[str, dict[str, float]] = defaultdict(
        lambda: {"requests": 0.0, "errors": 0.0, "timeouts": 0.0, "p95": 0.0, "p99": 0.0}
    )
    for row in rows:
        count = int(row.get("request_count") or 0)
        errors = int(row.get("server_error_count") or 0)
        row_timeouts = int(row.get("timeout_count") or 0)
        p95 = row.get("p95_latency_ms")
        p99 = row.get("p99_latency_ms")
        requests += count
        server_errors += errors
        timeouts += row_timeouts
        if isinstance(p95, (int, float)):
            worst_p95 = float(p95) if worst_p95 is None else max(worst_p95, float(p95))
        if isinstance(p99, (int, float)):
            worst_p99 = float(p99) if worst_p99 is None else max(worst_p99, float(p99))
        route = str(row.get("route") or "unknown")
        item = by_route[route]
        item["requests"] += count
        item["errors"] += errors
        item["timeouts"] += row_timeouts
        if isinstance(p95, (int, float)):
            item["p95"] = max(item["p95"], float(p95))
        if isinstance(p99, (int, float)):
            item["p99"] = max(item["p99"], float(p99))

    failures = server_errors + timeouts
    error_rate = safe_ratio(failures, requests)
    availability = 1.0 - error_rate
    error_budget_ratio = max(0.0, 1.0 - availability_target)
    burn_rate = safe_ratio(error_rate, error_budget_ratio) if error_budget_ratio else 0.0
    # Backwards-compatible field retained for existing clients. This is a windowed
    # burn multiple, not a month-to-date percentage of budget consumed.
    budget_consumed = burn_rate
    budget_remaining = max(0.0, 1.0 - burn_rate)

    routes = []
    for route, values in by_route.items():
        route_requests = int(values["requests"])
        route_failures = int(values["errors"] + values["timeouts"])
        route_error_rate = safe_ratio(route_failures, route_requests)
        routes.append(
            {
                "route": route,
                "requests": route_requests,
                "error_rate": route_error_rate,
                "p95_latency_ms": values["p95"] or None,
                "p99_latency_ms": values["p99"] or None,
                "latency_target_ms": latency_target_ms,
                "status": "CRITICAL"
                if route_error_rate >= 0.05
                else "WARN"
                if route_error_rate >= 0.01 or values["p95"] > latency_target_ms
                else "HEALTHY",
            }
        )
    routes.sort(
        key=lambda item: (
            item["status"] != "CRITICAL",
            item["status"] != "WARN",
            -item["error_rate"],
            -(item["p95_latency_ms"] or 0),
        )
    )

    return {
        "availability_target": availability_target,
        "error_budget_ratio": error_budget_ratio,
        "availability": availability,
        "requests": requests,
        "failures": failures,
        "error_rate": error_rate,
        "burn_rate": burn_rate,
        "error_budget_consumed": budget_consumed,
        "error_budget_remaining": budget_remaining,
        "latency_target_ms": latency_target_ms,
        "p95_latency_ms": worst_p95,
        "p99_latency_ms": worst_p99,
        "status": "CRITICAL"
        if availability < availability_target or burn_rate >= 6
        else "WARN"
        if burn_rate >= 2 or (worst_p95 or 0) > latency_target_ms
        else "HEALTHY",
        "routes": routes[:25],
    }


def capacity_summary(*, cpu_percent: float | None, memory_percent: float | None, db_active: int | None, db_max: int | None, requests_per_minute: float, queue_depth: int) -> dict[str, Any]:
    cpu = float(cpu_percent or 0)
    memory = float(memory_percent or 0)
    db_ratio = safe_ratio(db_active, db_max)
    pressure = max(cpu / 100.0, memory / 100.0, db_ratio, min(1.0, queue_depth / 1000.0))
    headroom = max(0.0, 1.0 - pressure)
    if pressure >= 0.9:
        status = "CRITICAL"
    elif pressure >= 0.75:
        status = "WARN"
    else:
        status = "HEALTHY"
    return {
        "status": status,
        "cpu_percent": cpu_percent,
        "memory_percent": memory_percent,
        "db_connections_active": db_active,
        "db_connections_max": db_max,
        "db_connection_utilisation": db_ratio,
        "requests_per_minute": requests_per_minute,
        "queue_depth": queue_depth,
        "estimated_headroom_percent": round(headroom * 100, 2),
        "forecast_note": "Headroom is a pressure indicator, not a production capacity certification. Production-equivalent load proof remains authoritative.",
    }


def tenant_health(*, active: bool, read_only: bool, api_requests: int, server_errors: int, timeouts: int, quota_percent: float | None, last_seen: datetime | None) -> dict[str, Any]:
    request_count = max(0, int(api_requests or 0))
    error_rate = safe_ratio(int(server_errors or 0) + int(timeouts or 0), request_count)
    quota = float(quota_percent or 0)
    score = 100.0
    reasons: list[str] = []
    if not active:
        score -= 60
        reasons.append("tenant inactive")
    if read_only:
        score -= 20
        reasons.append("tenant read-only")
    if error_rate >= 0.05:
        score -= 30
        reasons.append("API error rate >= 5%")
    elif error_rate >= 0.01:
        score -= 15
        reasons.append("API error rate >= 1%")
    if quota >= 95:
        score -= 25
        reasons.append("quota >= 95%")
    elif quota >= 80:
        score -= 10
        reasons.append("quota >= 80%")
    if last_seen is not None:
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - last_seen).total_seconds()
        if age > 3600:
            score -= 10
            reasons.append("no recent route telemetry")
    score = max(0.0, min(100.0, score))
    status = "CRITICAL" if score < 50 else "WARN" if score < 80 else "HEALTHY"
    return {"score": round(score, 1), "status": status, "error_rate": error_rate, "reasons": reasons}
