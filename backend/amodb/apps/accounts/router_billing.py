# backend/amodb/apps/accounts/router_billing.py

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from . import audit, schemas, services, models

router = APIRouter(prefix="/billing", tags=["billing"])


def _require_user(current_user=Depends(get_current_active_user)):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return current_user


@router.get("/catalog", response_model=list[schemas.CatalogSKURead])
def list_catalog(
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    return services.list_catalog_skus(db)


@router.post(
    "/catalog",
    response_model=schemas.CatalogSKURead,
    status_code=status.HTTP_201_CREATED,
)
def create_catalog(
    payload: schemas.CatalogSKUCreate,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser required.")
    try:
        return services.create_catalog_sku(
            db,
            data=payload,
            actor_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/entitlements", response_model=list[schemas.ResolvedEntitlement])
def list_entitlements(
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    entitlements = services.resolve_entitlements(db, amo_id=current_user.amo_id)
    return list(entitlements.values())


@router.get("/subscription", response_model=schemas.SubscriptionRead)
def get_current_subscription(
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    license = services.get_current_subscription(db, amo_id=current_user.amo_id)
    if not license:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription.")
    return license


@router.get("/invoices", response_model=list[schemas.InvoiceRead])
def get_invoices(
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    return services.list_invoices(db, amo_id=current_user.amo_id)


@router.get("/usage-meters", response_model=list[schemas.UsageMeterRead])
def get_usage_meters(
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    return services.list_usage_meters(db, amo_id=current_user.amo_id)


@router.get("/payment-methods", response_model=list[schemas.PaymentMethodRead])
def get_payment_methods(
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    return services.list_payment_methods(db, amo_id=current_user.amo_id)


@router.post("/payment-methods", response_model=schemas.PaymentMethodRead, status_code=status.HTTP_201_CREATED)
def add_payment_method(
    payload: schemas.PaymentMethodUpsertRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if payload.amo_id != current_user.amo_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AMO mismatch.")
    return services.add_payment_method(
        db,
        amo_id=current_user.amo_id,
        data=payload,
        idempotency_key=payload.idempotency_key,
    )


@router.delete("/payment-methods/{payment_method_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_payment_method(
    payment_method_id: str,
    payload: schemas.PaymentMethodMutationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    services.remove_payment_method(
        db,
        amo_id=current_user.amo_id,
        payment_method_id=payment_method_id,
        idempotency_key=payload.idempotency_key,
    )
    return {}


@router.post("/trial", response_model=schemas.SubscriptionRead, status_code=status.HTTP_201_CREATED)
def start_trial(
    payload: schemas.TrialStartRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    try:
        license = services.start_trial(
            db,
            amo_id=current_user.amo_id,
            sku_code=payload.sku_code,
            idempotency_key=payload.idempotency_key,
        )
        return license
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.post("/purchase", response_model=schemas.SubscriptionRead, status_code=status.HTTP_201_CREATED)
def purchase(
    payload: schemas.PurchaseRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    license, _ledger, _invoice = services.purchase_sku(
        db,
        amo_id=current_user.amo_id,
        sku_code=payload.sku_code,
        idempotency_key=payload.idempotency_key,
        purchase_kind=payload.purchase_kind,
        expected_amount_cents=payload.expected_amount_cents,
        expected_currency=payload.currency,
    )
    return license


@router.post("/cancel", response_model=schemas.SubscriptionRead)
def cancel(
    payload: schemas.CancelSubscriptionRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    license = services.cancel_subscription(
        db,
        amo_id=current_user.amo_id,
        effective_date=payload.effective_date,
        idempotency_key=payload.idempotency_key,
    )
    if not license:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription to cancel.")
    return license


@router.post("/audit-events", status_code=status.HTTP_202_ACCEPTED)
def record_audit_event(
    payload: schemas.AuditEventCreate,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    log = audit.safe_record_audit_event(
        db,
        amo_id=current_user.amo_id,
        event=payload.event_type.strip(),
        details=payload.details or {},
    )
    return {
        "id": log.id if log else None,
        "created_at": log.created_at if log else None,
    }


@router.post("/webhooks/{provider}", status_code=status.HTTP_202_ACCEPTED)
async def webhook_handler(
    provider: models.PaymentProvider,
    request: Request,
    psp_signature: str = Header(None, alias="X-PSP-Signature"),
    db: Session = Depends(get_db),
):
    payload: Dict[str, Any] = await request.json()
    external_id = payload.get("id") or payload.get("event_id") or "unknown"
    should_fail = payload.get("simulate_failure", False)
    event = services.handle_webhook(
        db,
        provider=provider,
        payload=payload,
        signature=psp_signature or "",
        external_event_id=str(external_id),
        event_type=payload.get("type"),
        should_fail=bool(should_fail),
    )
    return {"status": event.status}
