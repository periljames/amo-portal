from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import urlparse

from sqlalchemy import and_, func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import services as account_services
from amodb.user_id import generate_user_id

from . import diagnostics, metrics, models
from .command_registry import catalog as command_catalog, get_definition


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _safe_count(db: Session, model, *criteria) -> int:
    try:
        q = db.query(func.count(model.id))
        if criteria:
            q = q.filter(*criteria)
        return int(q.scalar() or 0)
    except Exception:
        return 0


def _safe_scalar(db: Session, sql: str, **params) -> Any:
    try:
        return db.execute(text(sql), params).scalar()
    except Exception:
        return None


def audit(db: Session, *, actor_user_id: str | None, action: str, tenant_id: str | None = None, entity_type: str | None = None, entity_id: str | None = None, reason: str | None = None, details: dict[str, Any] | None = None) -> models.PlatformAuditLog:
    row = models.PlatformAuditLog(
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        reason=reason,
        details_json=details or {},
    )
    db.add(row)
    return row


def latest_health_snapshot(db: Session) -> dict[str, Any] | None:
    row = db.query(models.PlatformHealthSnapshot).order_by(models.PlatformHealthSnapshot.created_at.desc()).first()
    if not row:
        return None
    return {
        "id": row.id,
        "status": row.status,
        "created_at": row.created_at,
        "db_ok": row.db_ok,
        "storage_ok": row.storage_ok,
        "internet_ok": row.internet_ok,
        "smtp_ok": row.smtp_ok,
        "requests_per_minute": row.requests_per_minute,
        "p95_latency_ms": row.p95_latency_ms,
        "p99_latency_ms": row.p99_latency_ms,
        "error_rate": row.error_rate,
        "details": row.details_json or {},
    }


def create_health_snapshot(db: Session, result: dict[str, Any]) -> models.PlatformHealthSnapshot:
    checks = {row.get("name"): row for row in result.get("checks") or []}
    throughput = result.get("throughput") or metrics.live_summary()
    row = models.PlatformHealthSnapshot(
        status=str(result.get("status") or "UNKNOWN"),
        db_ok=checks.get("database_select_1", {}).get("ok"),
        storage_ok=checks.get("storage_write_read_delete", {}).get("ok"),
        internet_ok=checks.get("internet_head", {}).get("ok"),
        smtp_ok=checks.get("smtp_tcp", {}).get("ok"),
        worker_ok=True,
        route_metrics_fresh=True,
        p95_latency_ms=throughput.get("p95_latency_ms"),
        p99_latency_ms=throughput.get("p99_latency_ms"),
        requests_per_minute=throughput.get("requests_per_minute"),
        error_rate=throughput.get("error_rate"),
        details_json=result,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def dashboard_summary(db: Session) -> dict[str, Any]:
    active_tenants = _safe_count(db, account_models.AMO, account_models.AMO.is_active.is_(True))
    inactive_tenants = _safe_count(db, account_models.AMO, account_models.AMO.is_active.is_(False))
    total_users = _safe_count(db, account_models.User)
    trialing = _safe_count(db, account_models.TenantLicense, account_models.TenantLicense.status == account_models.LicenseStatus.TRIALING)
    locked = _safe_count(db, account_models.TenantLicense, account_models.TenantLicense.is_read_only.is_(True))
    platform_mrr = int(_safe_scalar(db, """
        SELECT COALESCE(SUM(CASE WHEN cs.term='MONTHLY' THEN cs.amount_cents ELSE cs.amount_cents / 12 END),0)
        FROM tenant_licenses tl JOIN catalog_skus cs ON cs.id = tl.sku_id
        WHERE tl.status IN ('ACTIVE','TRIALING')
    """) or 0)
    invoice_overdue = _safe_count(db, account_models.BillingInvoice, account_models.BillingInvoice.status == account_models.InvoiceStatus.PENDING, account_models.BillingInvoice.due_at.isnot(None), account_models.BillingInvoice.due_at <= now_utc())
    support_open = _safe_count(db, models.PlatformSupportTicket, models.PlatformSupportTicket.status.in_(["OPEN", "NEW", "PENDING"]))
    security_open = _safe_count(db, models.PlatformSecurityAlert, models.PlatformSecurityAlert.status == "OPEN", models.PlatformSecurityAlert.severity.in_(["HIGH", "CRITICAL"]))
    throughput = metrics.live_summary()
    health = latest_health_snapshot(db)
    status = health.get("status") if health else "UNKNOWN"
    return {
        "active_tenants": active_tenants,
        "inactive_tenants": inactive_tenants,
        "locked_tenants": locked,
        "trialing_tenants": trialing,
        "total_users": total_users,
        "platform_mrr": platform_mrr,
        "platform_arr": platform_mrr * 12,
        "currency": "USD",
        "tenant_churn_rate": 0,
        "expansion_revenue": 0,
        "contraction_revenue": 0,
        "overdue_invoices": invoice_overdue,
        "api_requests_last_60m": throughput["requests_last_60m"],
        "api_error_rate_last_60m": throughput["error_rate"],
        "p95_latency_ms": throughput.get("p95_latency_ms"),
        "p99_latency_ms": throughput.get("p99_latency_ms"),
        "storage_used_bytes": 0,
        "storage_quota_bytes": None,
        "database_used_bytes": None,
        "database_quota_bytes": None,
        "active_support_tickets": support_open,
        "critical_security_alerts": security_open,
        "last_health_probe_at": health.get("created_at") if health else None,
        "platform_status": status,
    }


def list_tenants(db: Session, *, q: str | None = None, status_filter: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    query = db.query(account_models.AMO)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter((account_models.AMO.name.ilike(like)) | (account_models.AMO.amo_code.ilike(like)) | (account_models.AMO.login_slug.ilike(like)))
    if status_filter in {"active", "inactive"}:
        query = query.filter(account_models.AMO.is_active.is_(status_filter == "active"))
    total = query.count()
    rows = query.order_by(account_models.AMO.created_at.desc()).offset(offset).limit(min(limit, 200)).all()
    items = []
    for amo in rows:
        users = _safe_count(db, account_models.User, account_models.User.amo_id == amo.id)
        license_row = account_services.get_latest_subscription(db, amo_id=amo.id)
        sku = getattr(license_row, "catalog_sku", None) if license_row else None
        items.append({
            "id": amo.id,
            "amo_code": amo.amo_code,
            "login_slug": amo.login_slug,
            "name": amo.name,
            "country": amo.country,
            "is_active": amo.is_active,
            "status": "ACTIVE" if amo.is_active else "INACTIVE",
            "plan_code": getattr(sku, "code", None),
            "license_status": getattr(getattr(license_row, "status", None), "value", getattr(license_row, "status", None)),
            "is_read_only": bool(getattr(license_row, "is_read_only", False)) if license_row else False,
            "user_count": users,
            "created_at": amo.created_at,
            "updated_at": amo.updated_at,
        })
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def get_tenant_detail(db: Session, tenant_id: str) -> dict[str, Any]:
    amo = db.get(account_models.AMO, tenant_id)
    if not amo:
        raise ValueError("Tenant not found")
    license_row = account_services.get_latest_subscription(db, amo_id=amo.id)
    modules = db.query(account_models.ModuleSubscription).filter(account_models.ModuleSubscription.amo_id == amo.id).order_by(account_models.ModuleSubscription.module_code).all()
    invoices = db.query(account_models.BillingInvoice).filter(account_models.BillingInvoice.amo_id == amo.id).order_by(account_models.BillingInvoice.created_at.desc()).limit(20).all()
    usage = latest_resource_snapshot(db, amo.id)
    return {
        "tenant": {
            "id": amo.id,
            "amo_code": amo.amo_code,
            "login_slug": amo.login_slug,
            "name": amo.name,
            "country": amo.country,
            "contact_email": amo.contact_email,
            "contact_phone": amo.contact_phone,
            "is_active": amo.is_active,
            "created_at": amo.created_at,
            "updated_at": amo.updated_at,
        },
        "subscription": _license_payload(license_row),
        "modules": [{"id": m.id, "module_code": m.module_code, "status": getattr(m.status, "value", str(m.status)), "plan_code": m.plan_code, "effective_to": m.effective_to} for m in modules],
        "users": {"total": _safe_count(db, account_models.User, account_models.User.amo_id == amo.id), "active": _safe_count(db, account_models.User, account_models.User.amo_id == amo.id, account_models.User.is_active.is_(True))},
        "invoices": [_invoice_payload(i) for i in invoices],
        "resource_usage": usage,
    }


def _license_payload(row) -> dict[str, Any] | None:
    if not row:
        return None
    return {"id": row.id, "status": getattr(row.status, "value", str(row.status)), "term": getattr(row.term, "value", str(row.term)), "is_read_only": row.is_read_only, "current_period_end": row.current_period_end, "trial_ends_at": row.trial_ends_at, "sku_code": getattr(getattr(row, "catalog_sku", None), "code", None)}


def _invoice_payload(row) -> dict[str, Any]:
    return {"id": row.id, "amo_id": row.amo_id, "amount_cents": row.amount_cents, "currency": row.currency, "status": getattr(row.status, "value", str(row.status)), "description": row.description, "due_at": row.due_at, "paid_at": row.paid_at, "created_at": row.created_at}


def latest_resource_snapshot(db: Session, tenant_id: str) -> dict[str, Any] | None:
    row = db.query(models.PlatformTenantResourceSnapshot).filter(models.PlatformTenantResourceSnapshot.tenant_id == tenant_id).order_by(models.PlatformTenantResourceSnapshot.captured_at.desc()).first()
    if not row:
        return None
    return {"captured_at": row.captured_at, "storage_used_bytes": row.storage_used_bytes, "storage_quota_bytes": row.storage_quota_bytes, "api_requests_24h": row.api_requests_24h, "file_count": row.file_count, "quota_percent": row.quota_percent, "details": row.details_json or {}}


def create_tenant(db: Session, *, payload: dict[str, Any], actor_id: str) -> dict[str, Any]:
    required = ["name", "amo_code", "login_slug"]
    missing = [key for key in required if not str(payload.get(key) or "").strip()]
    if missing:
        raise ValueError("Missing required fields: " + ", ".join(missing))
    amo = account_models.AMO(
        name=str(payload["name"]).strip(),
        amo_code=str(payload["amo_code"]).strip().upper(),
        login_slug=str(payload["login_slug"]).strip().lower(),
        contact_email=payload.get("owner_email") or payload.get("contact_email"),
        country=payload.get("region") or payload.get("country"),
        is_active=str(payload.get("initial_status") or "ACTIVE").upper() != "INACTIVE",
    )
    db.add(amo)
    db.flush()
    audit(db, actor_user_id=actor_id, action="tenant.provisioned", tenant_id=amo.id, entity_type="tenant", entity_id=amo.id, reason=payload.get("reason"), details={"name": amo.name, "plan": payload.get("plan")})
    db.commit()
    return get_tenant_detail(db, amo.id)


def set_tenant_active(db: Session, *, tenant_id: str, active: bool, actor_id: str, reason: str) -> dict[str, Any]:
    amo = db.get(account_models.AMO, tenant_id)
    if not amo:
        raise ValueError("Tenant not found")
    amo.is_active = active
    audit(db, actor_user_id=actor_id, action="tenant.reactivated" if active else "tenant.suspended", tenant_id=tenant_id, entity_type="tenant", entity_id=tenant_id, reason=reason)
    db.commit()
    return get_tenant_detail(db, tenant_id)


def set_tenant_lock(db: Session, *, tenant_id: str, locked: bool, actor_id: str, reason: str) -> dict[str, Any]:
    lic = account_services.get_latest_subscription(db, amo_id=tenant_id)
    if not lic:
        raise ValueError("Tenant has no subscription to lock or unlock")
    lic.is_read_only = bool(locked)
    audit(db, actor_user_id=actor_id, action="tenant.locked" if locked else "tenant.unlocked", tenant_id=tenant_id, entity_type="tenant_license", entity_id=lic.id, reason=reason)
    db.commit()
    return get_tenant_detail(db, tenant_id)


def update_entitlements(db: Session, *, tenant_id: str, payload: dict[str, Any], actor_id: str) -> dict[str, Any]:
    modules = payload.get("modules") or []
    reason = payload.get("reason")
    for item in modules:
        code = str(item.get("module_code") or "").strip()
        if not code:
            continue
        row = db.query(account_models.ModuleSubscription).filter(account_models.ModuleSubscription.amo_id == tenant_id, account_models.ModuleSubscription.module_code == code).first()
        if not row:
            row = account_models.ModuleSubscription(amo_id=tenant_id, module_code=code)
            db.add(row)
        row.status = item.get("status") or row.status
        row.plan_code = item.get("plan_code") or row.plan_code
    audit(db, actor_user_id=actor_id, action="tenant.entitlements.updated", tenant_id=tenant_id, reason=reason, details={"modules": modules})
    db.commit()
    return get_tenant_detail(db, tenant_id)


def command_catalog_payload() -> list[dict[str, Any]]:
    return command_catalog()


def create_command_job(db: Session, *, payload: dict[str, Any], actor_id: str) -> models.PlatformCommandJob:
    name = str(payload.get("command_name") or "").strip().upper()
    definition = get_definition(name)
    if not definition:
        job = models.PlatformCommandJob(command_name=name or "UNKNOWN", risk_level="LOW", status="UNSUPPORTED", actor_user_id=actor_id, requested_by_user_id=actor_id, reason=payload.get("reason"), input_json=payload, output_json={"detail": "Unsupported command."})
        db.add(job); db.commit(); db.refresh(job); return job
    tenant_id = payload.get("tenant_id")
    reason = payload.get("reason")
    if definition.requires_tenant_id and not tenant_id:
        raise ValueError("This command requires tenant_id.")
    if definition.requires_reason and not str(reason or "").strip():
        raise ValueError("A reason is required for this command.")
    status = "NEEDS_APPROVAL" if definition.requires_approval and not payload.get("approved") else "PENDING"
    job = models.PlatformCommandJob(
        command_name=definition.command_name,
        risk_level=definition.risk_level,
        status=status,
        tenant_id=tenant_id,
        actor_user_id=actor_id,
        requested_by_user_id=actor_id,
        reason=reason,
        idempotency_key=payload.get("idempotency_key"),
        input_json=payload.get("input") or {},
        dry_run=bool(payload.get("dry_run", False)),
        max_retries=definition.max_retries,
        timeout_seconds=definition.timeout_seconds,
    )
    db.add(job); db.flush()
    add_job_event(db, job, status, "Command job created.")
    audit(db, actor_user_id=actor_id, action="platform.command.created", tenant_id=tenant_id, entity_type="platform_command_job", entity_id=job.id, reason=reason, details={"command_name": definition.command_name, "risk_level": definition.risk_level})
    if status == "PENDING" and definition.risk_level in {"LOW", "MEDIUM"}:
        execute_command_job(db, job, actor_id=actor_id)
    db.commit(); db.refresh(job)
    return job


def add_job_event(db: Session, job: models.PlatformCommandJob, status: str, message: str, data: dict[str, Any] | None = None) -> None:
    db.add(models.PlatformCommandJobEvent(job_id=job.id, status=status, message=message, data_json=data or {}))


def execute_command_job(db: Session, job: models.PlatformCommandJob, *, actor_id: str) -> None:
    job.status = "RUNNING"; job.started_at = now_utc(); job.attempt_count = (job.attempt_count or 0) + 1
    add_job_event(db, job, "RUNNING", "Command execution started.")
    try:
        if job.dry_run:
            result = {"dry_run": True, "detail": "Command validated but not executed."}
        elif job.command_name in {"RUN_PLATFORM_HEALTH_PROBE", "RUN_NETWORK_DIAGNOSTIC"}:
            result = diagnostics.run_health_probe(db, include_network=True)
            create_health_snapshot(db, result)
        elif job.command_name == "RUN_THROUGHPUT_PROBE":
            result = {"live": metrics.live_summary(), "flush": metrics.flush_route_metrics(db)}
        elif job.command_name in {"TENANT_REACTIVATE", "TENANT_DEACTIVATE"}:
            set_tenant_active(db, tenant_id=str(job.tenant_id), active=job.command_name == "TENANT_REACTIVATE", actor_id=actor_id, reason=job.reason or "platform command")
            result = {"tenant_id": job.tenant_id, "active": job.command_name == "TENANT_REACTIVATE"}
        elif job.command_name in {"TENANT_UNLOCK_TEMPORARILY", "TENANT_SET_READ_ONLY"}:
            requested_lock = bool((job.input_json or {}).get("read_only", job.command_name == "TENANT_SET_READ_ONLY"))
            if job.command_name == "TENANT_UNLOCK_TEMPORARILY": requested_lock = False
            set_tenant_lock(db, tenant_id=str(job.tenant_id), locked=requested_lock, actor_id=actor_id, reason=job.reason or "platform command")
            result = {"tenant_id": job.tenant_id, "read_only": requested_lock}
        elif job.command_name in {"TENANT_RECHECK_ENTITLEMENT", "TENANT_REFRESH_ACCESS_STATUS"}:
            result = account_services.get_billing_access_status(db, amo_id=str(job.tenant_id)).model_dump(mode="json")
        elif job.command_name in {"ROTATE_TENANT_API_KEY", "CLEAR_TENANT_CACHE", "INFRA_FAILOVER_DATABASE"}:
            job.status = "UNSUPPORTED"; job.error_code = "UNSUPPORTED"; job.output_json = {"detail": "No safe runtime implementation exists in this codebase yet."}; job.finished_at = now_utc(); add_job_event(db, job, "UNSUPPORTED", "Command is safely unsupported."); return
        else:
            result = {"detail": "Command accepted. No additional action required."}
        job.output_json = result; job.status = "SUCCEEDED"; job.finished_at = now_utc(); add_job_event(db, job, "SUCCEEDED", "Command completed.", result)
    except Exception as exc:
        job.status = "FAILED"; job.error_code = exc.__class__.__name__; job.error_detail = str(exc)[:2000]; job.finished_at = now_utc(); add_job_event(db, job, "FAILED", job.error_detail)


def list_jobs(db: Session, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    q = db.query(models.PlatformCommandJob).order_by(models.PlatformCommandJob.created_at.desc())
    total = q.count()
    return {"items": [job_payload(row) for row in q.offset(offset).limit(min(limit, 200)).all()], "total": total, "limit": limit, "offset": offset}


def job_payload(row: models.PlatformCommandJob) -> dict[str, Any]:
    return {"id": row.id, "command_name": row.command_name, "risk_level": row.risk_level, "status": row.status, "tenant_id": row.tenant_id, "actor_user_id": row.actor_user_id, "reason": row.reason, "output_json": row.output_json, "error_code": row.error_code, "error_detail": row.error_detail, "dry_run": row.dry_run, "attempt_count": row.attempt_count, "created_at": row.created_at, "started_at": row.started_at, "finished_at": row.finished_at}


def list_users(db: Session, *, q: str | None = None, tenant_id: str | None = None, status_filter: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    query = db.query(account_models.User)
    if q:
        like = f"%{q.strip()}%"; query = query.filter((account_models.User.email.ilike(like)) | (account_models.User.full_name.ilike(like)))
    if tenant_id: query = query.filter(account_models.User.amo_id == tenant_id)
    if status_filter == "active": query = query.filter(account_models.User.is_active.is_(True))
    if status_filter == "disabled": query = query.filter(account_models.User.is_active.is_(False))
    total = query.count()
    rows = query.order_by(account_models.User.updated_at.desc()).offset(offset).limit(min(limit, 200)).all()
    return {"items": [{"id": u.id, "email": u.email, "full_name": u.full_name, "role": getattr(u.role, "value", str(u.role)), "amo_id": u.amo_id, "tenant_name": getattr(u.amo, "name", None), "is_active": u.is_active, "is_superuser": u.is_superuser, "is_amo_admin": u.is_amo_admin, "webauthn_registered": u.webauthn_registered, "last_login_at": u.last_login_at, "locked_until": u.locked_until, "failed_login_count": u.login_attempts} for u in rows], "total": total, "limit": limit, "offset": offset}


def set_user_active(db: Session, *, user_id: str, active: bool, actor_id: str, reason: str) -> dict[str, Any]:
    user = db.get(account_models.User, user_id)
    if not user: raise ValueError("User not found")
    user.is_active = active
    if not active: user.deactivated_at = now_utc(); user.deactivated_reason = reason
    audit(db, actor_user_id=actor_id, action="user.enabled" if active else "user.disabled", tenant_id=user.amo_id, entity_type="user", entity_id=user.id, reason=reason)
    db.commit()
    return {"id": user.id, "is_active": user.is_active}


def revoke_user_sessions(db: Session, *, user_id: str, actor_id: str, reason: str) -> dict[str, Any]:
    user = db.get(account_models.User, user_id)
    if not user: raise ValueError("User not found")
    user.token_revoked_at = now_utc()
    audit(db, actor_user_id=actor_id, action="user.sessions.revoked", tenant_id=user.amo_id, entity_type="user", entity_id=user.id, reason=reason)
    db.commit()
    return {"id": user.id, "token_revoked_at": user.token_revoked_at}


def billing_summary(db: Session) -> dict[str, Any]:
    summary = dashboard_summary(db)
    return {**summary, "active_subscriptions": _safe_count(db, account_models.TenantLicense, account_models.TenantLicense.status == account_models.LicenseStatus.ACTIVE), "trial_subscriptions": _safe_count(db, account_models.TenantLicense, account_models.TenantLicense.status == account_models.LicenseStatus.TRIALING), "paid_invoices": _safe_count(db, account_models.BillingInvoice, account_models.BillingInvoice.status == account_models.InvoiceStatus.PAID), "failed_payments": 0, "grace_period_tenants": _safe_count(db, account_models.TenantLicense, account_models.TenantLicense.status == account_models.LicenseStatus.EXPIRED)}


def list_invoices(db: Session, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    q = db.query(account_models.BillingInvoice).order_by(account_models.BillingInvoice.created_at.desc())
    total = q.count()
    return {"items": [_invoice_payload(row) for row in q.offset(offset).limit(min(limit, 200)).all()], "total": total, "limit": limit, "offset": offset}


def mark_invoice_paid(db: Session, *, invoice_id: str, actor_id: str, reason: str) -> dict[str, Any]:
    row = db.get(account_models.BillingInvoice, invoice_id)
    if not row: raise ValueError("Invoice not found")
    row.status = account_models.InvoiceStatus.PAID; row.paid_at = now_utc()
    audit(db, actor_user_id=actor_id, action="billing.invoice.mark_paid", tenant_id=row.amo_id, entity_type="billing_invoice", entity_id=row.id, reason=reason)
    db.commit()
    return _invoice_payload(row)


def analytics_summary(db: Session) -> dict[str, Any]:
    throughput = metrics.live_summary()
    return {"dau": _safe_count(db, account_models.User, account_models.User.last_login_at >= now_utc() - timedelta(days=1)), "wau": _safe_count(db, account_models.User, account_models.User.last_login_at >= now_utc() - timedelta(days=7)), "mau": _safe_count(db, account_models.User, account_models.User.last_login_at >= now_utc() - timedelta(days=30)), "active_tenants": _safe_count(db, account_models.AMO, account_models.AMO.is_active.is_(True)), "api": throughput, "top_tenants": throughput.get("noisiest_tenants", []), "slow_routes": throughput.get("slowest_routes", [])}


def security_summary(db: Session) -> dict[str, Any]:
    return {"open_alerts": _safe_count(db, models.PlatformSecurityAlert, models.PlatformSecurityAlert.status == "OPEN"), "critical_alerts": _safe_count(db, models.PlatformSecurityAlert, models.PlatformSecurityAlert.status == "OPEN", models.PlatformSecurityAlert.severity == "CRITICAL"), "disabled_users": _safe_count(db, account_models.User, account_models.User.is_active.is_(False)), "locked_users": _safe_count(db, account_models.User, account_models.User.locked_until.isnot(None)), "mfa_coverage_percent": None}


def list_security_alerts(db: Session, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    q = db.query(models.PlatformSecurityAlert).order_by(models.PlatformSecurityAlert.created_at.desc())
    total = q.count()
    items = [{"id": a.id, "severity": a.severity, "status": a.status, "category": a.category, "title": a.title, "description": a.description, "tenant_id": a.tenant_id, "created_at": a.created_at} for a in q.offset(offset).limit(min(limit, 200)).all()]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def create_api_key(db: Session, *, name: str, scopes: list[str], actor_id: str) -> dict[str, Any]:
    raw = "apk_" + secrets.token_urlsafe(32)
    prefix = raw[:12]
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    row = models.PlatformAPIKey(name=name, key_prefix=prefix, key_hash=key_hash, scopes_json=scopes, created_by=actor_id)
    db.add(row); audit(db, actor_user_id=actor_id, action="integration.api_key.created", entity_type="platform_api_key", entity_id=row.id, details={"prefix": prefix}); db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name, "key_prefix": row.key_prefix, "status": row.status, "created_at": row.created_at, "raw_key": raw}


def list_api_keys(db: Session) -> list[dict[str, Any]]:
    rows = db.query(models.PlatformAPIKey).order_by(models.PlatformAPIKey.created_at.desc()).limit(100).all()
    return [{"id": r.id, "name": r.name, "key_prefix": r.key_prefix, "status": r.status, "scopes_json": r.scopes_json, "created_at": r.created_at, "last_used_at": r.last_used_at, "expires_at": r.expires_at} for r in rows]


def revoke_api_key(db: Session, *, key_id: str, actor_id: str, reason: str) -> dict[str, Any]:
    row = db.get(models.PlatformAPIKey, key_id)
    if not row: raise ValueError("API key not found")
    row.status = "REVOKED"; row.revoked_at = now_utc(); row.revoked_by = actor_id
    audit(db, actor_user_id=actor_id, action="integration.api_key.revoked", entity_type="platform_api_key", entity_id=row.id, reason=reason)
    db.commit()
    return {"id": row.id, "status": row.status}


def _validate_webhook_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("A valid absolute webhook URL is required.")
    if parsed.hostname in {"localhost", "127.0.0.1", "0.0.0.0"}:
        raise ValueError("Localhost webhook targets are not allowed from platform configuration.")


def list_webhooks(db: Session) -> list[dict[str, Any]]:
    rows = db.query(models.PlatformWebhookConfig).order_by(models.PlatformWebhookConfig.created_at.desc()).limit(100).all()
    return [{"id": r.id, "name": r.name, "event_type": r.event_type, "target_url": r.target_url, "status": r.status, "tenant_id": r.tenant_id, "is_global": r.is_global, "last_delivery_at": r.last_delivery_at, "failure_count": r.failure_count, "created_at": r.created_at} for r in rows]


def create_webhook(db: Session, *, payload: dict[str, Any], actor_id: str) -> dict[str, Any]:
    url = str(payload.get("target_url") or "")
    _validate_webhook_url(url)
    secret = payload.get("secret") or secrets.token_urlsafe(24)
    row = models.PlatformWebhookConfig(name=payload.get("name") or payload.get("event_type") or "Webhook", event_type=payload.get("event_type") or "platform.event", target_url=url, secret_hash=hashlib.sha256(str(secret).encode()).hexdigest(), status="ACTIVE", tenant_id=payload.get("tenant_id"), is_global=bool(payload.get("is_global", True)), created_by=actor_id)
    db.add(row); audit(db, actor_user_id=actor_id, action="integration.webhook.created", tenant_id=row.tenant_id, entity_type="platform_webhook_config", entity_id=row.id); db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name, "event_type": row.event_type, "target_url": row.target_url, "status": row.status, "has_secret": True}


def integration_summary(db: Session) -> dict[str, Any]:
    return {"active_api_keys": _safe_count(db, models.PlatformAPIKey, models.PlatformAPIKey.status == "ACTIVE"), "active_webhooks": _safe_count(db, models.PlatformWebhookConfig, models.PlatformWebhookConfig.status == "ACTIVE"), "failed_webhook_deliveries": _safe_count(db, models.PlatformWebhookDeliveryLog, models.PlatformWebhookDeliveryLog.success.is_(False)), "providers": list_providers(db)}


def list_providers(db: Session) -> list[dict[str, Any]]:
    rows = db.query(models.PlatformIntegrationProvider).order_by(models.PlatformIntegrationProvider.display_name).all()
    if not rows:
        return [{"provider": p, "display_name": p.title(), "status": "NOT_CONFIGURED", "redacted_configured": False} for p in ["stripe", "google_workspace", "zoom_education", "aws_s3", "sendgrid", "zendesk", "jira", "generic_webhook"]]
    return [{"id": r.id, "provider": r.provider, "display_name": r.display_name, "status": r.status, "uptime_percent": r.uptime_percent, "last_latency_ms": r.last_latency_ms, "last_checked_at": r.last_checked_at, "redacted_configured": bool(r.config_json)} for r in rows]


def infrastructure_summary(db: Session) -> dict[str, Any]:
    snap = db.query(models.PlatformInfrastructureSnapshot).order_by(models.PlatformInfrastructureSnapshot.captured_at.desc()).first()
    health = latest_health_snapshot(db)
    return {"status": (health or {}).get("status") or (snap.status if snap else "UNKNOWN"), "latest_snapshot": None if not snap else {"captured_at": snap.captured_at, "cpu_percent": snap.cpu_percent, "memory_percent": snap.memory_percent, "db_connections_active": snap.db_connections_active, "db_connections_max": snap.db_connections_max, "api_error_rate": snap.api_error_rate, "api_p95_latency_ms": snap.api_p95_latency_ms, "api_requests_per_minute": snap.api_requests_per_minute, "status": snap.status}, "feature_flags": _safe_count(db, models.PlatformFeatureFlag), "maintenance_windows": _safe_count(db, models.PlatformMaintenanceWindow, models.PlatformMaintenanceWindow.status.in_(["SCHEDULED", "ACTIVE"])), "workers": _safe_count(db, models.PlatformWorkerHeartbeat)}


def list_feature_flags(db: Session) -> list[dict[str, Any]]:
    return [{"id": f.id, "key": f.key, "name": f.name, "description": f.description, "enabled": f.enabled, "scope": f.scope, "tenant_id": f.tenant_id, "plan_code": f.plan_code, "updated_at": f.updated_at} for f in db.query(models.PlatformFeatureFlag).order_by(models.PlatformFeatureFlag.key).limit(200).all()]


def create_feature_flag(db: Session, *, payload: dict[str, Any], actor_id: str) -> dict[str, Any]:
    row = models.PlatformFeatureFlag(key=payload.get("key"), name=payload.get("name") or payload.get("key"), description=payload.get("description"), enabled=bool(payload.get("enabled", False)), scope=payload.get("scope") or "GLOBAL", tenant_id=payload.get("tenant_id"), plan_code=payload.get("plan_code"), created_by=actor_id, updated_by=actor_id)
    db.add(row); audit(db, actor_user_id=actor_id, action="infrastructure.feature_flag.created", tenant_id=row.tenant_id, entity_type="platform_feature_flag", entity_id=row.id); db.commit(); db.refresh(row)
    return {"id": row.id, "key": row.key, "enabled": row.enabled}


def support_summary(db: Session) -> dict[str, Any]:
    return {"open_tickets": _safe_count(db, models.PlatformSupportTicket, models.PlatformSupportTicket.status.in_(["OPEN", "NEW", "PENDING"])), "critical_tickets": _safe_count(db, models.PlatformSupportTicket, models.PlatformSupportTicket.priority.in_(["HIGH", "CRITICAL"])), "providers": [{"provider": p, "status": "NOT_CONFIGURED"} for p in ["zendesk", "jira", "generic_support_webhook"]]}


def list_support_tickets(db: Session, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    q = db.query(models.PlatformSupportTicket).order_by(models.PlatformSupportTicket.created_at.desc())
    total = q.count()
    items = [{"id": r.id, "external_id": r.external_id, "provider": r.provider, "tenant_id": r.tenant_id, "title": r.title, "status": r.status, "priority": r.priority, "created_at": r.created_at, "updated_at": r.updated_at} for r in q.offset(offset).limit(min(limit, 200)).all()]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def start_support_session(db: Session, *, tenant_id: str, actor_id: str, reason: str, mode: str = "READ_ONLY", minutes: int = 30) -> dict[str, Any]:
    if not reason or not reason.strip(): raise ValueError("Reason is required.")
    if minutes > 120: minutes = 120
    row = models.PlatformSupportSession(tenant_id=tenant_id, actor_user_id=actor_id, reason=reason, mode=mode if mode in {"READ_ONLY", "ASSISTED"} else "READ_ONLY", expires_at=now_utc() + timedelta(minutes=minutes))
    db.add(row); audit(db, actor_user_id=actor_id, action="support_session.started", tenant_id=tenant_id, entity_type="platform_support_session", entity_id=row.id, reason=reason, details={"mode": row.mode, "minutes": minutes}); db.commit(); db.refresh(row)
    return {"id": row.id, "tenant_id": row.tenant_id, "mode": row.mode, "status": row.status, "expires_at": row.expires_at, "reason": row.reason}


def list_support_sessions(db: Session, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.query(models.PlatformSupportSession).order_by(models.PlatformSupportSession.created_at.desc()).limit(limit).all()
    return [{"id": r.id, "tenant_id": r.tenant_id, "actor_user_id": r.actor_user_id, "reason": r.reason, "mode": r.mode, "status": r.status, "expires_at": r.expires_at, "started_at": r.started_at, "ended_at": r.ended_at} for r in rows]


def resources_summary(db: Session) -> dict[str, Any]:
    rows = db.query(models.PlatformTenantResourceSnapshot).order_by(models.PlatformTenantResourceSnapshot.captured_at.desc()).limit(100).all()
    return {"tenant_snapshots": len(rows), "storage_used_bytes": sum([r.storage_used_bytes or 0 for r in rows]), "api_requests_24h": sum([r.api_requests_24h or 0 for r in rows]), "top_tenants": [{"tenant_id": r.tenant_id, "storage_used_bytes": r.storage_used_bytes, "api_requests_24h": r.api_requests_24h, "quota_percent": r.quota_percent, "captured_at": r.captured_at} for r in rows[:20]]}


def notifications_summary(db: Session) -> dict[str, Any]:
    unread = _safe_count(db, models.PlatformNotification, models.PlatformNotification.read_at.is_(None))
    return {"unread_count": unread, "critical_count": _safe_count(db, models.PlatformNotification, models.PlatformNotification.read_at.is_(None), models.PlatformNotification.severity == "CRITICAL")}


def list_notifications(db: Session, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.query(models.PlatformNotification).order_by(models.PlatformNotification.created_at.desc()).limit(limit).all()
    return [{"id": r.id, "title": r.title, "message": r.message, "severity": r.severity, "source": r.source, "route": r.route, "read_at": r.read_at, "created_at": r.created_at} for r in rows]
