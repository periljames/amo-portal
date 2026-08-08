from __future__ import annotations

import asyncio
import json
import os
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import ReadSessionLocal, get_read_db, get_write_db
from amodb.observability import operation_span

from . import models, services
from .ops_logic import capacity_summary, normalise_mode, slo_summary, tenant_health
from .router import require_platform_superuser

router = APIRouter(prefix="/ops/v1", tags=["platform-operations-gateway"])

REFRESH_SECONDS = max(5.0, float(os.getenv("PLATFORM_OPS_REFRESH_SECONDS", "15") or "15"))
WORKER_SECONDS = max(1.0, float(os.getenv("PLATFORM_OPS_WORKER_SECONDS", "2") or "2"))
SLO_WINDOW_MINUTES = max(5, int(os.getenv("PLATFORM_OPS_SLO_WINDOW_MINUTES", "60") or "60"))
AVAILABILITY_TARGET = float(os.getenv("PLATFORM_OPS_AVAILABILITY_TARGET", "0.999") or "0.999")
LATENCY_TARGET_MS = float(os.getenv("PLATFORM_OPS_LATENCY_TARGET_MS", "750") or "750")
MAX_BULK_TENANTS = max(1, min(5000, int(os.getenv("PLATFORM_OPS_MAX_BULK_TENANTS", "1000") or "1000")))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _actor(user: Any) -> str:
    return str(getattr(user, "id", ""))


def _prometheus_query(expression: str) -> float | None:
    base = (os.getenv("PLATFORM_OPS_PROMETHEUS_URL") or "").strip().rstrip("/")
    if not base:
        return None
    try:
        query = urlencode({"query": expression})
        with urlopen(f"{base}/api/v1/query?{query}", timeout=float(os.getenv("PLATFORM_OPS_PROMETHEUS_TIMEOUT_SEC", "1.5") or "1.5")) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = (((payload or {}).get("data") or {}).get("result") or [])
        if not result:
            return None
        value = (result[0].get("value") or [None, None])[1]
        return float(value) if value is not None else None
    except Exception:
        return None


def _route_rows(db: Session, *, since: datetime, mode: str) -> list[models.PlatformRouteMetric1m]:
    query = db.query(models.PlatformRouteMetric1m).filter(models.PlatformRouteMetric1m.bucket_start >= since)
    if mode == "REAL":
        query = query.outerjoin(account_models.AMO, account_models.AMO.id == models.PlatformRouteMetric1m.tenant_id).filter(
            or_(models.PlatformRouteMetric1m.tenant_id.is_(None), account_models.AMO.is_demo.is_(False))
        )
    else:
        query = query.join(account_models.AMO, account_models.AMO.id == models.PlatformRouteMetric1m.tenant_id).filter(account_models.AMO.is_demo.is_(True))
    return query.order_by(models.PlatformRouteMetric1m.bucket_start.desc()).limit(20000).all()


def _route_payload(rows: list[models.PlatformRouteMetric1m]) -> list[dict[str, Any]]:
    return [
        {
            "route": row.route,
            "tenant_id": row.tenant_id,
            "request_count": row.request_count,
            "server_error_count": row.server_error_count,
            "timeout_count": row.timeout_count,
            "p95_latency_ms": row.p95_latency_ms,
            "bucket_start": row.bucket_start,
        }
        for row in rows
    ]


def _tenant_fleet(db: Session, *, mode: str, route_rows: list[models.PlatformRouteMetric1m]) -> list[dict[str, Any]]:
    tenant_query = db.query(account_models.AMO)
    tenant_query = tenant_query.filter(account_models.AMO.is_demo.is_(mode == "DEMO"))
    tenants = tenant_query.order_by(account_models.AMO.name.asc()).all()
    tenant_ids = [tenant.id for tenant in tenants]
    if not tenant_ids:
        return []

    user_counts = dict(
        db.query(account_models.User.amo_id, func.count(account_models.User.id))
        .filter(account_models.User.amo_id.in_(tenant_ids))
        .group_by(account_models.User.amo_id)
        .all()
    )
    active_user_counts = dict(
        db.query(account_models.User.amo_id, func.count(account_models.User.id))
        .filter(account_models.User.amo_id.in_(tenant_ids), account_models.User.is_active.is_(True))
        .group_by(account_models.User.amo_id)
        .all()
    )
    resource_rows = (
        db.query(models.PlatformTenantResourceSnapshot)
        .filter(models.PlatformTenantResourceSnapshot.tenant_id.in_(tenant_ids))
        .order_by(models.PlatformTenantResourceSnapshot.tenant_id.asc(), models.PlatformTenantResourceSnapshot.captured_at.desc())
        .all()
    )
    latest_resource: dict[str, models.PlatformTenantResourceSnapshot] = {}
    for row in resource_rows:
        latest_resource.setdefault(row.tenant_id, row)

    metric_rollup: dict[str, dict[str, Any]] = defaultdict(lambda: {"requests": 0, "errors": 0, "timeouts": 0, "last_seen": None, "p95": None})
    for row in route_rows:
        if not row.tenant_id:
            continue
        item = metric_rollup[row.tenant_id]
        item["requests"] += int(row.request_count or 0)
        item["errors"] += int(row.server_error_count or 0)
        item["timeouts"] += int(row.timeout_count or 0)
        if item["last_seen"] is None or row.bucket_start > item["last_seen"]:
            item["last_seen"] = row.bucket_start
        if row.p95_latency_ms is not None:
            item["p95"] = float(row.p95_latency_ms) if item["p95"] is None else max(item["p95"], float(row.p95_latency_ms))

    lock_rows = (
        db.query(account_models.TenantLicense.amo_id, account_models.TenantLicense.is_read_only)
        .filter(account_models.TenantLicense.amo_id.in_(tenant_ids))
        .order_by(account_models.TenantLicense.amo_id.asc(), account_models.TenantLicense.created_at.desc())
        .all()
    )
    read_only: dict[str, bool] = {}
    for tenant_id, locked in lock_rows:
        read_only.setdefault(tenant_id, bool(locked))

    fleet: list[dict[str, Any]] = []
    for tenant in tenants:
        resource = latest_resource.get(tenant.id)
        metric = metric_rollup.get(tenant.id, {})
        health = tenant_health(
            active=bool(tenant.is_active),
            read_only=bool(read_only.get(tenant.id, False)),
            api_requests=int(metric.get("requests") or 0),
            server_errors=int(metric.get("errors") or 0),
            timeouts=int(metric.get("timeouts") or 0),
            quota_percent=getattr(resource, "quota_percent", None),
            last_seen=metric.get("last_seen"),
        )
        fleet.append({
            "tenant_id": tenant.id,
            "amo_code": tenant.amo_code,
            "name": tenant.name,
            "country": tenant.country,
            "data_mode": mode,
            "active": bool(tenant.is_active),
            "read_only": bool(read_only.get(tenant.id, False)),
            "users": int(user_counts.get(tenant.id, 0)),
            "active_users": int(active_user_counts.get(tenant.id, 0)),
            "requests_window": int(metric.get("requests") or 0),
            "p95_latency_ms": metric.get("p95"),
            "quota_percent": getattr(resource, "quota_percent", None),
            "storage_used_bytes": getattr(resource, "storage_used_bytes", None),
            "last_telemetry_at": _iso(metric.get("last_seen")),
            "health": health,
        })
    fleet.sort(key=lambda item: (item["health"]["status"] != "CRITICAL", item["health"]["status"] != "WARN", item["name"] or ""))
    return fleet


def _product_analytics(db: Session, *, mode: str, route_rows: list[models.PlatformRouteMetric1m], fleet: list[dict[str, Any]]) -> dict[str, Any]:
    tenant_ids = [item["tenant_id"] for item in fleet]
    now = utcnow()
    users = db.query(account_models.User)
    if tenant_ids:
        users = users.filter(account_models.User.amo_id.in_(tenant_ids))
    else:
        users = users.filter(account_models.User.amo_id == "__none__")
    dau = users.filter(account_models.User.last_login_at >= now - timedelta(days=1)).count()
    wau = users.filter(account_models.User.last_login_at >= now - timedelta(days=7)).count()
    mau = users.filter(account_models.User.last_login_at >= now - timedelta(days=30)).count()
    routes: dict[str, int] = defaultdict(int)
    for row in route_rows:
        routes[row.route] += int(row.request_count or 0)
    top_routes = sorted(({"route": route, "requests": count} for route, count in routes.items()), key=lambda item: -item["requests"])[:20]
    return {
        "data_mode": mode,
        "dau": dau,
        "wau": wau,
        "mau": mau,
        "dau_mau_ratio": 0 if mau <= 0 else dau / mau,
        "active_tenants": sum(1 for item in fleet if item["active"]),
        "top_routes": top_routes,
        "note": "Route traffic is authoritative operational usage. Workflow funnels require explicit product events and are not inferred from clicks.",
    }


def _changes(db: Session) -> dict[str, Any]:
    windows = db.query(models.PlatformMaintenanceWindow).order_by(models.PlatformMaintenanceWindow.created_at.desc()).limit(50).all()
    audit_rows = db.query(models.PlatformAuditLog).filter(
        or_(
            models.PlatformAuditLog.action.ilike("%deploy%"),
            models.PlatformAuditLog.action.ilike("%feature%"),
            models.PlatformAuditLog.action.ilike("%maintenance%"),
            models.PlatformAuditLog.action.ilike("%command%"),
        )
    ).order_by(models.PlatformAuditLog.created_at.desc()).limit(100).all()
    return {
        "maintenance": [{"id": row.id, "title": row.title, "status": row.status, "impact_level": row.impact_level, "starts_at": _iso(row.starts_at), "ends_at": _iso(row.ends_at), "created_at": _iso(row.created_at)} for row in windows],
        "events": [{"id": row.id, "action": row.action, "tenant_id": row.tenant_id, "entity_type": row.entity_type, "entity_id": row.entity_id, "reason": row.reason, "created_at": _iso(row.created_at)} for row in audit_rows],
    }


def build_snapshot(db: Session, *, mode: str) -> dict[str, Any]:
    mode = normalise_mode(mode)
    now = utcnow()
    route_rows = _route_rows(db, since=now - timedelta(minutes=SLO_WINDOW_MINUTES), mode=mode)
    route_payload = _route_payload(route_rows)
    slo = slo_summary(route_payload, availability_target=AVAILABILITY_TARGET, latency_target_ms=LATENCY_TARGET_MS)
    fleet = _tenant_fleet(db, mode=mode, route_rows=route_rows)
    dashboard = services.dashboard_summary(db, data_mode=mode)
    billing = services.billing_summary(db, data_mode=mode)
    security = services.security_summary(db)
    infrastructure = services.infrastructure_summary(db)
    latest_infra = infrastructure.get("latest_snapshot") or {}
    cpu = _prometheus_query('100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)')
    memory = _prometheus_query("(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100")
    if cpu is None:
        cpu = latest_infra.get("cpu_percent")
    if memory is None:
        memory = latest_infra.get("memory_percent")
    requests_per_minute = float(slo.get("requests") or 0) / max(1.0, float(SLO_WINDOW_MINUTES))
    recent_jobs = services.list_jobs(db, limit=25)
    queue_depth = db.query(models.PlatformCommandJob).filter(models.PlatformCommandJob.status.in_(["PENDING", "RUNNING", "NEEDS_APPROVAL"])).count()
    capacity = capacity_summary(
        cpu_percent=cpu,
        memory_percent=memory,
        db_active=latest_infra.get("db_connections_active"),
        db_max=latest_infra.get("db_connections_max"),
        requests_per_minute=requests_per_minute,
        queue_depth=queue_depth,
    )
    incidents = db.query(models.PlatformSecurityAlert).filter(
        or_(models.PlatformSecurityAlert.category == "INCIDENT", models.PlatformSecurityAlert.severity.in_(["HIGH", "CRITICAL"]))
    ).order_by(models.PlatformSecurityAlert.created_at.desc()).limit(50).all()
    alerts = services.list_security_alerts(db, limit=25)
    product = _product_analytics(db, mode=mode, route_rows=route_rows, fleet=fleet)
    commercial = {
        "data_mode": mode,
        "mrr": dashboard.get("platform_mrr"),
        "arr": dashboard.get("platform_arr"),
        "currency": dashboard.get("currency"),
        "overdue_invoices": dashboard.get("overdue_invoices"),
        "active_subscriptions": billing.get("active_subscriptions"),
        "trial_subscriptions": billing.get("trial_subscriptions"),
        "paid_invoices": billing.get("paid_invoices"),
        "grace_period_tenants": billing.get("grace_period_tenants"),
    }
    return {
        "generated_at": now.isoformat(),
        "data_mode": mode,
        "source": "platform-ops-gateway-prepared-snapshot",
        "refresh_seconds": REFRESH_SECONDS,
        "overview": {**dashboard, "cpu_percent": cpu, "memory_percent": memory, "queue_depth": queue_depth},
        "slo": slo,
        "capacity": capacity,
        "fleet": {"total": len(fleet), "critical": sum(1 for item in fleet if item["health"]["status"] == "CRITICAL"), "warning": sum(1 for item in fleet if item["health"]["status"] == "WARN"), "items": fleet},
        "incidents": {"open": sum(1 for row in incidents if row.status == "OPEN"), "items": [{"id": row.id, "severity": row.severity, "status": row.status, "title": row.title, "description": row.description, "tenant_id": row.tenant_id, "created_at": _iso(row.created_at), "evidence": row.evidence_json or {}} for row in incidents]},
        "alerts": alerts,
        "jobs": recent_jobs,
        "product": product,
        "commercial": commercial,
        "security": security,
        "changes": _changes(db),
    }


class SnapshotStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._version = 0
        self._last_error: str | None = None

    def set(self, mode: str, snapshot: dict[str, Any]) -> None:
        with self._lock:
            self._snapshots[mode] = snapshot
            self._version += 1
            self._last_error = None

    def error(self, exc: Exception) -> None:
        with self._lock:
            self._last_error = f"{exc.__class__.__name__}: {str(exc)[:300]}"

    def get(self, mode: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._snapshots.get(mode)
            return None if value is None else dict(value)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"version": self._version, "modes": sorted(self._snapshots), "last_error": self._last_error}


snapshot_store = SnapshotStore()


def refresh_snapshots_once() -> None:
    with operation_span("platform_ops.snapshot.refresh"):
        db = ReadSessionLocal()
        try:
            for mode in ("REAL", "DEMO"):
                snapshot_store.set(mode, build_snapshot(db, mode=mode))
        except Exception as exc:
            snapshot_store.error(exc)
        finally:
            db.close()


async def snapshot_refresher(stop: asyncio.Event) -> None:
    while not stop.is_set():
        await asyncio.to_thread(refresh_snapshots_once)
        try:
            await asyncio.wait_for(stop.wait(), timeout=REFRESH_SECONDS)
        except TimeoutError:
            pass


def _execute_pending_batch() -> int:
    db = next(get_write_db())
    completed = 0
    try:
        rows = (
            db.query(models.PlatformCommandJob)
            .filter(models.PlatformCommandJob.status == "PENDING")
            .order_by(models.PlatformCommandJob.created_at.asc())
            .limit(10)
            .with_for_update(skip_locked=True)
            .all()
        )
        for row in rows:
            with operation_span("platform_ops.command.execute", command=row.command_name, tenant_id=row.tenant_id):
                services.execute_command_job(db, row, actor_id=str(row.actor_user_id or row.requested_by_user_id or ""))
                completed += 1
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
    return completed


async def command_worker(stop: asyncio.Event) -> None:
    while not stop.is_set():
        await asyncio.to_thread(_execute_pending_batch)
        try:
            await asyncio.wait_for(stop.wait(), timeout=WORKER_SECONDS)
        except TimeoutError:
            pass


@router.get("/snapshot")
def snapshot(data_mode: str = Query("REAL"), user=Depends(require_platform_superuser)):
    try:
        mode = normalise_mode(data_mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    value = snapshot_store.get(mode)
    if value is None:
        raise HTTPException(status_code=503, detail={"code": "OPS_SNAPSHOT_WARMING", **snapshot_store.status()})
    return value


@router.get("/health")
def gateway_health():
    state = snapshot_store.status()
    return {"status": "ok" if state["modes"] else "warming", **state}


@router.get("/events")
async def events(request: Request, data_mode: str = Query("REAL"), user=Depends(require_platform_superuser)):
    try:
        mode = normalise_mode(data_mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def stream():
        last_generated = None
        while not await request.is_disconnected():
            value = snapshot_store.get(mode)
            generated = (value or {}).get("generated_at")
            if value and generated != last_generated:
                last_generated = generated
                payload = json.dumps({"type": "platform.snapshot", "snapshot": value, "created_at": generated}, default=str, separators=(",", ":"))
                yield f"event: snapshot\ndata: {payload}\n\n"
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


@router.get("/tenants/{tenant_id}")
def tenant_360(tenant_id: str, data_mode: str = Query("REAL"), db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    mode = normalise_mode(data_mode)
    detail = services.get_tenant_detail(db, tenant_id)
    tenant = detail.get("tenant") or {}
    if str(tenant.get("data_mode") or "REAL").upper() != mode:
        raise HTTPException(status_code=404, detail="Tenant not found in selected data mode")
    since = utcnow() - timedelta(hours=24)
    route_rows = db.query(models.PlatformRouteMetric1m).filter(models.PlatformRouteMetric1m.tenant_id == tenant_id, models.PlatformRouteMetric1m.bucket_start >= since).order_by(models.PlatformRouteMetric1m.bucket_start.desc()).limit(2000).all()
    audits = db.query(models.PlatformAuditLog).filter(models.PlatformAuditLog.tenant_id == tenant_id).order_by(models.PlatformAuditLog.created_at.desc()).limit(100).all()
    jobs = db.query(models.PlatformCommandJob).filter(models.PlatformCommandJob.tenant_id == tenant_id).order_by(models.PlatformCommandJob.created_at.desc()).limit(50).all()
    alerts = db.query(models.PlatformSecurityAlert).filter(models.PlatformSecurityAlert.tenant_id == tenant_id).order_by(models.PlatformSecurityAlert.created_at.desc()).limit(50).all()
    return {
        **detail,
        "operations": {
            "slo_24h": slo_summary(_route_payload(route_rows), availability_target=AVAILABILITY_TARGET, latency_target_ms=LATENCY_TARGET_MS),
            "audit": [{"id": row.id, "action": row.action, "reason": row.reason, "actor_user_id": row.actor_user_id, "created_at": _iso(row.created_at), "details": row.details_json or {}} for row in audits],
            "jobs": [services.job_payload(row) for row in jobs],
            "alerts": [{"id": row.id, "severity": row.severity, "status": row.status, "title": row.title, "created_at": _iso(row.created_at)} for row in alerts],
        },
    }


@router.get("/users")
def global_users(q: str | None = None, tenant_id: str | None = None, status_filter: str | None = Query(None, alias="status"), limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.list_users(db, q=q, tenant_id=tenant_id, status_filter=status_filter, limit=limit, offset=offset)


@router.post("/incidents")
def create_incident(payload: dict[str, Any], db: Session = Depends(get_write_db), user=Depends(require_platform_superuser)):
    title = str(payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    severity = str(payload.get("severity") or "HIGH").upper()
    if severity not in {"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        raise HTTPException(status_code=422, detail="invalid severity")
    row = models.PlatformSecurityAlert(severity=severity, status="OPEN", category="INCIDENT", title=title, description=payload.get("description"), tenant_id=payload.get("tenant_id"), actor_user_id=_actor(user), evidence_json={"source": payload.get("source") or "manual", "runbook": payload.get("runbook"), "external_ref": payload.get("external_ref")})
    db.add(row)
    db.flush()
    services.audit(db, actor_user_id=_actor(user), action="incident.created", tenant_id=row.tenant_id, entity_type="platform_security_alert", entity_id=row.id, reason=payload.get("reason") or title, details={"severity": severity})
    db.commit()
    db.refresh(row)
    return {"id": row.id, "severity": row.severity, "status": row.status, "title": row.title, "created_at": row.created_at}


@router.post("/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: str, payload: dict[str, Any], db: Session = Depends(get_write_db), user=Depends(require_platform_superuser)):
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="reason is required")
    row = db.get(models.PlatformSecurityAlert, incident_id)
    if not row or row.category != "INCIDENT":
        raise HTTPException(status_code=404, detail="incident not found")
    row.status = "RESOLVED"
    row.resolved_at = utcnow()
    row.resolved_by = _actor(user)
    services.audit(db, actor_user_id=_actor(user), action="incident.resolved", tenant_id=row.tenant_id, entity_type="platform_security_alert", entity_id=row.id, reason=reason)
    db.commit()
    return {"id": row.id, "status": row.status, "resolved_at": row.resolved_at}


def _queue_job(db: Session, *, command_name: str, tenant_id: str | None, actor_id: str, reason: str, input_json: dict[str, Any], dry_run: bool, idempotency_key: str | None) -> models.PlatformCommandJob:
    if idempotency_key:
        existing = db.query(models.PlatformCommandJob).filter(models.PlatformCommandJob.idempotency_key == idempotency_key).first()
        if existing:
            return existing
    definition = services.get_definition(command_name) if hasattr(services, "get_definition") else None
    if definition is None:
        from .command_registry import get_definition
        definition = get_definition(command_name)
    if definition is None:
        raise HTTPException(status_code=422, detail=f"Unsupported command {command_name}")
    if definition.requires_tenant_id and not tenant_id:
        raise HTTPException(status_code=422, detail="tenant_id is required")
    job_status = "NEEDS_APPROVAL" if definition.requires_approval else "PENDING"
    row = models.PlatformCommandJob(command_name=definition.command_name, risk_level=definition.risk_level, status=job_status, tenant_id=tenant_id, actor_user_id=actor_id, requested_by_user_id=actor_id, reason=reason, idempotency_key=idempotency_key, input_json=input_json, dry_run=dry_run, max_retries=definition.max_retries, timeout_seconds=definition.timeout_seconds)
    db.add(row)
    db.flush()
    services.add_job_event(db, row, job_status, "Durable operations job queued.")
    services.audit(db, actor_user_id=actor_id, action="platform.command.queued", tenant_id=tenant_id, entity_type="platform_command_job", entity_id=row.id, reason=reason, details={"command_name": command_name, "risk_level": definition.risk_level, "dry_run": dry_run})
    return row


@router.post("/operations/bulk")
def bulk_operation(payload: dict[str, Any], db: Session = Depends(get_write_db), user=Depends(require_platform_superuser)):
    command_name = str(payload.get("command_name") or "").strip().upper()
    reason = str(payload.get("reason") or "").strip()
    tenant_ids = list(dict.fromkeys(str(value).strip() for value in (payload.get("tenant_ids") or []) if str(value).strip()))
    if not command_name or not reason:
        raise HTTPException(status_code=422, detail="command_name and reason are required")
    if not tenant_ids or len(tenant_ids) > MAX_BULK_TENANTS:
        raise HTTPException(status_code=422, detail=f"tenant_ids must contain 1..{MAX_BULK_TENANTS} unique tenants")
    mode = normalise_mode(payload.get("data_mode"))
    valid_ids = {row[0] for row in db.query(account_models.AMO.id).filter(account_models.AMO.id.in_(tenant_ids), account_models.AMO.is_demo.is_(mode == "DEMO")).all()}
    missing = [tenant_id for tenant_id in tenant_ids if tenant_id not in valid_ids]
    if missing:
        raise HTTPException(status_code=422, detail={"message": "One or more tenants are outside the selected data mode or do not exist", "tenant_ids": missing[:25]})
    batch_key = str(payload.get("idempotency_key") or f"bulk-{command_name}-{utcnow().strftime('%Y%m%d%H%M%S%f')}")
    jobs = []
    for tenant_id in tenant_ids:
        jobs.append(_queue_job(db, command_name=command_name, tenant_id=tenant_id, actor_id=_actor(user), reason=reason, input_json=payload.get("input") or {}, dry_run=bool(payload.get("dry_run", True)), idempotency_key=f"{batch_key}:{tenant_id}"))
    db.commit()
    return {"batch_key": batch_key, "count": len(jobs), "dry_run": bool(payload.get("dry_run", True)), "jobs": [services.job_payload(row) for row in jobs]}


@router.post("/operations/{job_id}/approve")
def approve_operation(job_id: str, payload: dict[str, Any], db: Session = Depends(get_write_db), user=Depends(require_platform_superuser)):
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="reason is required")
    row = db.get(models.PlatformCommandJob, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    if row.status != "NEEDS_APPROVAL":
        raise HTTPException(status_code=409, detail="job does not require approval")
    if row.requested_by_user_id == _actor(user):
        raise HTTPException(status_code=409, detail="high-risk operations require a second platform superuser")
    row.approved_by_user_id = _actor(user)
    row.status = "PENDING"
    services.add_job_event(db, row, "PENDING", "Operation approved and released to worker.", {"approval_reason": reason})
    services.audit(db, actor_user_id=_actor(user), action="platform.command.approved", tenant_id=row.tenant_id, entity_type="platform_command_job", entity_id=row.id, reason=reason)
    db.commit()
    return services.job_payload(row)


@router.post("/changes/maintenance")
def create_maintenance(payload: dict[str, Any], db: Session = Depends(get_write_db), user=Depends(require_platform_superuser)):
    title = str(payload.get("title") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    if not title or not reason:
        raise HTTPException(status_code=422, detail="title and reason are required")
    def parse_dt(value: Any) -> datetime | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    row = models.PlatformMaintenanceWindow(title=title, description=payload.get("description"), status="SCHEDULED", starts_at=parse_dt(payload.get("starts_at")), ends_at=parse_dt(payload.get("ends_at")), impact_level=str(payload.get("impact_level") or "LOW").upper(), created_by=_actor(user))
    db.add(row)
    db.flush()
    services.audit(db, actor_user_id=_actor(user), action="maintenance.scheduled", entity_type="platform_maintenance_window", entity_id=row.id, reason=reason, details={"impact_level": row.impact_level, "starts_at": _iso(row.starts_at), "ends_at": _iso(row.ends_at)})
    db.commit()
    return {"id": row.id, "title": row.title, "status": row.status, "starts_at": row.starts_at, "ends_at": row.ends_at, "impact_level": row.impact_level}
