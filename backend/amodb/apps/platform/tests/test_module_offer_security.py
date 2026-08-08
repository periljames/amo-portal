from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import module_commerce, saas_models
from amodb.database import WriteSessionLocal


def _case():
    suffix = uuid.uuid4().hex[:10]
    db = WriteSessionLocal()
    tenant_id = f"offer-{suffix}"
    db.add(
        account_models.AMO(
            id=tenant_id,
            amo_code=f"OF{suffix[:8].upper()}",
            login_slug=f"offer-{suffix}",
            name=f"Offer Test {suffix}",
            country="KE",
            is_demo=True,
            is_active=True,
        )
    )
    quality = saas_models.SaaSModulePrice(
        module_code="quality",
        plan_code=f"Q{suffix.upper()}",
        billing_term="MONTHLY",
        amount_cents=100000,
        currency="KES",
        trial_days=0,
        tax_rate_bps=1600,
        is_active=True,
    )
    training = saas_models.SaaSModulePrice(
        module_code="training",
        plan_code=f"T{suffix.upper()}",
        billing_term="MONTHLY",
        amount_cents=50000,
        currency="KES",
        trial_days=0,
        tax_rate_bps=1600,
        is_active=True,
    )
    db.add_all([quality, training])
    db.commit()
    db.refresh(quality)
    db.refresh(training)
    return db, suffix, tenant_id, quality, training


def _checkout(db, *, tenant_id: str, price_id: str, amount: int = 100000, currency: str = "KES"):
    return module_commerce.create_self_service_invoice(
        db,
        tenant_id=tenant_id,
        module_code="quality",
        price_id=price_id,
        expected_amount_cents=amount,
        expected_currency=currency,
        actor_user_id=None,
        idempotency_key=f"checkout-{uuid.uuid4().hex}",
        terms_version="module-subscription-2026-08-08",
        auto_renew_accepted=True,
    )


def test_checkout_rejects_price_id_from_another_module() -> None:
    db, _suffix, tenant_id, _quality, training = _case()
    try:
        with pytest.raises(ValueError, match="Price is not available for this tenant"):
            _checkout(db, tenant_id=tenant_id, price_id=training.id, amount=training.amount_cents)
    finally:
        db.close()


def test_checkout_rejects_client_amount_and_currency_tampering() -> None:
    db, _suffix, tenant_id, quality, _training = _case()
    try:
        with pytest.raises(ValueError, match="Displayed price changed"):
            _checkout(db, tenant_id=tenant_id, price_id=quality.id, amount=999)
        with pytest.raises(ValueError, match="Displayed currency changed"):
            _checkout(db, tenant_id=tenant_id, price_id=quality.id, currency="USD")
    finally:
        db.close()


def test_hidden_tenant_offer_is_authoritative_and_does_not_fallback_global() -> None:
    db, _suffix, tenant_id, quality, _training = _case()
    try:
        module_commerce.set_tenant_offer(
            db,
            tenant_id=tenant_id,
            module_code="quality",
            payload={
                "base_price_id": quality.id,
                "amount_cents": 80000,
                "currency": "KES",
                "billing_term": "MONTHLY",
                "tax_rate_bps": 1600,
                "customer_selectable": False,
                "reason": "Private negotiated offer not yet released",
            },
            actor_user_id=None,
        )
        catalog = module_commerce.self_service_catalog(db, tenant_id=tenant_id)
        item = next(row for row in catalog["items"] if row["code"] == "quality")
        assert item["prices"] == []
        assert item["can_subscribe"] is False
        with pytest.raises(ValueError, match="not currently available"):
            _checkout(db, tenant_id=tenant_id, price_id=quality.id)
    finally:
        db.close()


def test_expired_negotiated_offer_cannot_be_replayed() -> None:
    db, _suffix, tenant_id, quality, _training = _case()
    try:
        expired_terms = {
            "base_price_id": quality.id,
            "amount_cents": 75000,
            "currency": "KES",
            "billing_term": "MONTHLY",
            "tax_rate_bps": 1600,
            "trial_days": 0,
            "customer_selectable": True,
            "valid_until": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            "reason": "Expired negotiated quote",
        }
        db.add(
            account_models.ModuleSubscription(
                amo_id=tenant_id,
                module_code="quality",
                status=account_models.ModuleSubscriptionStatus.DISABLED,
                metadata_json=json.dumps(
                    {"commercial_offer_only": True, "commercial_terms": expired_terms},
                    separators=(",", ":"),
                ),
            )
        )
        db.commit()
        catalog = module_commerce.self_service_catalog(db, tenant_id=tenant_id)
        item = next(row for row in catalog["items"] if row["code"] == "quality")
        assert item["prices"] == []
        assert item["can_subscribe"] is False
        with pytest.raises(ValueError, match="not currently available"):
            _checkout(db, tenant_id=tenant_id, price_id=quality.id, amount=75000)
    finally:
        db.close()


def test_new_offer_cannot_be_saved_with_past_valid_until() -> None:
    db, _suffix, tenant_id, quality, _training = _case()
    try:
        with pytest.raises(ValueError, match="valid_until must be in the future"):
            module_commerce.set_tenant_offer(
                db,
                tenant_id=tenant_id,
                module_code="quality",
                payload={
                    "base_price_id": quality.id,
                    "amount_cents": 80000,
                    "currency": "KES",
                    "billing_term": "MONTHLY",
                    "tax_rate_bps": 1600,
                    "customer_selectable": True,
                    "valid_until": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                    "reason": "Invalid expired offer",
                },
                actor_user_id=None,
            )
    finally:
        db.close()
