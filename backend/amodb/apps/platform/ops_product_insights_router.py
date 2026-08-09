from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_read_db

from . import ops_data_models as ops_models
from .product_analytics import EVENT_TYPES
from .router import require_platform_superuser


router = APIRouter(prefix="/ops/v1/product-analytics", tags=["platform-product-insights"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _mode(value: str) -> str:
    mode = str(value or "REAL").strip().upper()
    if mode not in {"REAL", "DEMO"}:
        raise ValueError("data_mode must be REAL or DEMO")
    return mode


def _retention_payload(*, current: set[str], previous: set[str], eligible: int) -> dict[str, Any]:
    retained = current & previous
    return {
        "eligible_tenants": eligible,
        "current_active_tenants": len(current),
        "previous_active_tenants": len(previous),
        "retained_tenants": len(retained),
        "retention_rate": 0.0 if not previous else len(retained) / float(len(previous)),
        "current_activation_rate": 0.0 if eligible <= 0 else len(current) / float(eligible),
        "definition": "A tenant is retained when it has at least one approved product event in both the current and immediately preceding analysis windows.",
    }


def _cohort_payload(tenants: list[tuple[str, datetime | None]], current: set[str]) -> list[dict[str, Any]]:
    cohorts: dict[str, dict[str, int]] = defaultdict(lambda: {"tenants": 0, "active": 0})
    for tenant_id, created_at in tenants:
        if created_at is None:
            key = "unknown"
        else:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            key = created_at.astimezone(timezone.utc).strftime("%Y-%m")
        cohorts[key]["tenants"] += 1
        if tenant_id in current:
            cohorts[key]["active"] += 1
    rows = []
    for cohort, values in sorted(cohorts.items(), reverse=True):
        total = values["tenants"]
        active = values["active"]
        rows.append({
            "cohort": cohort,
            "tenants": total,
            "active_in_window": active,
            "activation_rate": 0.0 if total <= 0 else active / float(total),
        })
    return rows[:36]


@router.get("/insights")
def product_insights(
    data_mode: str = Query("REAL"),
    days: int = Query(30, ge=7, le=90),
    dormant_days: int = Query(30, ge=7, le=180),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    mode = _mode(data_mode)
    now = _utcnow()
    current_start = now - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)
    dormant_cutoff = now - timedelta(days=dormant_days)
    is_demo = mode == "DEMO"

    tenant_rows = (
        db.query(account_models.AMO.id, account_models.AMO.created_at)
        .filter(account_models.AMO.is_demo.is_(is_demo))
        .order_by(account_models.AMO.created_at.desc())
        .limit(20000)
        .all()
    )
    tenant_ids = {str(row[0]) for row in tenant_rows if row[0]}
    if not tenant_ids:
        return {
            "data_mode": mode,
            "window_days": days,
            "retention": _retention_payload(current=set(), previous=set(), eligible=0),
            "cohorts": [],
            "dormancy": {"dormant_days": dormant_days, "dormant_tenants": 0, "never_observed_tenants": 0, "active_recently": 0},
            "event_inventory": {"supported": sorted(EVENT_TYPES), "observed": []},
            "privacy": "Aggregate tenant-level cohort metrics only; no user identities or clickstream records are returned.",
        }

    activity_rows = (
        db.query(
            ops_models.PlatformProductRollup.tenant_id,
            func.max(case((ops_models.PlatformProductRollup.bucket_start >= current_start, 1), else_=0)).label("current_active"),
            func.max(case((ops_models.PlatformProductRollup.bucket_start < current_start, 1), else_=0)).label("previous_active"),
        )
        .filter(
            ops_models.PlatformProductRollup.bucket_kind == "day",
            ops_models.PlatformProductRollup.tenant_id.in_(tenant_ids),
            ops_models.PlatformProductRollup.bucket_start >= previous_start,
        )
        .group_by(ops_models.PlatformProductRollup.tenant_id)
        .limit(20000)
        .all()
    )
    current = {str(tenant_id) for tenant_id, current_active, _previous_active in activity_rows if int(current_active or 0) > 0}
    previous = {str(tenant_id) for tenant_id, _current_active, previous_active in activity_rows if int(previous_active or 0) > 0}

    last_activity_rows = (
        db.query(
            ops_models.PlatformProductRollup.tenant_id,
            func.max(ops_models.PlatformProductRollup.bucket_start),
        )
        .filter(
            ops_models.PlatformProductRollup.bucket_kind == "day",
            ops_models.PlatformProductRollup.tenant_id.in_(tenant_ids),
        )
        .group_by(ops_models.PlatformProductRollup.tenant_id)
        .limit(20000)
        .all()
    )
    last_activity: dict[str, datetime] = {}
    for tenant_id, value in last_activity_rows:
        if value is None:
            continue
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        last_activity[str(tenant_id)] = value
    never_observed = tenant_ids - set(last_activity)
    dormant = {tenant_id for tenant_id, value in last_activity.items() if value < dormant_cutoff}

    observed_rows = (
        db.query(ops_models.PlatformProductRollup.event_type, func.sum(ops_models.PlatformProductRollup.event_count))
        .filter(
            ops_models.PlatformProductRollup.bucket_kind == "day",
            ops_models.PlatformProductRollup.tenant_id.in_(tenant_ids),
            ops_models.PlatformProductRollup.bucket_start >= current_start,
        )
        .group_by(ops_models.PlatformProductRollup.event_type)
        .limit(100)
        .all()
    )
    observed = Counter({str(event_type): int(count or 0) for event_type, count in observed_rows})

    typed_tenants = [(str(tenant_id), created_at) for tenant_id, created_at in tenant_rows if tenant_id]
    return {
        "data_mode": mode,
        "window_days": days,
        "retention": _retention_payload(current=current, previous=previous, eligible=len(tenant_ids)),
        "cohorts": _cohort_payload(typed_tenants, current),
        "dormancy": {
            "dormant_days": dormant_days,
            "dormant_tenants": len(dormant | never_observed),
            "previously_observed_dormant": len(dormant),
            "never_observed_tenants": len(never_observed),
            "active_recently": len(tenant_ids - dormant - never_observed),
            "definition": "Dormant means no approved product event inside the dormancy window; never-observed tenants are reported separately and included in the dormant total.",
        },
        "event_inventory": {
            "supported": sorted(EVENT_TYPES),
            "observed": [{"event_type": key, "events": observed[key]} for key in sorted(observed)],
            "definition": "Only approved product-event taxonomy is counted; generic clicks and page views are not inferred.",
        },
        "privacy": "Aggregate tenant-level cohort metrics only; no user identities or clickstream records are returned.",
    }
