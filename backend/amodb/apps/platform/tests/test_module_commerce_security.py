from __future__ import annotations

import inspect
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import (
    commercial_access_policy,
    commercial_services,
    module_commerce,
    payment_data_policy,
    payment_transport_policy,
)
from amodb.database import WriteSessionLocal


ROOT = Path(__file__).resolve().parents[5]
FRONTEND = ROOT / "frontend" / "src"


def test_first_party_module_graph_has_explicit_commercial_boundaries() -> None:
    catalog = module_commerce.FIRST_PARTY_MODULES
    assert catalog["quality"]["kind"] == "STANDALONE"
    assert catalog["training"]["kind"] == "STANDALONE"
    assert catalog["fleet"]["kind"] == "STANDALONE"
    assert catalog["work"]["hard_requires"] == ["fleet"]
    assert set(catalog["reliability"]["hard_requires"]) == {"fleet", "work"}
    assert set(catalog["procurement"]["hard_requires"]) == {"finance", "inventory"}
    assert set(catalog["finance_inventory"]["included_modules"]) == {"finance", "inventory", "procurement"}
    assert catalog["rostering"]["customer_selectable"] is False


def test_bundle_activation_expands_to_enforceable_children() -> None:
    catalog = {
        "suite": {"kind": "BUNDLE", "included_modules": ["fleet", "work"]},
        "fleet": {"kind": "STANDALONE", "included_modules": []},
        "work": {"kind": "ADD_ON", "included_modules": []},
    }
    assert module_commerce.expand_activation_codes(catalog, "suite") == ["fleet", "work"]


def test_legacy_direct_purchase_and_manual_payment_method_attachment_are_blocked() -> None:
    with pytest.raises(payment_data_policy.LegacyBillingMutationDisabled, match="verified hosted payment workflow"):
        payment_data_policy._blocked_purchase()
    with pytest.raises(payment_data_policy.LegacyBillingMutationDisabled, match="configured payment provider"):
        payment_data_policy._blocked_payment_method()


def test_expired_trial_does_not_become_paid_from_stored_payment_reference() -> None:
    now = datetime.now(timezone.utc)
    license = account_models.TenantLicense(
        id="lic-payment-safety",
        amo_id="tenant-payment-safety",
        sku_id="sku-payment-safety",
        term=account_models.BillingTerm.MONTHLY,
        status=account_models.LicenseStatus.TRIALING,
        trial_started_at=now - timedelta(days=15),
        trial_ends_at=now - timedelta(minutes=1),
        current_period_start=now - timedelta(days=15),
        current_period_end=now - timedelta(minutes=1),
        is_read_only=False,
    )
    projection = commercial_access_policy._project_subscription(
        license,
        now=now,
        has_payment_method=True,
        has_overdue_invoice=False,
    )
    assert projection.status == account_models.LicenseStatus.EXPIRED
    assert projection.status != account_models.LicenseStatus.ACTIVE


def test_paystack_durable_webhook_payload_is_data_minimized() -> None:
    source = inspect.getsource(payment_data_policy._safe_paystack_webhook)
    assert '"event": payload' not in source
    assert '"reference": reference' in source
    assert '"invoice_id": invoice_id' in source
    assert '"credential_id": credential.id' in source


def test_mpesa_durable_callback_does_not_retain_full_callback_or_phone() -> None:
    source = inspect.getsource(payment_transport_policy.minimized_mpesa_callback)
    assert '"callback": payload' not in source
    assert '"PhoneNumber"' not in source
    assert '"checkout_request_id": checkout_request_id' in source
    assert '"receipt_number": receipt' in source
    assert '"amount_kes":' in source


def test_provider_hosted_redirects_are_allowlisted() -> None:
    assert payment_transport_policy._trusted_hosted_redirect(
        "https://checkout.paystack.com/abc123",
        provider="Paystack",
        allowed_hosts={"checkout.paystack.com"},
    ).startswith("https://checkout.paystack.com/")
    with pytest.raises(RuntimeError, match="untrusted hosted checkout URL"):
        payment_transport_policy._trusted_hosted_redirect(
            "https://paystack.example.evil.test/abc123",
            provider="Paystack",
            allowed_hosts={"checkout.paystack.com"},
        )
    with pytest.raises(RuntimeError, match="untrusted hosted checkout URL"):
        payment_transport_policy._trusted_hosted_redirect(
            "http://checkout.paystack.com/abc123",
            provider="Paystack",
            allowed_hosts={"checkout.paystack.com"},
        )


def test_production_provider_return_url_requires_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValueError, match="must use HTTPS"):
        payment_transport_policy._require_secure_callback(
            "http://portal.example/payments/return",
            label="Provider callback",
        )
    payment_transport_policy._require_secure_callback(
        "https://portal.example/payments/return",
        label="Provider callback",
    )


def test_tenant_frontend_has_no_manual_card_or_payment_token_entry() -> None:
    legacy = (FRONTEND / "pages" / "SubscriptionManagementPage.tsx").read_text(encoding="utf-8")
    billing = (FRONTEND / "pages" / "AdminBillingPage.tsx").read_text(encoding="utf-8")
    combined = f"{legacy}\n{billing}".lower()
    for forbidden in [
        'id="externalref"',
        'id="last4"',
        'id="expmonth"',
        'id="expyear"',
        'name="card_number"',
        'name="cvv"',
        'name="cvc"',
        'payment token / reference',
    ]:
        assert forbidden not in combined
    assert "hosted card/bank checkout" in billing.lower()
    assert "never asks for or stores a card number" in billing.lower()


def test_legacy_subscription_page_redirects_to_canonical_billing() -> None:
    source = (FRONTEND / "pages" / "SubscriptionManagementPage.tsx").read_text(encoding="utf-8")
    assert "/admin/billing" in source
    assert "purchaseSubscription" not in source
    assert "addPaymentMethod" not in source


def test_paid_legacy_period_requires_invoice_and_verified_settlement() -> None:
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(timezone.utc)
    amo_id = f"amo-renew-{suffix}"
    sku_id = f"sku-renew-{suffix}"
    license_id = f"lic-renew-{suffix}"
    db = WriteSessionLocal()
    try:
        db.add(
            account_models.AMO(
                id=amo_id,
                amo_code=f"RN{suffix[:8].upper()}",
                login_slug=f"renew-{suffix}",
                name=f"Renewal Test {suffix}",
                country="KE",
                is_demo=True,
                is_active=True,
            )
        )
        db.add(
            account_models.CatalogSKU(
                id=sku_id,
                code=f"RENEW_{suffix.upper()}",
                name="Paid renewal test",
                term=account_models.BillingTerm.MONTHLY,
                trial_days=0,
                amount_cents=125000,
                currency="KES",
                is_active=True,
            )
        )
        db.add(
            account_models.TenantLicense(
                id=license_id,
                amo_id=amo_id,
                sku_id=sku_id,
                term=account_models.BillingTerm.MONTHLY,
                status=account_models.LicenseStatus.ACTIVE,
                is_read_only=False,
                current_period_start=now - timedelta(days=31),
                current_period_end=now - timedelta(minutes=5),
            )
        )
        db.commit()

        payment_data_policy._secure_billing_maintenance(db, as_of=now)
        db.commit()
        license = db.get(account_models.TenantLicense, license_id)
        invoice = (
            db.query(account_models.BillingInvoice)
            .filter(
                account_models.BillingInvoice.amo_id == amo_id,
                account_models.BillingInvoice.license_id == license_id,
                account_models.BillingInvoice.status == account_models.InvoiceStatus.PENDING,
            )
            .one()
        )
        assert license is not None
        assert license.status == account_models.LicenseStatus.EXPIRED
        assert license.is_read_only is True
        assert invoice.amount_cents == 125000
        assert invoice.currency == "KES"

        commercial_services.mark_invoice_paid(
            db,
            invoice_id=invoice.id,
            provider="offline",
            provider_reference=f"BANK-{suffix}",
            actor_user_id=None,
            verified_amount_cents=125000,
            verified_currency="KES",
            reason="Integration-test verified renewal settlement",
        )
        db.expire_all()
        renewed = db.get(account_models.TenantLicense, license_id)
        paid_invoice = db.get(account_models.BillingInvoice, invoice.id)
        assert renewed is not None
        assert renewed.status == account_models.LicenseStatus.ACTIVE
        assert renewed.is_read_only is False
        assert renewed.current_period_end is not None
        renewed_end = renewed.current_period_end
        if renewed_end.tzinfo is None:
            renewed_end = renewed_end.replace(tzinfo=timezone.utc)
        assert renewed_end > now
        assert paid_invoice is not None
        assert paid_invoice.status == account_models.InvoiceStatus.PAID
        assert paid_invoice.paid_at is not None
    finally:
        db.close()
