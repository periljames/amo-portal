from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from amodb.database import get_db, get_read_db

from . import commercial_services
from .router import require_platform_superuser


router = APIRouter(prefix="/commercial", tags=["platform-commercial-control-plane"])


def _actor_id(user: Any) -> str:
    return str(getattr(user, "id", ""))


def _bad(exc: Exception, default_code: int = 400) -> None:
    message = str(exc)
    code = 404 if "not found" in message.lower() else default_code
    raise HTTPException(status_code=code, detail=message) from exc


@router.get("/data-modes")
def data_modes(user=Depends(require_platform_superuser)):
    return {
        "items": [
            {"code": "REAL", "label": "Real tenants", "description": "Live production tenants and commercial records."},
            {"code": "DEMO", "label": "Demo tenants", "description": "Isolated demonstration tenants and commercial records."},
        ],
        "rule": "The platform operates in either REAL or DEMO mode. ALL is intentionally unsupported.",
    }


@router.post("/bootstrap")
def bootstrap_catalog(
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    commercial_services.ensure_catalog(db, actor_user_id=_actor_id(user))
    return {
        "modules": commercial_services.list_modules(db),
        "plans": commercial_services.list_plans(db),
        "price_books": commercial_services.list_price_books(db),
    }


@router.get("/summary")
def summary(
    data_mode: str = Query("REAL"),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.commercial_summary(db, data_mode=data_mode)
    except Exception as exc:
        _bad(exc)


@router.get("/modules")
def modules(
    include_archived: bool = False,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return {"items": commercial_services.list_modules(db, include_archived=include_archived)}
    except Exception as exc:
        _bad(exc)


@router.post("/modules", status_code=status.HTTP_201_CREATED)
def create_module(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.upsert_module(db, payload=payload, actor_user_id=_actor_id(user))
    except Exception as exc:
        _bad(exc)


@router.patch("/modules/{module_id}")
def update_module(
    module_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.upsert_module(
            db,
            payload=payload,
            actor_user_id=_actor_id(user),
            module_id=module_id,
        )
    except Exception as exc:
        _bad(exc)


@router.get("/plans")
def plans(
    include_archived: bool = False,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return {"items": commercial_services.list_plans(db, include_archived=include_archived)}
    except Exception as exc:
        _bad(exc)


@router.post("/plans", status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.upsert_plan(db, payload=payload, actor_user_id=_actor_id(user))
    except Exception as exc:
        _bad(exc)


@router.patch("/plans/{plan_id}")
def update_plan(
    plan_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.upsert_plan(
            db,
            payload=payload,
            actor_user_id=_actor_id(user),
            plan_id=plan_id,
        )
    except Exception as exc:
        _bad(exc)


@router.get("/price-books")
def price_books(
    data_mode: str | None = None,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return {"items": commercial_services.list_price_books(db, data_mode=data_mode)}
    except Exception as exc:
        _bad(exc)


@router.post("/price-books", status_code=status.HTTP_201_CREATED)
def create_price_book(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.upsert_price_book(db, payload=payload, actor_user_id=_actor_id(user))
    except Exception as exc:
        _bad(exc)


@router.patch("/price-books/{book_id}")
def update_price_book(
    book_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.upsert_price_book(
            db,
            payload=payload,
            actor_user_id=_actor_id(user),
            book_id=book_id,
        )
    except Exception as exc:
        _bad(exc)


@router.get("/prices")
def prices(
    data_mode: str | None = None,
    include_retired: bool = False,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return {
            "items": commercial_services.list_prices(
                db,
                data_mode=data_mode,
                include_retired=include_retired,
            )
        }
    except Exception as exc:
        _bad(exc)


@router.post("/prices", status_code=status.HTTP_201_CREATED)
def create_price(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.upsert_price(db, payload=payload, actor_user_id=_actor_id(user))
    except Exception as exc:
        _bad(exc)


@router.patch("/prices/{price_id}")
def update_price(
    price_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.upsert_price(
            db,
            payload=payload,
            actor_user_id=_actor_id(user),
            price_id=price_id,
        )
    except Exception as exc:
        _bad(exc)


@router.get("/subscriptions")
def subscriptions(
    data_mode: str = Query("REAL"),
    tenant_id: str | None = None,
    subscription_status: str | None = Query(None, alias="status"),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return {
            "items": commercial_services.list_subscriptions(
                db,
                data_mode=data_mode,
                tenant_id=tenant_id,
                status=subscription_status,
            )
        }
    except Exception as exc:
        _bad(exc)


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
def create_subscription(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.create_subscription(db, payload=payload, actor_user_id=_actor_id(user))
    except Exception as exc:
        _bad(exc)


@router.get("/subscriptions/{subscription_id}")
def subscription_detail(
    subscription_id: str,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    from .commercial_models import TenantSubscription

    row = db.get(TenantSubscription, subscription_id)
    if not row:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return commercial_services.subscription_payload(db, row, include_events=True)


@router.patch("/subscriptions/{subscription_id}")
def update_subscription(
    subscription_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.update_subscription(
            db,
            subscription_id=subscription_id,
            payload=payload,
            actor_user_id=_actor_id(user),
        )
    except Exception as exc:
        _bad(exc)


@router.post("/subscriptions/{subscription_id}/transition")
def transition_subscription(
    subscription_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.transition_subscription(
            db,
            subscription_id=subscription_id,
            target_status=str(payload.get("target_status") or ""),
            actor_user_id=_actor_id(user),
            reason=str(payload.get("reason") or ""),
            at_period_end=bool(payload.get("at_period_end", False)),
        )
    except Exception as exc:
        _bad(exc)


@router.post("/subscriptions/{subscription_id}/items")
def upsert_subscription_item(
    subscription_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.upsert_subscription_item(
            db,
            subscription_id=subscription_id,
            payload=payload,
            actor_user_id=_actor_id(user),
        )
    except Exception as exc:
        _bad(exc)


@router.post("/subscriptions/{subscription_id}/reconcile")
def reconcile_subscription(
    subscription_id: str,
    payload: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    from .commercial_models import TenantSubscription

    row = db.get(TenantSubscription, subscription_id)
    if not row:
        raise HTTPException(status_code=404, detail="Subscription not found")
    try:
        return commercial_services.reconcile_subscription(
            db,
            row=row,
            actor_user_id=_actor_id(user),
            reason=str((payload or {}).get("reason") or "Manual superuser reconciliation"),
        )
    except Exception as exc:
        _bad(exc)


@router.post("/tenants/provision", status_code=status.HTTP_201_CREATED)
def provision_tenant(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.provision_tenant(db, payload=payload, actor_user_id=_actor_id(user))
    except Exception as exc:
        db.rollback()
        _bad(exc)


@router.get("/tenants/{tenant_id}")
def tenant_control_plane(
    tenant_id: str,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.tenant_control_plane(db, tenant_id=tenant_id)
    except Exception as exc:
        _bad(exc, 404)


@router.patch("/tenants/{tenant_id}")
def update_tenant_profile(
    tenant_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.update_tenant_profile(
            db,
            tenant_id=tenant_id,
            payload=payload,
            actor_user_id=_actor_id(user),
        )
    except Exception as exc:
        _bad(exc)


@router.post("/tenants/{tenant_id}/entitlement-overrides", status_code=status.HTTP_201_CREATED)
def create_entitlement_override(
    tenant_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.create_override(
            db,
            tenant_id=tenant_id,
            payload=payload,
            actor_user_id=_actor_id(user),
        )
    except Exception as exc:
        _bad(exc)


@router.get("/tenants/{tenant_id}/entitlements")
def tenant_entitlements(
    tenant_id: str,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return {"items": commercial_services.resolved_entitlements(db, tenant_id=tenant_id)}
    except Exception as exc:
        _bad(exc)


@router.get("/invoices")
def invoices(
    data_mode: str = Query("REAL"),
    invoice_status: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.list_invoices(
            db,
            data_mode=data_mode,
            status=invoice_status,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        _bad(exc)


@router.post("/tenants/{tenant_id}/invoices", status_code=status.HTTP_201_CREATED)
def create_invoice(
    tenant_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.create_invoice(
            db,
            tenant_id=tenant_id,
            payload=payload,
            actor_user_id=_actor_id(user),
        )
    except Exception as exc:
        db.rollback()
        _bad(exc)


@router.post("/invoices/{invoice_id}/payments", status_code=status.HTTP_201_CREATED)
def record_payment(
    invoice_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.record_payment(
            db,
            invoice_id=invoice_id,
            payload=payload,
            actor_user_id=_actor_id(user),
        )
    except Exception as exc:
        db.rollback()
        _bad(exc)


@router.post("/users/{user_id}/force-password-reset")
def force_password_reset(
    user_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return commercial_services.force_password_reset(
            db,
            user_id=user_id,
            actor_user_id=_actor_id(user),
            reason=str(payload.get("reason") or ""),
        )
    except Exception as exc:
        _bad(exc)
