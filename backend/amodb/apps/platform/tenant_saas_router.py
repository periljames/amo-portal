from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db, get_read_db
from amodb.security import get_current_active_user

from . import saas_models as models
from . import saas_providers, saas_services


router = APIRouter(prefix="/tenant-saas", tags=["tenant-saas-administration"])
ACTIVE_JOB_STATUSES = {"PENDING", "RETRY", "RUNNING"}


def require_saas_admin(
    current_user: account_models.User = Depends(get_current_active_user),
) -> account_models.User:
    if getattr(current_user, "is_system_account", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System/service accounts cannot manage SaaS configuration.",
        )
    if getattr(current_user, "is_superuser", False):
        return current_user
    if getattr(current_user, "is_amo_admin", False) or current_user.role == account_models.AccountRole.AMO_ADMIN:
        if not current_user.amo_id:
            raise HTTPException(status_code=403, detail="AMO administrator is not assigned to a tenant.")
        return current_user
    raise HTTPException(status_code=403, detail="AMO administrator or platform superuser access is required.")


def _tenant_scope(user: account_models.User, requested_tenant_id: str | None) -> str | None:
    if getattr(user, "is_superuser", False):
        return requested_tenant_id or None
    if requested_tenant_id and requested_tenant_id != user.amo_id:
        raise HTTPException(status_code=403, detail="Cannot manage SaaS settings for another AMO.")
    return str(user.amo_id)


def _require_tenant(user: account_models.User, requested_tenant_id: str | None) -> str:
    tenant_id = _tenant_scope(user, requested_tenant_id)
    if not tenant_id:
        raise HTTPException(status_code=422, detail="tenant_id is required for this operation.")
    return tenant_id


def _job_payload(row: models.SaaSJob) -> dict[str, Any]:
    return {
        "id": row.id,
        "queue_name": row.queue_name,
        "job_type": row.job_type,
        "tenant_id": row.tenant_id,
        "status": row.status,
        "priority": row.priority,
        "attempt_count": row.attempt_count,
        "max_attempts": row.max_attempts,
        "available_at": row.available_at,
        "locked_by": row.locked_by,
        "lease_expires_at": row.lease_expires_at,
        "last_error": row.last_error,
        "result": row.result_json,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "finished_at": row.finished_at,
    }


def _queue_summary(db: Session, *, tenant_id: str | None) -> dict[str, Any]:
    filters = []
    if tenant_id:
        filters.append(models.SaaSJob.tenant_id == tenant_id)
    rows = (
        db.query(
            models.SaaSJob.status,
            models.SaaSJob.queue_name,
            func.count(models.SaaSJob.id),
        )
        .filter(*filters)
        .group_by(models.SaaSJob.status, models.SaaSJob.queue_name)
        .all()
    )
    counts: dict[str, int] = {}
    queues: dict[str, int] = {}
    queue_depth = 0
    for job_status, queue_name, total in rows:
        status_key = str(job_status)
        count = int(total or 0)
        counts[status_key] = counts.get(status_key, 0) + count
        if status_key in ACTIVE_JOB_STATUSES:
            queue_key = str(queue_name)
            queues[queue_key] = queues.get(queue_key, 0) + count
            queue_depth += count

    oldest_query = db.query(func.min(models.SaaSJob.created_at)).filter(
        models.SaaSJob.status.in_(ACTIVE_JOB_STATUSES),
        *filters,
    )
    return {
        "scope": "TENANT" if tenant_id else "PLATFORM",
        "tenant_id": tenant_id,
        "counts": counts,
        "queues": queues,
        "queue_depth": queue_depth,
        "oldest_active_job_at": oldest_query.scalar(),
    }


def _deployment_readiness() -> list[dict[str, Any]]:
    rows = (
        ("PLATFORM_SECRETS_KEY", "Encrypted provider credential storage", True),
        ("MQTT_BROKER_INTERNAL_URL", "Internal realtime broker connection", True),
        ("MQTT_BROKER_WS_URL", "Browser WSS realtime endpoint", True),
        ("REALTIME_BROKER_WEBHOOK_SECRET", "Broker authentication callback", True),
        ("REALTIME_GATEWAY_USERNAME", "Realtime gateway service account", True),
        ("REALTIME_GATEWAY_PASSWORD", "Realtime gateway service credential", True),
        ("CORS_ALLOWED_ORIGINS", "Production browser origin allow-list", True),
        ("DATABASE_URL", "Primary PostgreSQL connection", True),
    )
    return [
        {
            "key": key,
            "label": label,
            "required": required,
            "configured": bool(str(os.getenv(key) or "").strip()),
            "managed_in_frontend": False,
            "management": "DEPLOYMENT_ENVIRONMENT",
        }
        for key, label, required in rows
    ]


def _setup_links(tenant_id: str | None, superuser: bool) -> dict[str, Any]:
    return {
        "stripe_webhook_path": "/platform/saas/webhooks/stripe",
        "tenant_admin_path": "/maintenance/{amoCode}/admin/email-settings",
        "platform_integrations_path": "/platform/integrations" if superuser else None,
        "platform_billing_path": "/platform/billing" if superuser else None,
        "scope_tenant_id": tenant_id,
    }


def _tenant_payload(db: Session, tenant_id: str | None) -> dict[str, Any] | None:
    if not tenant_id:
        return None
    row = db.get(account_models.AMO, tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {
        "id": row.id,
        "amo_code": row.amo_code,
        "login_slug": row.login_slug,
        "name": row.name,
        "contact_email": row.contact_email,
        "country": row.country,
        "time_zone": row.time_zone,
        "is_active": row.is_active,
        "is_demo": row.is_demo,
    }


def _provider_readiness(items: list[dict[str, Any]]) -> dict[str, Any]:
    configured = [row for row in items if row.get("status") in {"CONFIGURED", "HEALTHY"}]
    unhealthy = [row for row in items if row.get("status") == "UNHEALTHY"]
    return {
        "configured": len(configured),
        "catalog_total": len(items),
        "unhealthy": len(unhealthy),
        "ready_codes": sorted(str(row.get("provider")) for row in configured),
    }


@router.get("/setup")
def setup_summary(
    tenant_id: str | None = None,
    db: Session = Depends(get_read_db),
    user: account_models.User = Depends(require_saas_admin),
):
    scope_tenant_id = _tenant_scope(user, tenant_id)
    tenant = _tenant_payload(db, scope_tenant_id)
    providers = saas_services.list_provider_credentials(db, tenant_id=scope_tenant_id)
    module_prices = saas_services.list_module_prices(
        db,
        include_inactive=False,
        limit=200,
        offset=0,
    )
    modules = saas_services.list_tenant_modules(db, tenant_id=scope_tenant_id) if scope_tenant_id else []
    job_query = db.query(models.SaaSJob)
    if scope_tenant_id:
        job_query = job_query.filter(models.SaaSJob.tenant_id == scope_tenant_id)
    elif not getattr(user, "is_superuser", False):
        job_query = job_query.filter(False)
    jobs = job_query.order_by(models.SaaSJob.created_at.desc()).limit(30).all()
    invoices: list[dict[str, Any]] = []
    if scope_tenant_id:
        invoice_rows = (
            db.query(account_models.BillingInvoice)
            .filter(account_models.BillingInvoice.amo_id == scope_tenant_id)
            .order_by(account_models.BillingInvoice.created_at.desc())
            .limit(50)
            .all()
        )
        invoices = [saas_services.invoice_payload(row) for row in invoice_rows]
    return {
        "viewer": {
            "user_id": str(user.id),
            "is_superuser": bool(getattr(user, "is_superuser", False)),
            "is_amo_admin": bool(
                getattr(user, "is_amo_admin", False)
                or user.role == account_models.AccountRole.AMO_ADMIN
            ),
        },
        "scope": "TENANT" if scope_tenant_id else "PLATFORM",
        "tenant": tenant,
        "providers": providers,
        "provider_catalog": saas_providers.provider_catalog(),
        "provider_readiness": _provider_readiness(providers),
        "module_prices": module_prices.get("items", []),
        "modules": modules,
        "invoices": invoices,
        "jobs": [_job_payload(row) for row in jobs],
        "queue": _queue_summary(db, tenant_id=scope_tenant_id),
        "deployment_readiness": _deployment_readiness(),
        "links": _setup_links(scope_tenant_id, bool(getattr(user, "is_superuser", False))),
        "permissions": {
            "configure_tenant_providers": bool(scope_tenant_id),
            "configure_platform_providers": bool(getattr(user, "is_superuser", False)),
            "manage_global_prices": bool(getattr(user, "is_superuser", False)),
            "manage_all_tenants": bool(getattr(user, "is_superuser", False)),
            "view_tenant_pipeline": bool(scope_tenant_id or getattr(user, "is_superuser", False)),
            "start_tenant_checkout": bool(scope_tenant_id),
            "fiscalize_tenant_invoice": bool(scope_tenant_id),
        },
    }


@router.get("/providers")
def providers(
    tenant_id: str | None = None,
    db: Session = Depends(get_read_db),
    user: account_models.User = Depends(require_saas_admin),
):
    scope_tenant_id = _tenant_scope(user, tenant_id)
    return {"items": saas_services.list_provider_credentials(db, tenant_id=scope_tenant_id)}


@router.put("/providers/{provider}")
def update_provider(
    provider: str,
    payload: dict[str, Any],
    tenant_id: str | None = None,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_saas_admin),
):
    scope_tenant_id = _tenant_scope(user, tenant_id)
    if not getattr(user, "is_superuser", False) and not scope_tenant_id:
        raise HTTPException(status_code=403, detail="Tenant scope is required.")
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A configuration-change reason is required.")
    try:
        return saas_services.upsert_provider_credential(
            db,
            provider=provider,
            payload=payload,
            actor_user_id=str(user.id),
            tenant_id=scope_tenant_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/providers/{provider}/health", status_code=202)
def test_provider(
    provider: str,
    tenant_id: str | None = None,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_saas_admin),
):
    scope_tenant_id = _tenant_scope(user, tenant_id)
    try:
        job = saas_services.enqueue_provider_health(
            db,
            provider=provider,
            tenant_id=scope_tenant_id,
            actor_user_id=str(user.id),
        )
        return _job_payload(job)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs")
def jobs(
    tenant_id: str | None = None,
    job_status: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_read_db),
    user: account_models.User = Depends(require_saas_admin),
):
    scope_tenant_id = _tenant_scope(user, tenant_id)
    query = db.query(models.SaaSJob)
    if scope_tenant_id:
        query = query.filter(models.SaaSJob.tenant_id == scope_tenant_id)
    elif not getattr(user, "is_superuser", False):
        query = query.filter(False)
    if job_status:
        query = query.filter(models.SaaSJob.status == job_status.strip().upper())
    total = query.count()
    rows = query.order_by(models.SaaSJob.created_at.desc()).offset(offset).limit(limit).all()
    return {"items": [_job_payload(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/modules")
def modules(
    tenant_id: str | None = None,
    db: Session = Depends(get_read_db),
    user: account_models.User = Depends(require_saas_admin),
):
    scope_tenant_id = _require_tenant(user, tenant_id)
    return {
        "items": saas_services.list_tenant_modules(db, tenant_id=scope_tenant_id),
        "prices": saas_services.list_module_prices(
            db,
            include_inactive=False,
            limit=200,
            offset=0,
        ).get("items", []),
    }


@router.get("/invoices")
def invoices(
    tenant_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_read_db),
    user: account_models.User = Depends(require_saas_admin),
):
    scope_tenant_id = _require_tenant(user, tenant_id)
    query = db.query(account_models.BillingInvoice).filter(
        account_models.BillingInvoice.amo_id == scope_tenant_id
    )
    total = query.count()
    rows = query.order_by(account_models.BillingInvoice.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "items": [saas_services.invoice_payload(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/checkout", status_code=202)
def checkout(
    payload: dict[str, Any],
    tenant_id: str | None = None,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_saas_admin),
):
    scope_tenant_id = _require_tenant(user, tenant_id)
    try:
        job = saas_services.enqueue_checkout(
            db,
            tenant_id=scope_tenant_id,
            module_price_id=str(payload.get("module_price_id") or ""),
            actor_user_id=str(user.id),
            idempotency_key=str(payload.get("idempotency_key") or ""),
        )
        return _job_payload(job)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/invoices/{invoice_id}/fiscalize", status_code=202)
def fiscalize(
    invoice_id: str,
    payload: dict[str, Any],
    tenant_id: str | None = None,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_saas_admin),
):
    scope_tenant_id = _require_tenant(user, tenant_id)
    invoice = db.get(account_models.BillingInvoice, invoice_id)
    if not invoice or invoice.amo_id != scope_tenant_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    try:
        job = saas_services.enqueue_fiscalization(
            db,
            invoice_id=invoice_id,
            provider=str(payload.get("provider") or "etims_oscu"),
            actor_user_id=str(user.id),
        )
        return _job_payload(job)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
