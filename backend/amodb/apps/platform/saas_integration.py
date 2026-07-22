from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_read_db

from . import models as platform_models
from . import saas_models
from . import saas_queue
from .router import require_platform_superuser


integration_router = APIRouter(prefix="/saas/integration-health", tags=["platform-saas-integration-health"])


TABLE_GROUPS: dict[str, tuple[str, ...]] = {
    "quality": (
        "qms_audits",
        "qms_audit_schedules",
        "qms_audit_findings",
        "quality_cars",
        "quality_car_responses",
        "quality_car_attachments",
    ),
    "training": (
        "training_records",
        "training_events",
        "training_courses",
    ),
    "shared_workflow": (
        "tasks",
        "notifications",
        "audit_events",
    ),
    "billing": (
        "module_subscriptions",
        "billing_invoices",
        "ledger_entries",
        "usage_meters",
        "saas_jobs",
        "saas_module_prices",
    ),
    "support": (
        "platform_support_tickets",
        "saas_support_ticket_details",
        "saas_support_ticket_messages",
    ),
}


ROUTE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "quality_direct": ("/quality",),
    "quality_canonical": ("/api/maintenance/{amo_code}/quality",),
    "training": ("/training",),
    "tasks": ("/tasks",),
    "notifications": ("/notifications",),
    "billing": ("/billing",),
    "platform_saas": ("/platform/saas",),
}


def _route_paths(request: Request) -> set[str]:
    return {str(getattr(route, "path", "")) for route in request.app.routes if getattr(route, "path", None)}


def _route_group_status(paths: set[str], prefixes: tuple[str, ...]) -> dict[str, Any]:
    matches = sorted(path for path in paths if any(path == prefix or path.startswith(f"{prefix}/") for prefix in prefixes))
    return {"available": bool(matches), "route_count": len(matches), "sample": matches[:10]}


def _table_status(db: Session) -> dict[str, Any]:
    inspector = inspect(db.get_bind())
    available = set(inspector.get_table_names())
    result: dict[str, Any] = {}
    for group, required in TABLE_GROUPS.items():
        missing = [table for table in required if table not in available]
        result[group] = {
            "available": not missing,
            "required": list(required),
            "missing": missing,
        }
    return result


def _pool_status(db: Session) -> dict[str, Any]:
    engine = db.get_bind()
    pool = engine.pool
    payload: dict[str, Any] = {
        "dialect": engine.dialect.name,
        "configured_pool_size": int(os.getenv("DB_POOL_SIZE", "20")),
        "configured_max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "configured_pool_timeout_seconds": int(os.getenv("DB_POOL_TIMEOUT", "5")),
    }
    for name in ("size", "checkedin", "checkedout", "overflow"):
        method = getattr(pool, name, None)
        if callable(method):
            try:
                payload[name] = method()
            except Exception:
                payload[name] = None
    if engine.dialect.name == "postgresql":
        try:
            row = db.execute(
                text(
                    """
                    SELECT
                        count(*) FILTER (WHERE datname = current_database()) AS total,
                        count(*) FILTER (WHERE datname = current_database() AND state = 'active') AS active,
                        current_setting('max_connections')::int AS max_connections
                    FROM pg_stat_activity
                    """
                )
            ).mappings().one()
            payload["database_connections"] = dict(row)
        except Exception as exc:
            payload["database_connections_error"] = str(exc)[:500]
    return payload


def _worker_status(db: Session) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
    rows = (
        db.query(platform_models.PlatformWorkerHeartbeat)
        .order_by(platform_models.PlatformWorkerHeartbeat.last_seen_at.desc())
        .limit(100)
        .all()
    )
    items = [
        {
            "worker_name": row.worker_name,
            "worker_type": row.worker_type,
            "status": row.status,
            "last_seen_at": row.last_seen_at,
            "fresh": bool(row.last_seen_at and row.last_seen_at >= cutoff),
            "metadata": row.metadata_json or {},
        }
        for row in rows
    ]
    return {
        "items": items,
        "fresh_count": sum(1 for item in items if item["fresh"]),
        "saas_worker_online": any(item["fresh"] and item["worker_type"] == "saas_queue" for item in items),
    }


def _tenant_modules(db: Session, tenant_id: str | None) -> dict[str, Any]:
    query = db.query(account_models.ModuleSubscription)
    if tenant_id:
        query = query.filter(account_models.ModuleSubscription.amo_id == tenant_id)
    rows = query.all()
    by_status: dict[str, int] = {}
    by_module: dict[str, dict[str, int]] = {}
    for row in rows:
        status = getattr(row.status, "value", str(row.status))
        by_status[status] = by_status.get(status, 0) + 1
        module = by_module.setdefault(row.module_code, {})
        module[status] = module.get(status, 0) + 1
    return {
        "tenant_id": tenant_id,
        "subscription_rows": len(rows),
        "by_status": by_status,
        "by_module": by_module,
    }


def _index_status(db: Session) -> dict[str, Any]:
    inspector = inspect(db.get_bind())
    expected = {
        "saas_jobs": {"ix_saas_jobs_claim", "ix_saas_jobs_lease", "ix_saas_jobs_tenant"},
        "module_subscriptions": {"ix_module_subscriptions_amo"},
        "usage_meters": set(),
        "qms_audit_schedules": set(),
        "training_records": set(),
    }
    output: dict[str, Any] = {}
    tables = set(inspector.get_table_names())
    for table, required in expected.items():
        if table not in tables:
            output[table] = {"available": False, "missing": sorted(required), "indexes": []}
            continue
        indexes = {str(item.get("name")) for item in inspector.get_indexes(table) if item.get("name")}
        missing = required - indexes
        output[table] = {"available": not missing, "missing": sorted(missing), "indexes": sorted(indexes)}
    return output


@integration_router.get("")
def integration_health(
    request: Request,
    tenant_id: str | None = None,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    paths = _route_paths(request)
    routes = {name: _route_group_status(paths, prefixes) for name, prefixes in ROUTE_REQUIREMENTS.items()}
    tables = _table_status(db)
    workers = _worker_status(db)
    queue = saas_queue.queue_summary(db)
    pool = _pool_status(db)
    indexes = _index_status(db)
    modules = _tenant_modules(db, tenant_id)

    blockers: list[str] = []
    warnings: list[str] = []
    for name, state in routes.items():
        if not state["available"]:
            blockers.append(f"Missing route family: {name}")
    for name, state in tables.items():
        if not state["available"]:
            blockers.append(f"Missing database table group: {name} ({', '.join(state['missing'])})")
    if not workers["saas_worker_online"]:
        warnings.append("No fresh SaaS queue worker heartbeat was detected in the last two minutes.")
    oldest_age = queue.get("oldest_pending_age_seconds")
    if isinstance(oldest_age, int) and oldest_age > 60:
        warnings.append(f"Oldest queued job has waited {oldest_age} seconds.")
    if int(pool.get("configured_pool_timeout_seconds") or 0) > 5:
        warnings.append("Database pool timeout exceeds the interactive target of five seconds.")

    training_enabled = modules["by_module"].get("training", {}).get("ENABLED", 0) + modules["by_module"].get("training", {}).get("TRIAL", 0)
    quality_enabled = modules["by_module"].get("quality", {}).get("ENABLED", 0) + modules["by_module"].get("quality", {}).get("TRIAL", 0)
    quality_training = {
        "quality_route_available": routes["quality_canonical"]["available"],
        "training_route_available": routes["training"]["available"],
        "quality_tables_available": tables["quality"]["available"],
        "training_tables_available": tables["training"]["available"],
        "quality_enabled_subscriptions": quality_enabled,
        "training_enabled_subscriptions": training_enabled,
        "calendar_contract": "/api/maintenance/{amo_code}/quality/calendar aggregates audits, CARs, training expiries and training sessions when Training is entitled.",
        "degradation_contract": "Quality audit and CAR calendar sources remain available when Training is disabled or unavailable.",
    }

    return {
        "status": "BLOCKED" if blockers else "DEGRADED" if warnings else "HEALTHY",
        "generated_at": datetime.now(timezone.utc),
        "tenant_id": tenant_id,
        "routes": routes,
        "tables": tables,
        "indexes": indexes,
        "quality_training": quality_training,
        "module_subscriptions": modules,
        "workers": workers,
        "queue": queue,
        "database_pool": pool,
        "blockers": blockers,
        "warnings": warnings,
        "capacity_position": {
            "target_tenants": 1000,
            "verified_by_this_endpoint": False,
            "required_evidence": "Run the committed k6 profile against a production-like multi-worker deployment and retain latency, error-rate, pool, queue-depth and database metrics.",
        },
    }
