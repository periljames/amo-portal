from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from .ops_query_registry import query_range
from .router import require_platform_superuser


router = APIRouter(prefix="/ops/v1/capacity", tags=["platform-capacity"], dependencies=[Depends(require_platform_superuser)])


def _first_series(payload: dict[str, Any]) -> list[tuple[float, float]]:
    series = payload.get("series") or []
    if not series:
        return []
    values = series[0].get("values") or []
    return [(float(ts), float(value)) for ts, value in values if value is not None]


def _linear_forecast(points: list[tuple[float, float]], *, threshold: float) -> dict[str, Any]:
    if len(points) < 3:
        return {"available": False, "reason": "At least three historical samples are required."}
    origin = points[0][0]
    xs = [(timestamp - origin) / 3600.0 for timestamp, _value in points]
    ys = [value for _timestamp, value in points]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator <= 0:
        return {"available": False, "reason": "Historical sample timestamps do not span a usable interval."}
    slope_per_hour = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
    current = ys[-1]
    days_to_threshold = None
    if slope_per_hour > 0 and current < threshold:
        hours = (threshold - current) / slope_per_hour
        if math.isfinite(hours) and hours >= 0:
            days_to_threshold = round(hours / 24.0, 2)
    return {
        "available": True,
        "current": round(current, 3),
        "average": round(y_mean, 3),
        "slope_per_hour": round(slope_per_hour, 6),
        "threshold": threshold,
        "days_to_threshold": days_to_threshold,
        "samples": len(points),
        "method": "least-squares-linear-trend",
        "certification": "planning-indicator-only",
    }


def _forecast(name: str, range_value: str, *, threshold: float) -> dict[str, Any]:
    try:
        payload = query_range(name, range_value)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not payload.get("available"):
        return {"metric": name, "range": range_value, "source": payload, "forecast": {"available": False, "reason": payload.get("error") or "Historical telemetry unavailable."}}
    return {"metric": name, "range": range_value, "source": payload, "forecast": _linear_forecast(_first_series(payload), threshold=threshold)}


@router.get("/forecast")
def capacity_forecast(range: str = Query("7d")):
    if range not in {"6h", "24h", "7d", "30d"}:
        raise HTTPException(status_code=422, detail="Capacity forecast range must be 6h, 24h, 7d or 30d")
    return {
        "range": range,
        "cpu": _forecast("host_cpu_utilization", range, threshold=85.0),
        "memory": _forecast("host_memory_utilization", range, threshold=90.0),
        "filesystem": _forecast("filesystem_utilization", range, threshold=90.0),
        "interpretation": "Forecasts are trend-based planning indicators. Production-equivalent load tests remain authoritative for scale certification.",
    }
