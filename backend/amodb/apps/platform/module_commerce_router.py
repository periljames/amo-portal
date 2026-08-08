from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db, get_read_db
from amodb.security import get_current_active_user

from . import commercial_services, module_commerce
from .router import require_platform_superuser


router = APIRouter(prefix="/commerce", tags=["platform-module-commerce"])
TERMS_VERSION = "module-subscription-2026-08-08"


def _bad(exc: Exception, code: int = 400) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    raise HTTPException(status_code=code, detail=str(exc)) from exc


def _tenant_id(user: account_models.User) -> str:
    tenant_id = str(getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None) or "").strip()
    if not tenant_id or getattr(user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="A tenant billing context is required.")
    return tenant_id


def _role_value(user: account_models.User) -> str:
    role = getattr(user, "role", None)
    return str(getattr(role, "value", role) or "").upper()


def _require_contract_authority(user: account_models.User) -> None:
    if bool(getattr(user, "is_amo_admin", False)):
        return
    if _role_value(user) in {"AMO_ADMIN", "FINANCE_MANAGER"}:
        return
    raise HTTPException(
        status_code=403,
        detail="Only an AMO administrator or Finance Manager may accept a new recurring module subscription.",
    )


def _require_payment_authority(user: account_models.User) -> None:
    if bool(getattr(user, "is_amo_admin", False)):
        return
    if _role_value(user) in {"AMO_ADMIN", "FINANCE_MANAGER", "ACCOUNTS_OFFICER"}:
        return
    raise HTTPException(
        status_code=403,
        detail="Only an AMO administrator or authorised finance role may initiate tenant payments.",
    )


def _job_payload(job) -> dict[str, Any]:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "tenant_id": job.tenant_id,
        "correlation_id": job.correlation_id,
        "created_at": job.created_at,
    }


# ---------------------------------------------------------------------------
# Platform superuser commercial governance
# ---------------------------------------------------------------------------


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
        return module_commerce.upsert_module_definition(
            db,
            payload=request,
            actor_user_id=str(user.id),
        )
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


# ---------------------------------------------------------------------------
# Tenant self-service commerce. Billing remains reachable while modules are
# locked so the tenant always has a cure path.
# ---------------------------------------------------------------------------


@router.get("/self-service/catalog")
def self_service_catalog(
    db: Session = Depends(get_read_db),
    user: account_models.User = Depends(get_current_active_user),
):
    tenant_id = _tenant_id(user)
    result = module_commerce.self_service_catalog(db, tenant_id=tenant_id)
    result["terms"] = {
        "version": TERMS_VERSION,
        "recurring_billing": "The selected module renews on the displayed billing interval until cancelled or changed under the agreed commercial terms.",
        "price_disclosure": "The checkout screen must show the exact currency, subtotal, applicable tax and renewal interval before acceptance.",
        "cancellation": "Cancellation stops future renewal; access ordinarily continues through the already-paid service period unless a lawful security, compliance or contractual suspension applies.",
        "non_payment": "An unpaid renewal may suspend service after the stated due date or contractual grace period. Billing, invoices and payment access remain available so the account can cure the arrears.",
        "records": "Suspension of paid features does not by itself delete tenant records. Record retention and deletion remain subject to the tenant agreement, applicable aviation record-retention duties and data-protection requirements.",
    }
    return result


@router.post("/self-service/subscribe", status_code=status.HTTP_201_CREATED)
def self_service_subscribe(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    tenant_id = _tenant_id(user)
    _require_contract_authority(user)
    try:
        return module_commerce.create_self_service_invoice(
            db,
            tenant_id=tenant_id,
            module_code=str(payload.get("module_code") or ""),
            price_id=str(payload.get("price_id") or ""),
            expected_amount_cents=int(payload.get("expected_amount_cents") or 0),
            expected_currency=str(payload.get("currency") or ""),
            actor_user_id=str(user.id),
            idempotency_key=str(payload.get("idempotency_key") or ""),
            terms_version=str(payload.get("terms_version") or ""),
            auto_renew_accepted=bool(payload.get("auto_renew_accepted", False)),
        )
    except Exception as exc:
        _bad(exc)


@router.post("/self-service/invoices/{invoice_id}/payment", status_code=status.HTTP_202_ACCEPTED)
def self_service_invoice_payment(
    invoice_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    tenant_id = _tenant_id(user)
    _require_payment_authority(user)
    invoice = (
        db.query(account_models.BillingInvoice)
        .filter(
            account_models.BillingInvoice.id == invoice_id,
            account_models.BillingInvoice.amo_id == tenant_id,
        )
        .first()
    )
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
