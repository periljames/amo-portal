from __future__ import annotations

import hashlib
import hmac
from urllib.parse import parse_qs, urlparse

import pytest

from amodb.apps.platform import commercial_integrations, commercial_policy, saas_providers


def test_commercial_provider_catalog_is_registered() -> None:
    catalog = {row["provider"]: row for row in saas_providers.provider_catalog()}
    assert "paystack" in catalog
    assert "quickbooks_online" in catalog
    assert catalog["paystack"]["category"] == "PAYMENTS"
    assert catalog["quickbooks_online"]["category"] == "ACCOUNTING"


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
