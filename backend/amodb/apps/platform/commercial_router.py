from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from amodb.database import get_db, get_read_db

from .router import require_platform_superuser
from . import commercial_policy, commercial_services


router = APIRouter(prefix="/commercial", tags=["platform-commercial-control"])


def _actor_id(user: Any) -> str:
    return str(user.id)


def _bad(exc: Exception, code: int = 400) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("/summary")
def summary(
    data_mode: str = Query("REAL"),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    return commercial_services.commercial_summary(db, data_mode=data_mode)


@router.get("/capacity")
def capacity(
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    return commercial_services.capacity_readiness(db)


@router.get("/tenants/{tenant_id}/lifecycle")
def tenant_lifecycle(
    tenant_id: str,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_policy.tenant_lifecycle_evidence(db, tenant_id=tenant_id)
    except Exception as exc:
        _bad(exc, 404)


@router.post("/tenants/{tenant_id}/reconcile-status")
def reconcile_tenant_status(
    tenant_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_policy.reconcile_tenant_status(
            db,
            tenant_id=tenant_id,
            actor_user_id=_actor_id(user),
            reason=str(payload.get("reason") or "").strip(),
            apply=bool(payload.get("apply", False)),
        )
    except Exception as exc:
        _bad(exc)


@router.post("/billing/invoices/{invoice_id}/payment", status_code=status.HTTP_202_ACCEPTED)
def start_invoice_payment(
    invoice_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        job = commercial_services.enqueue_invoice_payment(
            db,
            invoice_id=invoice_id,
            provider=str(payload.get("provider") or ""),
            actor_user_id=_actor_id(user),
            idempotency_key=str(payload.get("idempotency_key") or ""),
            phone=str(payload.get("phone") or "").strip() or None,
        )
        return {
            "id": job.id,
            "job_type": job.job_type,
            "status": job.status,
            "tenant_id": job.tenant_id,
            "correlation_id": job.correlation_id,
        }
    except Exception as exc:
        _bad(exc)


@router.post("/billing/invoices/{invoice_id}/offline-payment")
def record_offline_payment(
    invoice_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.record_offline_payment(
            db,
            invoice_id=invoice_id,
            reference=str(payload.get("reference") or "").strip(),
            actor_user_id=_actor_id(user),
            reason=str(payload.get("reason") or "").strip(),
        )
    except Exception as exc:
        _bad(exc)


@router.post("/billing/invoices/{invoice_id}/quickbooks-sync", status_code=status.HTTP_202_ACCEPTED)
def quickbooks_sync(
    invoice_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        job = commercial_services.enqueue_quickbooks_sync(
            db,
            invoice_id=invoice_id,
            actor_user_id=_actor_id(user),
        )
        return {
            "id": job.id,
            "job_type": job.job_type,
            "status": job.status,
            "tenant_id": job.tenant_id,
            "correlation_id": job.correlation_id,
        }
    except Exception as exc:
        _bad(exc)


@router.get("/quickbooks/authorize")
def quickbooks_authorize(
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.quickbooks_authorize(db)
    except Exception as exc:
        _bad(exc)


@router.get("/quickbooks/callback", include_in_schema=True)
def quickbooks_callback(
    code: str = Query(...),
    state: str = Query(...),
    realmId: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        commercial_services.quickbooks_oauth_callback(db, code=code, state=state, realm_id=realmId)
    except Exception as exc:
        message = urllib_quote(str(exc)[:400])
        return RedirectResponse(url=f"/platform/billing?quickbooks=error&detail={message}", status_code=303)
    return RedirectResponse(url="/platform/billing?quickbooks=connected", status_code=303)


def urllib_quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


@router.post("/webhooks/paystack", status_code=status.HTTP_202_ACCEPTED)
async def paystack_webhook(
    request: Request,
    paystack_signature: str = Header("", alias="x-paystack-signature"),
    db: Session = Depends(get_db),
):
    raw = await request.body()
    try:
        job = commercial_services.record_paystack_webhook(db, raw_payload=raw, signature=paystack_signature)
        return {"accepted": True, "job_id": job.id}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook JSON") from exc
    except Exception as exc:
        _bad(exc)


@router.post("/webhooks/mpesa", status_code=status.HTTP_202_ACCEPTED)
async def mpesa_callback(
    request: Request,
    tenant_id: str = Query(...),
    invoice_id: str = Query(...),
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid M-PESA callback JSON") from exc
    try:
        job = commercial_services.record_mpesa_callback(
            db,
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            token=token,
            payload=payload,
        )
        return {"ResultCode": 0, "ResultDesc": "Accepted", "job_id": job.id}
    except Exception as exc:
        _bad(exc)
