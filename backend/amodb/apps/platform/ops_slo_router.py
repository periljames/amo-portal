from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_read_db

from . import models
from .ops_logic import normalise_mode, slo_summary
from .router import require_platform_superuser


router = APIRouter(prefix="/ops/v1", tags=["platform-operations-slo"])

AVAILABILITY_TARGET = 0.999
LATENCY_TARGET_MS = 750.0
WINDOWS: dict[str, int] = {"5m": 5, "1h": 60, "6h": 360}


def _summary(db: Session, *, mode: str, minutes: int) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    query = (
        db.query(
            models.PlatformRouteMetric1m.route,
            func.sum(models.PlatformRouteMetric1m.request_count),
            func.sum(models.PlatformRouteMetric1m.server_error_count),
            func.sum(models.PlatformRouteMetric1m.timeout_count),
            func.max(models.PlatformRouteMetric1m.p95_latency_ms),
            func.max(models.PlatformRouteMetric1m.p99_latency_ms),
        )
        .filter(models.PlatformRouteMetric1m.bucket_start >= since)
    )
    if mode == "REAL":
        query = query.outerjoin(
            account_models.AMO,
            account_models.AMO.id == models.PlatformRouteMetric1m.tenant_id,
        ).filter(
            or_(
                models.PlatformRouteMetric1m.tenant_id.is_(None),
                account_models.AMO.is_demo.is_(False),
            )
        )
    else:
        query = query.join(
            account_models.AMO,
            account_models.AMO.id == models.PlatformRouteMetric1m.tenant_id,
        ).filter(account_models.AMO.is_demo.is_(True))

    rows = query.group_by(models.PlatformRouteMetric1m.route).limit(500).all()
    payload = [
        {
            "route": route,
            "request_count": int(request_count or 0),
            "server_error_count": int(server_error_count or 0),
            "timeout_count": int(timeout_count or 0),
            "p95_latency_ms": p95_latency_ms,
            "p99_latency_ms": p99_latency_ms,
        }
        for route, request_count, server_error_count, timeout_count, p95_latency_ms, p99_latency_ms in rows
    ]
    summary = slo_summary(
        payload,
        availability_target=AVAILABILITY_TARGET,
        latency_target_ms=LATENCY_TARGET_MS,
    )
    summary["window"] = next((name for name, value in WINDOWS.items() if value == minutes), f"{minutes}m")
    burn = float(summary.get("burn_rate") or 0.0)
    summary["budget_exhaustion_hours_at_current_burn"] = None if burn <= 0 else round(720.0 / burn, 2)
    return summary


@router.get("/slo/windows")
def slo_windows(
    data_mode: str = Query("REAL"),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    mode = normalise_mode(data_mode)
    windows = {name: _summary(db, mode=mode, minutes=minutes) for name, minutes in WINDOWS.items()}
    fast_burn = float(windows["5m"].get("burn_rate") or 0.0) >= 14.4 and float(windows["1h"].get("burn_rate") or 0.0) >= 6.0
    sustained_burn = float(windows["1h"].get("burn_rate") or 0.0) >= 2.0 and float(windows["6h"].get("burn_rate") or 0.0) >= 1.0
    return {
        "data_mode": mode,
        "availability_target": AVAILABILITY_TARGET,
        "latency_target_ms": LATENCY_TARGET_MS,
        "windows": windows,
        "burn": {
            "fast": fast_burn,
            "sustained": sustained_burn,
            "status": "CRITICAL" if fast_burn else "WARN" if sustained_burn else "HEALTHY",
            "fast_policy": {"5m": 14.4, "1h": 6.0},
            "sustained_policy": {"1h": 2.0, "6h": 1.0},
        },
        "source": "platform_route_metrics_1m",
    }
