from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db, get_read_db
from amodb.security import get_current_active_user

from . import models as platform_models
from . import saas_models as models
from . import saas_queue, saas_services
from .router import require_platform_superuser


platform_saas_router = APIRouter(prefix="/saas", tags=["platform-saas-control-plane"])
webhook_router = APIRouter(prefix="/saas/webhooks", tags=["platform-saas-webhooks"])
support_router = APIRouter(prefix="/saas/support", tags=["portal-support"])


def _actor_id(user: account_models.User) -> str:
    return str(user.id)


def _bad(exc: Exception, default_code: int = 400) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    raise HTTPException(status_code=default_code, detail=str(exc)) from exc


def _job_payload(row: models.SaaSJob) -> dict[str, Any]:
    return {
        "id": row.id,
        "queue_name": row.queue_name,
        "job_type": row.job_type,
        "tenant_id": row.tenant_id,
        "status": row.status,
        "priority": row.priority,
        "result": row.result_json,
        "idempotency_key": row.idempotency_key,
        "correlation_id": row.correlation_id,
        "attempt_count": row.attempt_count,
        "max_attempts": row.max_attempts,
        "available_at": row.available_at,
        "locked_at": row.locked_at,
        "locked_by": row.locked_by,
        "lease_expires_at": row.lease_expires_at,
        "last_error": row.last_error,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "finished_at": row.finished_at,
    }


def _ticket_access(user: account_models.User, ticket: platform_models.PlatformSupportTicket) -> None:
    if getattr(user, "is_superuser", False):
        return
    if not user.amo_id or ticket.tenant_id != user.amo_id:
        raise HTTPException(status_code=404, detail="Support ticket not found")


@platform_saas_router.get("/capabilities")
def capabilities(
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    return saas_services.platform_capabilities(db)


@platform_saas_router.get("/providers")
def providers(
    tenant_id: str | None = None,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    return {"items": saas_services.list_provider_credentials(db, tenant_id=tenant_id)}


@platform_saas_router.put("/providers/{provider}")
def provider_update(
    provider: str,
    payload: dict[str, Any],
    tenant_id: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return saas_services.upsert_provider_credential(
            db,
            provider=provider,
            payload=payload,
            actor_user_id=_actor_id(user),
            tenant_id=tenant_id,
        )
    except Exception as exc:
        _bad(exc)


@platform_saas_router.post("/providers/{provider}/health", status_code=status.HTTP_202_ACCEPTED)
def provider_health(
    provider: str,
    payload: dict[str, Any] | None = None,
    tenant_id: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        job = saas_services.enqueue_provider_health(
            db,
            provider=provider,
            tenant_id=tenant_id,
            actor_user_id=_actor_id(user),
        )
        return _job_payload(job)
    except Exception as exc:
        _bad(exc)


@platform_saas_router.get("/jobs")
def jobs(
    queue_name: str | None = None,
    job_type: str | None = None,
    job_status: str | None = Query(None, alias="status"),
    tenant_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    query = db.query(models.SaaSJob)
    if queue_name:
        query = query.filter(models.SaaSJob.queue_name == queue_name.strip().lower())
    if job_type:
        query = query.filter(models.SaaSJob.job_type == job_type.strip().upper())
    if job_status:
        query = query.filter(models.SaaSJob.status == job_status.strip().upper())
    if tenant_id:
        query = query.filter(models.SaaSJob.tenant_id == tenant_id)
    total = query.count()
    rows = (
        query.order_by(models.SaaSJob.created_at.desc(), models.SaaSJob.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"items": [_job_payload(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@platform_saas_router.get("/jobs/summary")
def jobs_summary(
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    return saas_queue.queue_summary(db)


@platform_saas_router.get("/jobs/{job_id}")
def job_detail(
    job_id: str,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    row = db.get(models.SaaSJob, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    payload = _job_payload(row)
    events = (
        db.query(models.SaaSJobEvent)
        .filter(models.SaaSJobEvent.job_id == job_id)
        .order_by(models.SaaSJobEvent.created_at.asc())
        .all()
    )
    payload["events"] = [
        {"id": event.id, "status": event.status, "message": event.message, "data": event.data_json or {}, "created_at": event.created_at}
        for event in events
    ]
    return payload


@platform_saas_router.post("/jobs/{job_id}/retry")
def job_retry(
    job_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    row = db.get(models.SaaSJob, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        return _job_payload(saas_queue.retry_job(db, row, actor_user_id=_actor_id(user)))
    except Exception as exc:
        _bad(exc)


@platform_saas_router.post("/jobs/{job_id}/cancel")
def job_cancel(
    job_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    row = db.get(models.SaaSJob, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A cancellation reason is required")
    try:
        return _job_payload(saas_queue.cancel_job(db, row, reason=reason))
    except Exception as exc:
        _bad(exc)


@platform_saas_router.get("/module-prices")
def module_prices(
    module_code: str | None = None,
    include_inactive: bool = True,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return saas_services.list_module_prices(
            db,
            module_code=module_code,
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        _bad(exc)


@platform_saas_router.post("/module-prices", status_code=status.HTTP_201_CREATED)
def module_price_create(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return saas_services.upsert_module_price(db, payload=payload, actor_user_id=_actor_id(user))
    except Exception as exc:
        _bad(exc)


@platform_saas_router.patch("/module-prices/{price_id}")
def module_price_update(
    price_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return saas_services.upsert_module_price(
            db,
            payload=payload,
            actor_user_id=_actor_id(user),
            price_id=price_id,
        )
    except Exception as exc:
        _bad(exc)


@platform_saas_router.get("/tenants/{tenant_id}/modules")
def tenant_modules(
    tenant_id: str,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return {"items": saas_services.list_tenant_modules(db, tenant_id=tenant_id)}
    except Exception as exc:
        _bad(exc, 404)


@platform_saas_router.patch("/tenants/{tenant_id}/modules")
def tenant_modules_update(
    tenant_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    changes = payload.get("changes") or []
    reason = str(payload.get("reason") or "").strip()
    if not isinstance(changes, list):
        raise HTTPException(status_code=422, detail="changes must be a list")
    try:
        return {
            "items": saas_services.update_tenant_modules(
                db,
                tenant_id=tenant_id,
                changes=changes,
                actor_user_id=_actor_id(user),
                reason=reason,
            )
        }
    except Exception as exc:
        _bad(exc)


@platform_saas_router.post("/billing/tenants/{tenant_id}/manual-invoices", status_code=status.HTTP_201_CREATED)
def manual_invoice(
    tenant_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return saas_services.create_manual_invoice(
            db,
            tenant_id=tenant_id,
            module_price_id=str(payload.get("module_price_id") or ""),
            quantity=int(payload.get("quantity") or 1),
            due_days=int(payload.get("due_days") or 7),
            actor_user_id=_actor_id(user),
            reason=str(payload.get("reason") or "Manual platform invoice"),
            idempotency_key=str(payload.get("idempotency_key") or ""),
        )
    except Exception as exc:
        _bad(exc)


@platform_saas_router.post("/billing/tenants/{tenant_id}/checkout", status_code=status.HTTP_202_ACCEPTED)
def checkout(
    tenant_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        job = saas_services.enqueue_checkout(
            db,
            tenant_id=tenant_id,
            module_price_id=str(payload.get("module_price_id") or ""),
            actor_user_id=_actor_id(user),
            idempotency_key=str(payload.get("idempotency_key") or ""),
        )
        return _job_payload(job)
    except Exception as exc:
        _bad(exc)


@platform_saas_router.post("/billing/invoices/{invoice_id}/fiscalize", status_code=status.HTTP_202_ACCEPTED)
def fiscalize_invoice(
    invoice_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        job = saas_services.enqueue_fiscalization(
            db,
            invoice_id=invoice_id,
            provider=str(payload.get("provider") or "etims_oscu"),
            actor_user_id=_actor_id(user),
        )
        return _job_payload(job)
    except Exception as exc:
        _bad(exc)


@platform_saas_router.get("/billing/invoices/{invoice_id}/fiscalization")
def invoice_fiscalization(
    invoice_id: str,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    row = (
        db.query(models.SaaSInvoiceFiscalization)
        .filter(models.SaaSInvoiceFiscalization.invoice_id == invoice_id)
        .first()
    )
    return saas_services.fiscalization_payload(row) or {"invoice_id": invoice_id, "status": "NOT_SUBMITTED"}


@webhook_router.post("/stripe", status_code=status.HTTP_202_ACCEPTED)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header("", alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    raw = await request.body()
    try:
        job = saas_services.record_stripe_webhook(db, raw_payload=raw, signature=stripe_signature)
        return {"accepted": True, "job_id": job.id}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook JSON") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        _bad(exc)


@support_router.post("/tickets", status_code=status.HTTP_201_CREATED)
def support_ticket_create(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    requested_tenant = str(payload.get("tenant_id") or "").strip() or None
    tenant_id = requested_tenant if getattr(user, "is_superuser", False) else user.amo_id
    if not tenant_id and not getattr(user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="A tenant context is required")
    try:
        return saas_services.create_support_ticket(
            db,
            tenant_id=tenant_id,
            title=str(payload.get("title") or ""),
            description=str(payload.get("description") or ""),
            priority=str(payload.get("priority") or "NORMAL"),
            category=str(payload.get("category") or "GENERAL"),
            requester_user_id=_actor_id(user),
            requester_email=user.email,
        )
    except Exception as exc:
        _bad(exc)


@support_router.get("/tickets")
def support_tickets(
    tenant_id: str | None = None,
    ticket_status: str | None = Query(None, alias="status"),
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_read_db),
    user=Depends(get_current_active_user),
):
    scoped_tenant = tenant_id if getattr(user, "is_superuser", False) else user.amo_id
    return saas_services.list_support_tickets(
        db,
        tenant_id=scoped_tenant,
        status=ticket_status,
        q=q,
        limit=limit,
        offset=offset,
    )


@support_router.get("/tickets/{ticket_id}")
def support_ticket_detail(
    ticket_id: str,
    db: Session = Depends(get_read_db),
    user=Depends(get_current_active_user),
):
    row = db.get(platform_models.PlatformSupportTicket, ticket_id)
    if not row:
        raise HTTPException(status_code=404, detail="Support ticket not found")
    _ticket_access(user, row)
    return saas_services.support_ticket_payload(db, row, include_messages=True)


@support_router.patch("/tickets/{ticket_id}")
def support_ticket_update(
    ticket_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    row = db.get(platform_models.PlatformSupportTicket, ticket_id)
    if not row:
        raise HTTPException(status_code=404, detail="Support ticket not found")
    _ticket_access(user, row)
    if not getattr(user, "is_superuser", False):
        allowed = {"status", "reason"}
        if set(payload) - allowed:
            raise HTTPException(status_code=403, detail="Tenant users may only update ticket status")
    try:
        return saas_services.update_support_ticket(
            db,
            ticket_id=ticket_id,
            payload=payload,
            actor_user_id=_actor_id(user),
        )
    except Exception as exc:
        _bad(exc)


@support_router.post("/tickets/{ticket_id}/messages", status_code=status.HTTP_201_CREATED)
def support_message_create(
    ticket_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    row = db.get(platform_models.PlatformSupportTicket, ticket_id)
    if not row:
        raise HTTPException(status_code=404, detail="Support ticket not found")
    _ticket_access(user, row)
    visibility = str(payload.get("visibility") or "PUBLIC").upper()
    if visibility == "INTERNAL" and not getattr(user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="Internal notes require platform support access")
    try:
        return saas_services.add_support_message(
            db,
            ticket_id=ticket_id,
            author_user_id=_actor_id(user),
            author_type="SUPPORT" if getattr(user, "is_superuser", False) else "USER",
            body=str(payload.get("body") or ""),
            visibility=visibility,
        )
    except Exception as exc:
        _bad(exc)


@support_router.post("/tickets/{ticket_id}/ai-reply", status_code=status.HTTP_202_ACCEPTED)
def support_ai_reply(
    ticket_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        job = saas_services.enqueue_ai_support_reply(db, ticket_id=ticket_id, actor_user_id=_actor_id(user))
        return _job_payload(job)
    except Exception as exc:
        _bad(exc)
