from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json

import pytest
from fastapi import HTTPException

from amodb.apps.accounts import models, services, schemas


def _create_amo(session, *, code: str = "AMO1") -> models.AMO:
    amo = models.AMO(
        amo_code=code,
        name="Test AMO",
        login_slug=f"{code.lower()}-login",
    )
    session.add(amo)
    session.commit()
    return amo


def _create_sku(
    session, *, code: str, term: models.BillingTerm, amount_cents: int = 2500
) -> models.CatalogSKU:
    sku = models.CatalogSKU(
        code=code,
        name=f"{code} Plan",
        term=term,
        trial_days=14,
        amount_cents=amount_cents,
        currency="USD",
    )
    session.add(sku)
    session.commit()
    return sku


def _create_license(
    session,
    *,
    amo_id: str,
    sku: models.CatalogSKU,
    status: models.LicenseStatus,
    term: models.BillingTerm,
    trial_extra_days: int = 0,
) -> models.TenantLicense:
    now = datetime.now(timezone.utc)
    license = models.TenantLicense(
        amo_id=amo_id,
        sku_id=sku.id,
        status=status,
        term=term,
        current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=30),
        trial_started_at=now - timedelta(days=sku.trial_days or 0),
        trial_ends_at=now + timedelta(days=trial_extra_days),
        trial_grace_expires_at=None,
        is_read_only=False,
    )
    session.add(license)
    session.commit()
    return license


def _add_payment_method(session, amo_id: str, *, is_default: bool = True) -> models.PaymentMethod:
    method = models.PaymentMethod(
        amo_id=amo_id,
        provider=models.PaymentProvider.PSP,
        external_ref="pm_default",
        is_default=is_default,
    )
    session.add(method)
    session.commit()
    return method


def test_resolve_entitlements_picks_unlimited_first(db_session):
    amo = _create_amo(db_session)
    sku_monthly = _create_sku(db_session, code="BASE-M", term=models.BillingTerm.MONTHLY)
    sku_annual = _create_sku(db_session, code="BASE-A", term=models.BillingTerm.ANNUAL)

    limited_license = _create_license(
        db_session,
        amo_id=amo.id,
        sku=sku_monthly,
        status=models.LicenseStatus.ACTIVE,
        term=models.BillingTerm.MONTHLY,
    )
    unlimited_license = _create_license(
        db_session,
        amo_id=amo.id,
        sku=sku_annual,
        status=models.LicenseStatus.TRIALING,
        term=models.BillingTerm.ANNUAL,
        trial_extra_days=10,
    )

    db_session.add_all(
        [
            models.LicenseEntitlement(
                license_id=limited_license.id,
                key="seats",
                limit=5,
                is_unlimited=False,
            ),
            models.LicenseEntitlement(
                license_id=limited_license.id,
                key="storage_gb",
                limit=50,
            ),
            models.LicenseEntitlement(
                license_id=unlimited_license.id,
                key="seats",
                is_unlimited=True,
            ),
        ]
    )
    db_session.commit()

    resolved = services.resolve_entitlements(db_session, amo_id=amo.id)
    assert resolved["seats"].is_unlimited is True
    assert resolved["seats"].license_term == models.BillingTerm.ANNUAL
    assert resolved["storage_gb"].limit == 50
    assert resolved["storage_gb"].license_status == models.LicenseStatus.ACTIVE


def test_append_ledger_entry_enforces_idempotency(db_session):
    amo = _create_amo(db_session, code="AMO2")
    entry = services.append_ledger_entry(
        db_session,
        amo_id=amo.id,
        amount_cents=1000,
        currency="USD",
        entry_type=models.LedgerEntryType.CHARGE,
        description="Initial charge",
        idempotency_key="charge-001",
    )

    duplicate = services.append_ledger_entry(
        db_session,
        amo_id=amo.id,
        amount_cents=1000,
        currency="USD",
        entry_type=models.LedgerEntryType.CHARGE,
        description="Should reuse existing",
        idempotency_key="charge-001",
    )

    assert entry.id == duplicate.id
    assert db_session.query(models.LedgerEntry).count() == 1

    with pytest.raises(services.IdempotencyError):
        services.append_ledger_entry(
            db_session,
            amo_id=amo.id,
            amount_cents=1500,
            currency="USD",
            entry_type=models.LedgerEntryType.CHARGE,
            description="Conflicting payload",
            idempotency_key="charge-001",
        )


def test_add_payment_method_is_idempotent(db_session):
    amo = _create_amo(db_session, code="AMO3")
    payload = schemas.PaymentMethodCreate(
        amo_id=amo.id,
        provider=models.PaymentProvider.PSP,
        external_ref="card_123",
        display_name="Test Card",
        card_last4="4242",
        card_exp_month=1,
        card_exp_year=2030,
        is_default=True,
    )
    first = services.add_payment_method(
        db_session,
        amo_id=amo.id,
        data=payload,
        idempotency_key="pm-1",
    )
    second = services.add_payment_method(
        db_session,
        amo_id=amo.id,
        data=payload,
        idempotency_key="pm-1",
    )
    assert first.id == second.id

    altered = payload.model_copy(update={"external_ref": "card_456"})
    with pytest.raises(services.IdempotencyError):
        services.add_payment_method(
            db_session,
            amo_id=amo.id,
            data=altered,
            idempotency_key="pm-1",
        )


def test_purchase_validates_server_pricing(db_session):
    amo = _create_amo(db_session, code="AMO4")
    sku = _create_sku(
        db_session,
        code="BASE-PURCHASE",
        term=models.BillingTerm.MONTHLY,
        amount_cents=9900,
    )

    license, ledger, invoice = services.purchase_sku(
        db_session,
        amo_id=amo.id,
        sku_code=sku.code,
        idempotency_key="purchase-1",
        expected_amount_cents=9900,
        expected_currency="USD",
    )

    assert license.status == models.LicenseStatus.ACTIVE
    assert ledger.amount_cents == 9900
    assert invoice.amount_cents == 9900

    with pytest.raises(ValueError):
        services.purchase_sku(
            db_session,
            amo_id=amo.id,
            sku_code=sku.code,
            idempotency_key="purchase-2",
            expected_amount_cents=100,
            expected_currency="USD",
        )


def test_webhook_signature_verification(db_session, monkeypatch):
    amo = _create_amo(db_session, code="AMO5")
    monkeypatch.setenv("PSP_WEBHOOK_SECRET", "super-secret")

    payload = {"id": "evt_123", "type": "payment.succeeded", "amo_id": amo.id}
    good_signature = hmac.new(
        b"super-secret",
        msg=json.dumps(payload, sort_keys=True).encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    with pytest.raises(HTTPException):
        services.handle_webhook(
            db_session,
            provider=models.PaymentProvider.PSP,
            payload=payload,
            signature="bad",
            external_event_id="evt_123",
            event_type="payment.succeeded",
        )


def test_start_trial_enforces_single_trial_per_sku(db_session):
    amo = _create_amo(db_session, code="AMO6")
    sku = _create_sku(db_session, code="BASE-TRIAL", term=models.BillingTerm.MONTHLY)

    first = services.start_trial(
        db_session,
        amo_id=amo.id,
        sku_code=sku.code,
        idempotency_key="trial-1",
    )
    assert first.status == models.LicenseStatus.TRIALING
    assert first.trial_started_at is not None

    with pytest.raises(ValueError):
        services.start_trial(
            db_session,
            amo_id=amo.id,
            sku_code=sku.code,
            idempotency_key="trial-2",
        )


def test_trial_auto_converts_when_payment_method_exists(db_session):
    amo = _create_amo(db_session, code="AMO7")
    sku = _create_sku(db_session, code="BASE-AUTO", term=models.BillingTerm.MONTHLY)
    license = services.start_trial(
        db_session,
        amo_id=amo.id,
        sku_code=sku.code,
        idempotency_key="trial-auto",
    )
    license.trial_ends_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.add(license)
    _add_payment_method(db_session, amo_id=amo.id, is_default=True)
    db_session.commit()

    result = services.roll_billing_periods_and_alert(
        db_session, as_of=datetime.now(timezone.utc)
    )

    db_session.refresh(license)
    assert license.status == models.LicenseStatus.ACTIVE
    assert license.current_period_start == license.trial_ends_at
    assert license.trial_grace_expires_at is None
    assert license.is_read_only is False
    assert result["expired_licenses"] == []


def test_trial_grace_sets_read_only_after_expiry(db_session):
    amo = _create_amo(db_session, code="AMO8")
    sku = _create_sku(db_session, code="BASE-GRACE", term=models.BillingTerm.MONTHLY)
    license = services.start_trial(
        db_session,
        amo_id=amo.id,
        sku_code=sku.code,
        idempotency_key="trial-grace",
    )
    grace_start = datetime.now(timezone.utc) - timedelta(days=1)
    license.trial_ends_at = grace_start
    db_session.add(license)
    db_session.commit()

    # First roll: set grace window
    services.roll_billing_periods_and_alert(db_session, as_of=grace_start + timedelta(minutes=1))
    db_session.refresh(license)
    assert license.status == models.LicenseStatus.EXPIRED
    assert license.trial_grace_expires_at is not None
    assert license.is_read_only is False

    # Second roll after grace: lock to read-only
    services.roll_billing_periods_and_alert(
        db_session, as_of=license.trial_grace_expires_at + timedelta(seconds=1)
    )
    db_session.refresh(license)
    assert license.is_read_only is True
