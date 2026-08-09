from __future__ import annotations

import base64
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.fleet import models as fleet_models
from amodb.database import get_read_db, get_write_db

from . import models, ops_data_models, product_analytics, services
from .ops_logic import normalise_mode, slo_summary, tenant_health
from .router import require_platform_superuser


router = APIRouter(prefix="/ops/v1", tags=["platform-operations-scale"])

_FLEET_SORTS = {"health", "name", "traffic", "users", "assets", "activity"}
_USER_SORTS = {"updated", "last_login", "name", "failed_logins"}
_USER_ACTIONS = {"DISABLE", "ENABLE", "REVOKE_SESSIONS", "REQUIRE_PASSWORD_RESET"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _fingerprint(values: dict[str, Any]) -> str:
    raw = json.dumps(values, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _encode_cursor(offset: int, fingerprint: str) -> str:
    raw = json.dumps({"o": max(0, offset), "f": fingerprint}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str | None, fingerprint: str) -> int:
    if not value:
        return 0
    try:
        padding = "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode((value + padding).encode()).decode())
        if str(payload.get("f") or "") != fingerprint:
            raise ValueError("cursor query mismatch")
        return max(0, int(payload.get("o") or 0))
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid or stale pagination cursor") from exc


def _mode_tenants(db: Session, mode: str) -> list[account_models.AMO]:
    return (
        db.query(account_models.AMO)
        .filter(account_models.AMO.is_demo.is_(mode == "DEMO"))
        .order_by(account_models.AMO.name.asc(), account_models.AMO.id.asc())
        .all()
    )


def _latest_license_map(db: Session, tenant_ids: list[str]) -> dict[str, account_models.TenantLicense]:
    if not tenant_ids:
        return {}
    rows = (
        db.query(account_models.TenantLicense)
        .filter(account_models.TenantLicense.amo_id.in_(tenant_ids))
        .order_by(account_models.TenantLicense.amo_id.asc(), account_models.TenantLicense.created_at.desc())
        .all()
    )
    result: dict[str, account_models.TenantLicense] = {}
    for row in rows:
        result.setdefault(str(row.amo_id), row)
    return result


def _fleet_rows(db: Session, *, mode: str) -> list[dict[str, Any]]:
    tenants = _mode_tenants(db, mode)
    tenant_ids = [str(row.id) for row in tenants]
    if not tenant_ids:
        return []
    now = _utcnow()
    recent_since = now - timedelta(hours=24)

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
    asset_counts = dict(
        db.query(fleet_models.Aircraft.amo_id, func.count(fleet_models.Aircraft.serial_number))
        .filter(fleet_models.Aircraft.amo_id.in_(tenant_ids), fleet_models.Aircraft.is_active.is_(True))
        .group_by(fleet_models.Aircraft.amo_id)
        .all()
    )
    licenses = _latest_license_map(db, tenant_ids)

    module_rows = (
        db.query(account_models.ModuleSubscription)
        .filter(account_models.ModuleSubscription.amo_id.in_(tenant_ids))
        .all()
    )
    module_map: dict[str, list[str]] = defaultdict(list)
    for row in module_rows:
        state = (_enum(row.status) or "").upper()
        if state in {"ENABLED", "TRIAL"}:
            module_map[str(row.amo_id)].append(str(row.module_code))

    overdue_counts = dict(
        db.query(account_models.BillingInvoice.amo_id, func.count(account_models.BillingInvoice.id))
        .filter(
            account_models.BillingInvoice.amo_id.in_(tenant_ids),
            account_models.BillingInvoice.status == account_models.InvoiceStatus.PENDING,
            account_models.BillingInvoice.due_at.isnot(None),
            account_models.BillingInvoice.due_at < now,
        )
        .group_by(account_models.BillingInvoice.amo_id)
        .all()
    )
    security_counts = dict(
        db.query(models.PlatformSecurityAlert.tenant_id, func.count(models.PlatformSecurityAlert.id))
        .filter(
            models.PlatformSecurityAlert.tenant_id.in_(tenant_ids),
            models.PlatformSecurityAlert.status == "OPEN",
            models.PlatformSecurityAlert.severity.in_(["HIGH", "CRITICAL"]),
        )
        .group_by(models.PlatformSecurityAlert.tenant_id)
        .all()
    )
    support_counts = dict(
        db.query(models.PlatformSupportTicket.tenant_id, func.count(models.PlatformSupportTicket.id))
        .filter(
            models.PlatformSupportTicket.tenant_id.in_(tenant_ids),
            models.PlatformSupportTicket.status.in_(["OPEN", "NEW", "PENDING"]),
        )
        .group_by(models.PlatformSupportTicket.tenant_id)
        .all()
    )
    integration_failures = dict(
        db.query(models.PlatformWebhookConfig.tenant_id, func.coalesce(func.sum(models.PlatformWebhookConfig.failure_count), 0))
        .filter(models.PlatformWebhookConfig.tenant_id.in_(tenant_ids))
        .group_by(models.PlatformWebhookConfig.tenant_id)
        .all()
    )
    route_rows = (
        db.query(
            models.PlatformRouteMetric1m.tenant_id,
            func.coalesce(func.sum(models.PlatformRouteMetric1m.request_count), 0),
            func.coalesce(func.sum(models.PlatformRouteMetric1m.server_error_count), 0),
            func.coalesce(func.sum(models.PlatformRouteMetric1m.timeout_count), 0),
            func.max(models.PlatformRouteMetric1m.p95_latency_ms),
            func.max(models.PlatformRouteMetric1m.bucket_start),
        )
        .filter(models.PlatformRouteMetric1m.tenant_id.in_(tenant_ids), models.PlatformRouteMetric1m.bucket_start >= recent_since)
        .group_by(models.PlatformRouteMetric1m.tenant_id)
        .all()
    )
    route_map = {
        str(tenant_id): {
            "requests": int(requests or 0),
            "errors": int(errors or 0),
            "timeouts": int(timeouts or 0),
            "p95": p95,
            "last_seen": last_seen,
        }
        for tenant_id, requests, errors, timeouts, p95, last_seen in route_rows
    }
    resources = (
        db.query(models.PlatformTenantResourceSnapshot)
        .filter(models.PlatformTenantResourceSnapshot.tenant_id.in_(tenant_ids))
        .order_by(models.PlatformTenantResourceSnapshot.tenant_id.asc(), models.PlatformTenantResourceSnapshot.captured_at.desc())
        .all()
    )
    resource_map: dict[str, models.PlatformTenantResourceSnapshot] = {}
    for row in resources:
        resource_map.setdefault(str(row.tenant_id), row)

    rows: list[dict[str, Any]] = []
    for tenant in tenants:
        tenant_id = str(tenant.id)
        license_row = licenses.get(tenant_id)
        sku = getattr(license_row, "catalog_sku", None) if license_row else None
        license_status = (_enum(getattr(license_row, "status", None)) or "NONE").upper()
        read_only = bool(getattr(license_row, "is_read_only", False)) if license_row else False
        overdue = int(overdue_counts.get(tenant_id, 0) or 0)
        security_open = int(security_counts.get(tenant_id, 0) or 0)
        support_open = int(support_counts.get(tenant_id, 0) or 0)
        integration_failure_count = int(integration_failures.get(tenant_id, 0) or 0)
        route = route_map.get(tenant_id, {})
        resource = resource_map.get(tenant_id)
        health = tenant_health(
            active=bool(tenant.is_active),
            read_only=read_only,
            api_requests=int(route.get("requests") or 0),
            server_errors=int(route.get("errors") or 0),
            timeouts=int(route.get("timeouts") or 0),
            quota_percent=getattr(resource, "quota_percent", None),
            last_seen=route.get("last_seen"),
        )
        risk_penalty = (20 if overdue else 0) + (20 if security_open else 0) + (10 if integration_failure_count else 0) + (5 if support_open else 0)
        health["score"] = max(0.0, float(health.get("score") or 0.0) - risk_penalty)
        health["status"] = "CRITICAL" if health["score"] < 50 else "WARN" if health["score"] < 80 else "HEALTHY"
        lifecycle = "INACTIVE" if not tenant.is_active else "TRIAL" if license_status == "TRIALING" else "ACTIVE"
        billing_risk = "OVERDUE" if overdue else "READ_ONLY" if read_only else "WATCH" if license_status in {"PAST_DUE", "GRACE"} else "CLEAR"
        rows.append({
            "tenant_id": tenant_id,
            "amo_code": tenant.amo_code,
            "name": tenant.name,
            "country": tenant.country,
            "data_mode": mode,
            "active": bool(tenant.is_active),
            "lifecycle": lifecycle,
            "plan": getattr(sku, "code", None),
            "license_status": license_status,
            "read_only": read_only,
            "modules": sorted(set(module_map.get(tenant_id, []))),
            "users": int(user_counts.get(tenant_id, 0) or 0),
            "active_users": int(active_user_counts.get(tenant_id, 0) or 0),
            "asset_count": int(asset_counts.get(tenant_id, 0) or 0),
            "requests_24h": int(route.get("requests") or 0),
            "p95_latency_ms": route.get("p95"),
            "last_activity_at": _iso(route.get("last_seen")),
            "quota_percent": getattr(resource, "quota_percent", None),
            "storage_used_bytes": getattr(resource, "storage_used_bytes", None),
            "billing_risk": billing_risk,
            "overdue_invoices": overdue,
            "security_risk": "HIGH" if security_open else "CLEAR",
            "security_alerts": security_open,
            "integration_failure": integration_failure_count > 0,
            "integration_failure_count": integration_failure_count,
            "support_state": "OPEN" if support_open else "CLEAR",
            "support_open": support_open,
            "health": health,
        })
    return rows


def _filter_fleet(rows: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    result = rows
    q = str(filters.get("q") or "").strip().lower()
    if q:
        result = [row for row in result if q in " ".join(str(row.get(k) or "").lower() for k in ("name", "amo_code", "country", "plan"))]
    for field in ("lifecycle", "billing_risk", "security_risk", "support_state"):
        wanted = str(filters.get(field) or "").strip().upper()
        if wanted:
            result = [row for row in result if str(row.get(field) or "").upper() == wanted]
    health = str(filters.get("health") or "").strip().upper()
    if health:
        result = [row for row in result if str((row.get("health") or {}).get("status") or "").upper() == health]
    country = str(filters.get("country") or "").strip().lower()
    if country:
        result = [row for row in result if str(row.get("country") or "").lower() == country]
    plan = str(filters.get("plan") or "").strip().lower()
    if plan:
        result = [row for row in result if str(row.get("plan") or "").lower() == plan]
    module = str(filters.get("module") or "").strip().lower()
    if module:
        result = [row for row in result if module in {str(value).lower() for value in row.get("modules") or []}]
    integration = str(filters.get("integration") or "").strip().upper()
    if integration in {"FAILED", "FAILURE", "TRUE"}:
        result = [row for row in result if bool(row.get("integration_failure"))]
    elif integration in {"CLEAR", "FALSE"}:
        result = [row for row in result if not bool(row.get("integration_failure"))]
    if filters.get("active") is not None:
        result = [row for row in result if bool(row.get("active")) is bool(filters["active"])]
    for field, minimum, maximum in (
        ("users", filters.get("min_users"), filters.get("max_users")),
        ("asset_count", filters.get("min_assets"), filters.get("max_assets")),
    ):
        if minimum is not None:
            result = [row for row in result if int(row.get(field) or 0) >= int(minimum)]
        if maximum is not None:
            result = [row for row in result if int(row.get(field) or 0) <= int(maximum)]
    hours = filters.get("recent_activity_hours")
    if hours is not None:
        cutoff = _utcnow() - timedelta(hours=max(1, min(int(hours), 24 * 90)))
        result = [row for row in result if row.get("last_activity_at") and datetime.fromisoformat(str(row["last_activity_at"]).replace("Z", "+00:00")) >= cutoff]
    return result


@router.get("/tenant-fleet")
def tenant_fleet(
    data_mode: str = Query("REAL"), health: str | None = None, active: bool | None = None,
    q: str | None = None, country: str | None = None, plan: str | None = None, module: str | None = None,
    lifecycle: str | None = None, billing_risk: str | None = None, security_risk: str | None = None,
    integration: str | None = None, support_state: str | None = None,
    recent_activity_hours: int | None = Query(None, ge=1, le=2160),
    min_users: int | None = Query(None, ge=0), max_users: int | None = Query(None, ge=0),
    min_assets: int | None = Query(None, ge=0), max_assets: int | None = Query(None, ge=0),
    sort: str = Query("health"), limit: int = Query(100, ge=1, le=200), cursor: str | None = None,
    db: Session = Depends(get_read_db), user=Depends(require_platform_superuser),
):
    mode = normalise_mode(data_mode)
    if sort not in _FLEET_SORTS:
        raise HTTPException(status_code=422, detail="Unsupported fleet sort")
    filters = {"health": health, "active": active, "q": q, "country": country, "plan": plan, "module": module, "lifecycle": lifecycle, "billing_risk": billing_risk, "security_risk": security_risk, "integration": integration, "support_state": support_state, "recent_activity_hours": recent_activity_hours, "min_users": min_users, "max_users": max_users, "min_assets": min_assets, "max_assets": max_assets, "sort": sort, "data_mode": mode}
    fingerprint = _fingerprint(filters)
    offset = _decode_cursor(cursor, fingerprint)
    rows = _filter_fleet(_fleet_rows(db, mode=mode), filters)
    rank = {"CRITICAL": 0, "WARN": 1, "HEALTHY": 2}
    if sort == "name": rows.sort(key=lambda row: str(row.get("name") or "").lower())
    elif sort == "traffic": rows.sort(key=lambda row: (-int(row.get("requests_24h") or 0), str(row.get("name") or "").lower()))
    elif sort == "users": rows.sort(key=lambda row: (-int(row.get("users") or 0), str(row.get("name") or "").lower()))
    elif sort == "assets": rows.sort(key=lambda row: (-int(row.get("asset_count") or 0), str(row.get("name") or "").lower()))
    elif sort == "activity": rows.sort(key=lambda row: (row.get("last_activity_at") is None, str(row.get("last_activity_at") or "")), reverse=True)
    else: rows.sort(key=lambda row: (rank.get(str((row.get("health") or {}).get("status") or ""), 3), str(row.get("name") or "").lower()))
    page = rows[offset:offset + limit]
    next_offset = offset + len(page)
    return {"items": page, "total": len(rows), "limit": limit, "next_cursor": _encode_cursor(next_offset, fingerprint) if next_offset < len(rows) else None, "data_mode": mode, "filters": filters, "source": "server-side-fleet-rollup"}


@router.get("/tenant-360/{tenant_id}")
def tenant_360(tenant_id: str, data_mode: str = Query("REAL"), db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    mode = normalise_mode(data_mode)
    detail = services.get_tenant_detail(db, tenant_id)
    tenant = detail.get("tenant") or {}
    if str(tenant.get("data_mode") or "REAL").upper() != mode:
        raise HTTPException(status_code=404, detail="Tenant not found in selected environment")
    fleet = next((row for row in _fleet_rows(db, mode=mode) if row["tenant_id"] == tenant_id), None)
    since = _utcnow() - timedelta(hours=24)
    route_rows = db.query(models.PlatformRouteMetric1m).filter(models.PlatformRouteMetric1m.tenant_id == tenant_id, models.PlatformRouteMetric1m.bucket_start >= since).order_by(models.PlatformRouteMetric1m.bucket_start.desc()).limit(5000).all()
    performance = slo_summary([{"route": row.route, "request_count": row.request_count, "server_error_count": row.server_error_count, "timeout_count": row.timeout_count, "p95_latency_ms": row.p95_latency_ms, "p99_latency_ms": row.p99_latency_ms} for row in route_rows])
    integrations = db.query(models.PlatformWebhookConfig).filter(models.PlatformWebhookConfig.tenant_id == tenant_id).order_by(models.PlatformWebhookConfig.updated_at.desc()).limit(100).all()
    jobs = db.query(models.PlatformCommandJob).filter(models.PlatformCommandJob.tenant_id == tenant_id).order_by(models.PlatformCommandJob.created_at.desc()).limit(100).all()
    support = db.query(models.PlatformSupportTicket).filter(models.PlatformSupportTicket.tenant_id == tenant_id).order_by(models.PlatformSupportTicket.created_at.desc()).limit(100).all()
    support_sessions = db.query(models.PlatformSupportSession).filter(models.PlatformSupportSession.tenant_id == tenant_id).order_by(models.PlatformSupportSession.created_at.desc()).limit(50).all()
    security = db.query(models.PlatformSecurityAlert).filter(models.PlatformSecurityAlert.tenant_id == tenant_id).order_by(models.PlatformSecurityAlert.created_at.desc()).limit(100).all()
    audits = db.query(models.PlatformAuditLog).filter(models.PlatformAuditLog.tenant_id == tenant_id).order_by(models.PlatformAuditLog.created_at.desc()).limit(200).all()
    product = product_analytics.analytics_summary(db, data_mode=mode, days=30)
    tenant_product = [row for row in db.query(ops_data_models.PlatformProductRollup).filter(ops_data_models.PlatformProductRollup.tenant_id == tenant_id, ops_data_models.PlatformProductRollup.bucket_kind == "DAY", ops_data_models.PlatformProductRollup.bucket_start >= _utcnow() - timedelta(days=30)).order_by(ops_data_models.PlatformProductRollup.bucket_start.desc()).limit(500).all()]
    return {
        "data_mode": mode,
        "overview": detail.get("tenant"),
        "health": fleet,
        "usage": {"resource": detail.get("resource_usage"), "product_events_30d": sum(int(row.event_count or 0) for row in tenant_product), "platform_product_context": {"window_days": product.get("window_days"), "privacy": product.get("privacy")}},
        "users": detail.get("users"),
        "modules": detail.get("modules"),
        "subscription": detail.get("subscription"),
        "billing": {"access_status": detail.get("access_status"), "invoices": detail.get("invoices")},
        "performance": performance,
        "integrations": [{"id": row.id, "name": row.name, "event_type": row.event_type, "status": row.status, "last_delivery_at": _iso(row.last_delivery_at), "failure_count": row.failure_count} for row in integrations],
        "jobs": [services.job_payload(row) for row in jobs],
        "support": {"tickets": [{"id": row.id, "title": row.title, "status": row.status, "priority": row.priority, "created_at": _iso(row.created_at)} for row in support], "sessions": [{"id": row.id, "mode": row.mode, "status": row.status, "reason": row.reason, "started_at": _iso(row.started_at), "expires_at": _iso(row.expires_at)} for row in support_sessions]},
        "security": [{"id": row.id, "severity": row.severity, "status": row.status, "category": row.category, "title": row.title, "created_at": _iso(row.created_at)} for row in security],
        "audit": [{"id": row.id, "action": row.action, "entity_type": row.entity_type, "entity_id": row.entity_id, "reason": row.reason, "actor_user_id": row.actor_user_id, "created_at": _iso(row.created_at)} for row in audits],
        "changes": [row for row in [{"id": audit.id, "action": audit.action, "reason": audit.reason, "created_at": _iso(audit.created_at)} for audit in audits if any(token in str(audit.action).lower() for token in ("change", "feature", "maintenance", "command", "subscription", "tenant."))]][:100],
    }


@router.get("/users/v2")
def users_v2(
    data_mode: str = Query("REAL"), q: str | None = None, role: str | None = None, status_filter: str | None = Query(None, alias="status"),
    mfa: bool | None = None, min_failed_logins: int | None = Query(None, ge=0), platform_only: bool | None = None,
    last_login_after: datetime | None = None, last_login_before: datetime | None = None,
    sort: str = Query("updated"), limit: int = Query(100, ge=1, le=200), cursor: str | None = None,
    db: Session = Depends(get_read_db), user=Depends(require_platform_superuser),
):
    mode = normalise_mode(data_mode)
    if sort not in _USER_SORTS:
        raise HTTPException(status_code=422, detail="Unsupported user sort")
    values = {"data_mode": mode, "q": q, "role": role, "status": status_filter, "mfa": mfa, "min_failed_logins": min_failed_logins, "platform_only": platform_only, "last_login_after": last_login_after, "last_login_before": last_login_before, "sort": sort}
    fingerprint = _fingerprint(values)
    offset = _decode_cursor(cursor, fingerprint)
    query = db.query(account_models.User).join(account_models.AMO, account_models.AMO.id == account_models.User.amo_id).filter(account_models.AMO.is_demo.is_(mode == "DEMO"))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(account_models.User.email.ilike(like), account_models.User.full_name.ilike(like), account_models.User.staff_code.ilike(like)))
    if role:
        query = query.filter(account_models.User.role == role.strip().upper())
    if status_filter == "active": query = query.filter(account_models.User.is_active.is_(True))
    if status_filter == "disabled": query = query.filter(account_models.User.is_active.is_(False))
    if mfa is not None: query = query.filter(account_models.User.webauthn_registered.is_(mfa))
    if min_failed_logins is not None: query = query.filter(account_models.User.login_attempts >= min_failed_logins)
    if platform_only is True: query = query.filter(account_models.User.is_superuser.is_(True))
    if platform_only is False: query = query.filter(account_models.User.is_superuser.is_(False))
    if last_login_after: query = query.filter(account_models.User.last_login_at >= last_login_after)
    if last_login_before: query = query.filter(account_models.User.last_login_at <= last_login_before)
    total = query.count()
    if sort == "last_login": query = query.order_by(account_models.User.last_login_at.desc().nullslast(), account_models.User.id.asc())
    elif sort == "name": query = query.order_by(account_models.User.full_name.asc(), account_models.User.id.asc())
    elif sort == "failed_logins": query = query.order_by(account_models.User.login_attempts.desc(), account_models.User.id.asc())
    else: query = query.order_by(account_models.User.updated_at.desc(), account_models.User.id.asc())
    rows = query.offset(offset).limit(limit).all()
    items = [{"id": row.id, "email": row.email, "full_name": row.full_name, "staff_code": row.staff_code, "role": _enum(row.role), "tenant_id": row.amo_id, "tenant_name": getattr(row.amo, "name", None), "data_mode": mode, "is_active": bool(row.is_active), "is_superuser": bool(row.is_superuser), "mfa_registered": bool(row.webauthn_registered), "failed_login_count": int(row.login_attempts or 0), "locked_until": _iso(row.locked_until), "last_login_at": _iso(row.last_login_at), "token_revoked_at": _iso(row.token_revoked_at), "must_change_password": bool(row.must_change_password), "updated_at": _iso(row.updated_at)} for row in rows]
    next_offset = offset + len(items)
    return {"items": items, "total": total, "limit": limit, "next_cursor": _encode_cursor(next_offset, fingerprint) if next_offset < total else None, "data_mode": mode, "filters": values}


@router.post("/users/v2/bulk")
def users_bulk(payload: dict[str, Any], db: Session = Depends(get_write_db), user=Depends(require_platform_superuser)):
    action = str(payload.get("action") or "").strip().upper()
    reason = str(payload.get("reason") or "").strip()
    user_ids = list(dict.fromkeys(str(value).strip() for value in payload.get("user_ids") or [] if str(value).strip()))
    if action not in _USER_ACTIONS or not reason or not user_ids or len(user_ids) > 200:
        raise HTTPException(status_code=422, detail="Valid action, reason, and 1..200 user_ids are required")
    rows = db.query(account_models.User).filter(account_models.User.id.in_(user_ids)).all()
    found = {str(row.id): row for row in rows}
    results = []
    now = _utcnow()
    actor_id = str(getattr(user, "id", ""))
    for user_id in user_ids:
        row = found.get(user_id)
        if row is None:
            results.append({"user_id": user_id, "status": "SKIPPED", "detail": "not found"})
            continue
        if str(row.id) == actor_id and action in {"DISABLE", "REVOKE_SESSIONS"}:
            results.append({"user_id": user_id, "status": "SKIPPED", "detail": "self-targeting blocked"})
            continue
        if action == "DISABLE": row.is_active = False; row.deactivated_at = now; row.deactivated_reason = reason
        elif action == "ENABLE": row.is_active = True; row.deactivated_at = None; row.deactivated_reason = None
        elif action == "REVOKE_SESSIONS": row.token_revoked_at = now
        elif action == "REQUIRE_PASSWORD_RESET": row.must_change_password = True; row.token_revoked_at = now
        services.audit(db, actor_user_id=actor_id, action=f"platform.user.{action.lower()}", tenant_id=row.amo_id, entity_type="user", entity_id=row.id, reason=reason, details={"bulk": True})
        results.append({"user_id": user_id, "status": "SUCCEEDED"})
    db.commit()
    return {"action": action, "requested": len(user_ids), "succeeded": sum(1 for row in results if row["status"] == "SUCCEEDED"), "skipped": sum(1 for row in results if row["status"] == "SKIPPED"), "results": results}


def _monthly_amount(license_row: account_models.TenantLicense) -> tuple[str, int, str]:
    sku = getattr(license_row, "catalog_sku", None)
    if sku is None:
        return "UNKNOWN", 0, "UNKNOWN"
    currency = str(getattr(sku, "currency", "UNKNOWN") or "UNKNOWN").upper()
    amount = int(getattr(sku, "amount_cents", 0) or 0)
    term = (_enum(getattr(sku, "term", None)) or _enum(getattr(license_row, "term", None)) or "MONTHLY").upper()
    monthly = amount if term == "MONTHLY" else round(amount / 12) if term in {"ANNUAL", "YEARLY"} else amount
    return currency, int(monthly), str(getattr(sku, "code", "UNKNOWN") or "UNKNOWN")


@router.get("/commercial")
def commercial(data_mode: str = Query("REAL"), db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    mode = normalise_mode(data_mode)
    tenants = _mode_tenants(db, mode)
    tenant_ids = [str(row.id) for row in tenants]
    licenses = _latest_license_map(db, tenant_ids)
    currencies: dict[str, dict[str, Any]] = defaultdict(lambda: {"mrr_cents": 0, "arr_cents": 0, "active_subscriptions": 0, "trial_subscriptions": 0, "overdue_invoice_cents": 0, "overdue_invoices": 0})
    plans: dict[tuple[str, str], dict[str, Any]] = {}
    tenant_revenue = []
    renewals = {"30d": [], "60d": [], "90d": []}
    now = _utcnow()
    for tenant in tenants:
        row = licenses.get(str(tenant.id))
        if row is None:
            continue
        state = (_enum(row.status) or "UNKNOWN").upper()
        currency, mrr, plan = _monthly_amount(row)
        if state in {"ACTIVE", "TRIALING"}:
            currencies[currency]["mrr_cents"] += mrr
            currencies[currency]["arr_cents"] += mrr * 12
            currencies[currency]["active_subscriptions"] += 1 if state == "ACTIVE" else 0
            currencies[currency]["trial_subscriptions"] += 1 if state == "TRIALING" else 0
            key = (currency, plan)
            item = plans.setdefault(key, {"currency": currency, "plan": plan, "mrr_cents": 0, "tenants": 0})
            item["mrr_cents"] += mrr; item["tenants"] += 1
            tenant_revenue.append({"tenant_id": tenant.id, "tenant": tenant.name, "currency": currency, "plan": plan, "mrr_cents": mrr, "status": state})
        end = getattr(row, "current_period_end", None)
        if end:
            if end.tzinfo is None: end = end.replace(tzinfo=timezone.utc)
            days = (end - now).total_seconds() / 86400
            for label, ceiling in (("30d", 30), ("60d", 60), ("90d", 90)):
                if 0 <= days <= ceiling:
                    renewals[label].append({"tenant_id": tenant.id, "tenant": tenant.name, "currency": currency, "plan": plan, "renews_at": _iso(end), "mrr_cents": mrr})
                    break
    if tenant_ids:
        invoice_rows = db.query(account_models.BillingInvoice).filter(account_models.BillingInvoice.amo_id.in_(tenant_ids), account_models.BillingInvoice.status == account_models.InvoiceStatus.PENDING, account_models.BillingInvoice.due_at.isnot(None), account_models.BillingInvoice.due_at < now).all()
        for invoice in invoice_rows:
            currency = str(invoice.currency or "UNKNOWN").upper()
            currencies[currency]["overdue_invoices"] += 1
            currencies[currency]["overdue_invoice_cents"] += int(invoice.amount_cents or 0)
    canceled_30d = [row for row in licenses.values() if getattr(row, "canceled_at", None) and (now - (row.canceled_at if row.canceled_at.tzinfo else row.canceled_at.replace(tzinfo=timezone.utc))) <= timedelta(days=30)]
    tenant_revenue.sort(key=lambda row: (row["currency"], -row["mrr_cents"]))
    return {
        "data_mode": mode,
        "currencies": [{"currency": currency, **values} for currency, values in sorted(currencies.items())],
        "plans": sorted(plans.values(), key=lambda row: (row["currency"], -row["mrr_cents"])),
        "tenants": tenant_revenue[:500],
        "renewal_pipeline": renewals,
        "churn": {"cancellations_30d": len(canceled_30d), "definition": "Count of tenants whose latest subscription has canceled_at in the last 30 days. A churn rate is not emitted because the schema does not preserve a defensible period-start denominator."},
        "expansion_contraction": {"available": False, "reason": "Authoritative historical subscription-price transitions are not retained in a form that supports defensible expansion/contraction attribution."},
        "module_revenue": {"available": False, "reason": "Module subscriptions do not carry independent authoritative price/currency fields; module adoption is reported separately rather than inventing revenue."},
        "currency_rule": "No cross-currency total is produced. Every monetary aggregate remains grouped by invoice/SKU currency.",
    }
