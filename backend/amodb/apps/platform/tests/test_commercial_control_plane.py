from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import (
    commercial_access_policy,
    commercial_integrations,
    commercial_invoice_policy,
    commercial_policy,
    saas_providers,
)


def test_commercial_provider_catalog_is_registered() -> None:
    catalog = {row["provider"]: row for row in saas_providers.provider_catalog()}
    assert "paystack" in catalog
    assert "quickbooks_online" in catalog
    assert catalog["paystack"]["category"] == "PAYMENTS"
    assert catalog["quickbooks_online"]["category"] == "ACCOUNTING"
    # OAuth refresh/access tokens are written by the callback and must never be
    # typed or overwritten through the super-admin integration secret form.
    assert catalog["quickbooks_online"]["secret_fields"] == ["client_secret"]


def test_paystack_signature_is_hmac_sha512_of_raw_body() -> None:
    body = b'{"event":"charge.success","data":{"reference":"ref-1"}}'
    secret = "sk_test_example"
    signature = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
    assert commercial_integrations.verify_paystack_signature(body, signature, secret)
    assert not commercial_integrations.verify_paystack_signature(body + b"x", signature, secret)
    assert not commercial_integrations.verify_paystack_signature(body, signature, "wrong")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0712345678", "254712345678"),
        ("712345678", "254712345678"),
        ("254712345678", "254712345678"),
        ("+254 712 345 678", "254712345678"),
    ],
)
def test_mpesa_phone_normalization(raw: str, expected: str) -> None:
    assert commercial_integrations.normalize_ke_phone(raw) == expected


def test_mpesa_phone_rejects_non_kenyan_number() -> None:
    with pytest.raises(ValueError, match="Kenyan MSISDN"):
        commercial_integrations.normalize_ke_phone("+1 415 555 0100")


def test_quickbooks_authorization_url_uses_accounting_scope_and_state() -> None:
    url = commercial_integrations.quickbooks_authorization_url(
        config={"client_id": "client-1", "redirect_uri": "https://portal.example/platform/commercial/quickbooks/callback"},
        state="signed-state",
    )
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "appcenter.intuit.com"
    assert query["scope"] == ["com.intuit.quickbooks.accounting"]
    assert query["state"] == ["signed-state"]
    assert query["response_type"] == ["code"]


def test_lifecycle_conflict_requires_commercial_evidence() -> None:
    assert commercial_policy._commercial_state(
        license_status="ACTIVE",
        module_enabled=0,
        module_trial=0,
        provider_statuses={},
    ) == "CONNECTED"
    assert commercial_policy._is_conflict(administrative_active=False, commercial_status="CONNECTED")
    assert not commercial_policy._is_conflict(administrative_active=False, commercial_status="UNCONNECTED")
    assert not commercial_policy._is_conflict(administrative_active=True, commercial_status="CONNECTED")


def test_past_due_is_not_mislabeled_as_disconnected() -> None:
    assert commercial_policy._commercial_state(
        license_status=None,
        module_enabled=0,
        module_trial=0,
        provider_statuses={"stripe": "PAST_DUE"},
    ) == "PAST_DUE"


def test_access_projection_keeps_expired_trial_in_grace_without_payment_method() -> None:
    now = datetime.now(timezone.utc)
    license = account_models.TenantLicense(
        id="lic-access-projection",
        amo_id="tenant-access-projection",
        sku_id="sku-access-projection",
        term=account_models.BillingTerm.MONTHLY,
        status=account_models.LicenseStatus.TRIALING,
        trial_started_at=now - timedelta(days=15),
        trial_ends_at=now - timedelta(hours=1),
        current_period_start=now - timedelta(days=15),
        current_period_end=now - timedelta(hours=1),
        is_read_only=False,
    )
    projection = commercial_access_policy._project_subscription(
        license,
        now=now,
        has_payment_method=False,
        has_overdue_invoice=False,
    )
    assert projection.status == account_models.LicenseStatus.EXPIRED
    assert projection.is_read_only is False
    assert projection.trial_grace_expires_at is not None
    assert projection.trial_grace_expires_at > now


def test_access_projection_locks_overdue_active_subscription() -> None:
    now = datetime.now(timezone.utc)
    license = account_models.TenantLicense(
        id="lic-overdue-projection",
        amo_id="tenant-overdue-projection",
        sku_id="sku-overdue-projection",
        term=account_models.BillingTerm.ANNUAL,
        status=account_models.LicenseStatus.ACTIVE,
        current_period_start=now - timedelta(days=10),
        current_period_end=now + timedelta(days=355),
        is_read_only=False,
    )
    projection = commercial_access_policy._project_subscription(
        license,
        now=now,
        has_payment_method=True,
        has_overdue_invoice=True,
    )
    assert projection.status == account_models.LicenseStatus.ACTIVE
    assert projection.is_read_only is True


def test_tax_rounding_uses_commercial_half_up() -> None:
    # Python's built-in round() would use banker's rounding here. Billing cents
    # require a deterministic half-up policy.
    assert commercial_invoice_policy.tax_cents(1, 5000) == 1
    assert commercial_invoice_policy.tax_cents(1000, 1600) == 160


def test_invoice_breakdown_uses_structured_tax_snapshot() -> None:
    invoice = account_models.BillingInvoice(
        id="invoice-tax-breakdown",
        amo_id="tenant-tax-breakdown",
        amount_cents=11600,
        currency="KES",
        status=account_models.InvoiceStatus.PENDING,
        idempotency_key="invoice-tax-breakdown",
        description=json.dumps(
            {
                "subtotal_cents": 10000,
                "tax_rate_bps": 1600,
                "tax_amount_cents": 1600,
                "tax_mode": "EXCLUSIVE",
                "total_cents": 11600,
            }
        ),
    )
    breakdown = commercial_invoice_policy.invoice_breakdown(invoice)
    assert breakdown["subtotal_cents"] == 10000
    assert breakdown["tax_amount_cents"] == 1600
    assert breakdown["total_cents"] == 11600
    assert breakdown["tax_rate_bps"] == 1600


def test_invoice_breakdown_refuses_unreconciled_snapshot() -> None:
    invoice = account_models.BillingInvoice(
        id="invoice-tax-mismatch",
        amo_id="tenant-tax-mismatch",
        amount_cents=11600,
        currency="KES",
        status=account_models.InvoiceStatus.PENDING,
        idempotency_key="invoice-tax-mismatch",
        description=json.dumps(
            {
                "subtotal_cents": 10000,
                "tax_rate_bps": 1600,
                "tax_amount_cents": 1500,
                "tax_mode": "EXCLUSIVE",
                "total_cents": 11500,
            }
        ),
    )
    with pytest.raises(ValueError, match="does not reconcile"):
        commercial_invoice_policy.invoice_breakdown(invoice)
