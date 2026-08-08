from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import commercial_access_policy, module_commerce, payment_data_policy


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
