from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import commercial_services as services
from .commercial_models import (
    CommercialModule,
    PriceBook,
    ProductPlan,
    SubscriptionEvent,
    SubscriptionItem,
    TenantSubscription,
)

_INSTALLED = False
_CURRENT_SUBSCRIPTION_STATUSES = services.ACTIVE_SUBSCRIPTION_STATUSES | {"DRAFT", "PAUSED"}


def _tenant_mode(db: Session, tenant_id: str) -> str:
    tenant = db.get(account_models.AMO, tenant_id)
    if not tenant:
        raise ValueError("Tenant not found")
    return "DEMO" if tenant.is_demo else "REAL"


def _price_book_for_update(db: Session, row: TenantSubscription, value: Any) -> PriceBook | None:
    if value is None or str(value).strip() == "":
        return None
    book = db.get(PriceBook, str(value))
    if not book or book.status != "ACTIVE" or book.data_mode != _tenant_mode(db, row.tenant_id):
        raise ValueError("Price book does not match the tenant environment")
    return book


def _subscription_amount(db: Session, row: TenantSubscription, *, at: datetime | None = None) -> int:
    at = at or services.utcnow()
    plan_price = services.active_price_for(
        db,
        price_book_id=row.price_book_id,
        plan_id=row.plan_id,
        module_id=None,
        billing_term=row.billing_term,
        at=at,
    )
    if plan_price:
        return int(plan_price.unit_amount_cents or 0) * max(1, int(row.quantity or 1))
    return sum(
        int(item.unit_amount_cents or 0) * max(1, int(item.quantity or 1))
        for item in db.query(SubscriptionItem).filter(
            SubscriptionItem.subscription_id == row.id,
            SubscriptionItem.status == "ACTIVE",
        ).all()
    )


def _rebuild_subscription_items(
    db: Session,
    *,
    row: TenantSubscription,
    actor_user_id: str,
    reason: str,
) -> None:
    now = services.utcnow()
    links = services.plan_module_links(db, row.plan_id)
    desired = {link.module_id: link for link in links}
    existing = {
        item.module_id: item
        for item in db.query(SubscriptionItem).filter(
            SubscriptionItem.subscription_id == row.id,
        ).all()
    }

    for module_id, item in existing.items():
        if module_id in desired:
            continue
        item.status = "DISABLED"
        item.effective_to = item.effective_to or now

    for module_id, link in desired.items():
        module = db.get(CommercialModule, module_id)
        if not module:
            continue
        item = existing.get(module_id)
        if not item:
            item = SubscriptionItem(
                subscription_id=row.id,
                module_id=module_id,
                effective_from=now,
            )
            db.add(item)
        price = services.active_price_for(
            db,
            price_book_id=row.price_book_id,
            plan_id=row.plan_id,
            module_id=module_id,
            billing_term=row.billing_term,
            at=now,
        )
        item.price_entry_id = price.id if price else None
        item.status = "ACTIVE"
        item.quantity = max(1, int(row.quantity or 1))
        item.unit_amount_cents = int(price.unit_amount_cents or 0) if price else 0
        item.limits_json = {
            **(module.default_limits_json or {}),
            **(link.limits_json or {}),
        }
        item.effective_to = None

    db.flush()
    db.add(SubscriptionEvent(
        subscription_id=row.id,
        event_type="ITEMS_REBUILT",
        actor_user_id=actor_user_id,
        reason=reason,
        before_json={},
        after_json={
            "plan_id": row.plan_id,
            "price_book_id": row.price_book_id,
            "billing_term": row.billing_term,
            "quantity": row.quantity,
            "active_module_count": len(desired),
        },
    ))
    services.audit(
        db,
        actor_user_id=actor_user_id,
        action="commercial.subscription.items_rebuilt",
        tenant_id=row.tenant_id,
        entity_type="tenant_subscription",
        entity_id=row.id,
        reason=reason,
        details={"active_module_count": len(desired)},
    )


def _apply_due_cancellations(db: Session, *, tenant_id: str | None = None) -> int:
    now = services.utcnow()
    query = db.query(TenantSubscription).filter(
        TenantSubscription.cancel_at_period_end.is_(True),
        TenantSubscription.current_period_end.isnot(None),
        TenantSubscription.current_period_end <= now,
        TenantSubscription.status.in_(services.ACTIVE_SUBSCRIPTION_STATUSES | {"PAUSED"}),
    )
    if tenant_id:
        query = query.filter(TenantSubscription.tenant_id == tenant_id)
    rows = query.all()
    for row in rows:
        before = services.subscription_snapshot(row)
        row.status = "CANCELLED"
        row.cancel_at_period_end = False
        row.cancelled_at = now
        row.updated_at = now
        for item in db.query(SubscriptionItem).filter(
            SubscriptionItem.subscription_id == row.id,
            SubscriptionItem.status == "ACTIVE",
        ).all():
            item.status = "DISABLED"
            item.effective_to = item.effective_to or now
        db.add(SubscriptionEvent(
            subscription_id=row.id,
            event_type="STATUS_CANCELLED",
            actor_user_id=None,
            reason="Scheduled cancellation reached the current period end",
            before_json=before,
            after_json=services.subscription_snapshot(row),
        ))
        services.audit(
            db,
            actor_user_id=None,
            action="commercial.subscription.scheduled_cancellation_applied",
            tenant_id=row.tenant_id,
            entity_type="tenant_subscription",
            entity_id=row.id,
            reason="Current period ended",
            details={"current_period_end": row.current_period_end.isoformat() if row.current_period_end else None},
        )
        license_row = services.account_services.get_latest_subscription(db, amo_id=row.tenant_id)
        if license_row:
            license_row.status = account_models.LicenseStatus.CANCELLED
            license_row.is_read_only = True
            license_row.canceled_at = now
        for legacy in db.query(account_models.ModuleSubscription).filter(
            account_models.ModuleSubscription.amo_id == row.tenant_id,
        ).all():
            legacy.status = account_models.ModuleSubscriptionStatus.DISABLED
            legacy.effective_to = legacy.effective_to or now
    if rows:
        db.flush()
        db.commit()
    return len(rows)


def _monthly_amount(amount: int, term: str) -> int:
    if term == "MONTHLY":
        return amount
    if term == "BI_ANNUAL":
        return round(amount / 6)
    if term == "ANNUAL":
        return round(amount / 12)
    return 0


def install_commercial_integrity_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_update_subscription = services.update_subscription
    original_transition_subscription = services.transition_subscription
    original_update_tenant_profile = services.update_tenant_profile
    original_list_subscriptions = services.list_subscriptions
    original_subscription_payload = services.subscription_payload
    original_resolved_entitlements = services.resolved_entitlements
    original_tenant_control_plane = services.tenant_control_plane
    original_commercial_summary = services.commercial_summary

    def update_subscription(
        db: Session,
        *,
        subscription_id: str,
        payload: dict[str, Any],
        actor_user_id: str,
    ) -> dict[str, Any]:
        row = db.get(TenantSubscription, subscription_id)
        if not row:
            raise ValueError("Subscription not found")
        next_payload = dict(payload)
        clear_price_book = "price_book_id" in next_payload and not str(next_payload.get("price_book_id") or "").strip()
        selected_book = _price_book_for_update(db, row, next_payload.get("price_book_id")) if "price_book_id" in next_payload else None
        plan_changed = "plan_id" in next_payload and str(next_payload.get("plan_id") or "") != row.plan_id
        pricing_changed = any(key in next_payload for key in ("price_book_id", "billing_term", "quantity"))

        if clear_price_book:
            next_payload.pop("price_book_id", None)
        result = original_update_subscription(
            db,
            subscription_id=subscription_id,
            payload=next_payload,
            actor_user_id=actor_user_id,
        )
        row = db.get(TenantSubscription, subscription_id)
        if not row:
            return result
        if clear_price_book:
            row.price_book_id = None
            row.currency = str(payload.get("currency") or row.currency or "USD").upper()
        elif selected_book:
            row.price_book_id = selected_book.id
            row.currency = selected_book.currency
        if plan_changed or pricing_changed:
            _rebuild_subscription_items(
                db,
                row=row,
                actor_user_id=actor_user_id,
                reason=str(payload.get("reason") or "Subscription configuration changed"),
            )
            services.reconcile_subscription(
                db,
                row=row,
                actor_user_id=actor_user_id,
                reason="Reconcile rebuilt subscription items",
                commit=False,
            )
            db.commit()
            db.refresh(row)
            return services.subscription_payload(db, row, include_events=True)
        return result

    def transition_subscription(
        db: Session,
        *,
        subscription_id: str,
        target_status: str,
        actor_user_id: str,
        reason: str,
        at_period_end: bool = False,
    ) -> dict[str, Any]:
        row = db.get(TenantSubscription, subscription_id)
        if not row:
            raise ValueError("Subscription not found")
        target = target_status.strip().upper()
        if target in services.ACTIVE_SUBSCRIPTION_STATUSES and row.price_book_id:
            _price_book_for_update(db, row, row.price_book_id)
        return original_transition_subscription(
            db,
            subscription_id=subscription_id,
            target_status=target_status,
            actor_user_id=actor_user_id,
            reason=reason,
            at_period_end=at_period_end,
        )

    def update_tenant_profile(
        db: Session,
        *,
        tenant_id: str,
        payload: dict[str, Any],
        actor_user_id: str,
    ) -> dict[str, Any]:
        tenant = db.get(account_models.AMO, tenant_id)
        if not tenant:
            raise ValueError("Tenant not found")
        if "is_demo" in payload and bool(payload["is_demo"]) != bool(tenant.is_demo):
            current = db.query(TenantSubscription).filter(
                TenantSubscription.tenant_id == tenant_id,
                TenantSubscription.status.in_(_CURRENT_SUBSCRIPTION_STATUSES),
            ).first()
            if current:
                raise ValueError("End or explicitly migrate the current subscription before changing tenant environment")
        return original_update_tenant_profile(
            db,
            tenant_id=tenant_id,
            payload=payload,
            actor_user_id=actor_user_id,
        )

    def list_subscriptions(db: Session, **kwargs: Any) -> list[dict[str, Any]]:
        _apply_due_cancellations(db, tenant_id=kwargs.get("tenant_id"))
        return original_list_subscriptions(db, **kwargs)

    def subscription_payload(db: Session, row: TenantSubscription, **kwargs: Any) -> dict[str, Any]:
        _apply_due_cancellations(db, tenant_id=row.tenant_id)
        fresh = db.get(TenantSubscription, row.id) or row
        return original_subscription_payload(db, fresh, **kwargs)

    def resolved_entitlements(db: Session, *, tenant_id: str) -> list[dict[str, Any]]:
        _apply_due_cancellations(db, tenant_id=tenant_id)
        return original_resolved_entitlements(db, tenant_id=tenant_id)

    def tenant_control_plane(db: Session, *, tenant_id: str) -> dict[str, Any]:
        _apply_due_cancellations(db, tenant_id=tenant_id)
        return original_tenant_control_plane(db, tenant_id=tenant_id)

    def commercial_summary(db: Session, *, data_mode: str) -> dict[str, Any]:
        mode = services.normalize_data_mode(data_mode)
        _apply_due_cancellations(db)
        result = original_commercial_summary(db, data_mode=mode)
        tenant_filter = account_models.AMO.is_demo.is_(mode == "DEMO")
        rows = db.query(TenantSubscription).join(
            account_models.AMO,
            account_models.AMO.id == TenantSubscription.tenant_id,
        ).filter(
            tenant_filter,
            TenantSubscription.status.in_(services.ACTIVE_SUBSCRIPTION_STATUSES),
        ).all()
        revenue: dict[str, dict[str, int]] = {}
        for row in rows:
            monthly = _monthly_amount(_subscription_amount(db, row), row.billing_term)
            bucket = revenue.setdefault(row.currency, {
                "mrr_cents": 0,
                "arr_cents": 0,
                "at_risk_cents": 0,
                "trial_pipeline_cents": 0,
            })
            bucket["mrr_cents"] += monthly
            bucket["arr_cents"] += monthly * 12
            if row.status == "PAST_DUE":
                bucket["at_risk_cents"] += monthly
            if row.status == "TRIALING":
                bucket["trial_pipeline_cents"] += monthly
        result["revenue_by_currency"] = revenue
        return result

    services.update_subscription = update_subscription
    services.transition_subscription = transition_subscription
    services.update_tenant_profile = update_tenant_profile
    services.list_subscriptions = list_subscriptions
    services.subscription_payload = subscription_payload
    services.resolved_entitlements = resolved_entitlements
    services.tenant_control_plane = tenant_control_plane
    services.commercial_summary = commercial_summary
    _INSTALLED = True


__all__ = [
    "install_commercial_integrity_policy",
    "_apply_due_cancellations",
    "_rebuild_subscription_items",
    "_subscription_amount",
]
