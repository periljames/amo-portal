from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.apps.accounts import billing_auth, models as account_models
from amodb.database import get_db, get_read_db

from . import commercial_services, module_commerce
from .router import require_platform_superuser


router = APIRouter(prefix="/commerce", tags=["platform-module-commerce"])
TERMS_VERSION = "module-subscription-2026-08-08"
SUBSCRIPTION_TERMS = {
    "recurring_billing": "The selected module renews on the displayed billing interval until cancelled or changed under the agreed commercial terms.",
    "price_disclosure": "The checkout screen must show the exact currency, subtotal, applicable tax and renewal interval before acceptance.",
    "cancellation": "Cancellation stops future renewal; access ordinarily continues through the already-paid service period unless a lawful security, compliance or contractual suspension applies.",
    "non_payment": "An unpaid renewal may suspend the affected paid service after the stated due date or contractual grace period. Billing, invoices and payment access remain available so authorised users can cure the arrears.",
    "records": "Suspension of paid features does not by itself delete tenant records. Record retention and deletion remain subject to the tenant agreement, applicable aviation record-retention duties and data-protection requirements.",
}
TERMS_HASH = hashlib.sha256(
    json.dumps(SUBSCRIPTION_TERMS, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()


def _bad(exc: Exception, code: int = 400) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    raise HTTPException(status_code=code, detail=str(exc)) from exc


def _tenant_id(user: account_models.User) -> str:
    tenant_id = str(getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None) or "").strip()
    if not tenant_id or getattr(user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="A tenant billing context is required.")
    return tenant_id


def _job_payload(job) -> dict[str, Any]:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "tenant_id": job.tenant_id,
        "correlation_id": job.correlation_id,
        "created_at": job.created_at,
    }


def _terms_payload() -> dict[str, Any]:
    return {"version": TERMS_VERSION, "hash": TERMS_HASH, **SUBSCRIPTION_TERMS}


def _stamp_accepted_terms(db: Session, *, tenant_id: str, invoice_id: str) -> dict[str, Any]:
    invoice = db.query(account_models.BillingInvoice).filter(
        account_models.BillingInvoice.id == invoice_id,
        account_models.BillingInvoice.amo_id == tenant_id,
    ).first()
    if invoice is None:
        raise ValueError("Created checkout invoice could not be reloaded")
    try:
        details = json.loads(invoice.description or "{}")
    except (TypeError, ValueError):
        details = {}
    if not isinstance(details, dict):
        details = {}
    existing_hash = str(details.get("terms_hash") or "").strip()
    if existing_hash and existing_hash != TERMS_HASH:
        raise ValueError("Accepted terms hash does not match the current terms version; issue a new terms version before checkout")
    details["terms_version"] = TERMS_VERSION
    details["terms_hash"] = TERMS_HASH
    details["terms_snapshot"] = dict(SUBSCRIPTION_TERMS)
    invoice.description = json.dumps(details, separators=(",", ":"))
    db.add(invoice)
    db.commit()
    return details


@router.get("/catalog/modules")
def module_catalog(
    include_inactive: bool = True,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    return {"items": module_commerce.list_module_catalog(db, include_inactive=include_inactive)}


@router.put("/catalog/modules/{module_code}")
def module_definition_update(
    module_code: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    request = dict(payload or {})
    request["code"] = module_code
    try:
        return module_commerce.upsert_module_definition(db, payload=request, actor_user_id=str(user.id))
    except Exception as exc:
        _bad(exc)


@router.get("/tenants/{tenant_id}/catalog")
def tenant_effective_catalog(
    tenant_id: str,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    return module_commerce.self_service_catalog(db, tenant_id=tenant_id)


@router.put("/tenants/{tenant_id}/offers/{module_code}")
def tenant_offer_update(
    tenant_id: str,
    module_code: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return module_commerce.set_tenant_offer(
            db,
            tenant_id=tenant_id,
            module_code=module_code,
            payload=payload,
            actor_user_id=str(user.id),
        )
    except Exception as exc:
        _bad(exc)


@router.get("/self-service/catalog")
def self_service_catalog(
    db: Session = Depends(get_read_db),
    user=Depends(billing_auth.require_billing_reader),
):
    tenant_id = _tenant_id(user)
    result = module_commerce.self_service_catalog(db, tenant_id=tenant_id)
    result["terms"] = _terms_payload()
    return result


@router.post("/self-service/subscribe", status_code=status.HTTP_201_CREATED)
def self_service_subscribe(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(billing_auth.require_contract_manager),
):
    tenant_id = _tenant_id(user)
    submitted_terms_version = str(payload.get("terms_version") or "").strip()
    if submitted_terms_version != TERMS_VERSION:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Subscription terms changed. Refresh Billing and review the current terms before accepting.",
        )
    try:
        result = module_commerce.create_self_service_invoice(
            db,
            tenant_id=tenant_id,
            module_code=str(payload.get("module_code") or ""),
            price_id=str(payload.get("price_id") or ""),
            expected_amount_cents=int(payload.get("expected_amount_cents") or 0),
            expected_currency=str(payload.get("currency") or ""),
            actor_user_id=str(user.id),
            idempotency_key=str(payload.get("idempotency_key") or ""),
            terms_version=TERMS_VERSION,
            auto_renew_accepted=bool(payload.get("auto_renew_accepted", False)),
        )
        result["commercial"] = _stamp_accepted_terms(db, tenant_id=tenant_id, invoice_id=str(result["id"]))
        return result
    except Exception as exc:
        _bad(exc)


@router.post("/self-service/invoices/{invoice_id}/payment", status_code=status.HTTP_202_ACCEPTED)
def self_service_invoice_payment(
    invoice_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(billing_auth.require_billing_reader),
):
    tenant_id = _tenant_id(user)
    invoice = db.query(account_models.BillingInvoice).filter(
        account_models.BillingInvoice.id == invoice_id,
        account_models.BillingInvoice.amo_id == tenant_id,
    ).first()
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    try:
        job = commercial_services.enqueue_invoice_payment(
            db,
            invoice_id=invoice.id,
            provider=str(payload.get("provider") or ""),
            actor_user_id=str(user.id),
            idempotency_key=str(payload.get("idempotency_key") or ""),
            phone=str(payload.get("phone") or "").strip() or None,
        )
        return _job_payload(job)
    except Exception as exc:
        _bad(exc)
