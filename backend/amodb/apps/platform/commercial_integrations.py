from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.parse
from typing import Any, Callable

from . import saas_providers


_INSTALLED = False
_ORIGINAL_CHECK_PROVIDER: Callable[..., dict[str, Any]] | None = None

PAYSTACK_CODE = "paystack"
QUICKBOOKS_CODE = "quickbooks_online"


def _register_provider(definition: saas_providers.ProviderDefinition) -> None:
    """Register a provider without duplicating definitions across app reloads."""
    existing = tuple(item for item in saas_providers._PROVIDER_DEFINITIONS if item.code != definition.code)
    saas_providers._PROVIDER_DEFINITIONS = (*existing, definition)
    saas_providers.PROVIDERS[definition.code] = definition


def _bearer(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}


def _paystack_base(config: dict[str, Any]) -> str:
    return saas_providers._safe_url(str(config.get("api_base_url") or "https://api.paystack.co"))


def verify_paystack_signature(raw_payload: bytes, signature: str, secret_key: str) -> bool:
    """Verify Paystack's x-paystack-signature HMAC-SHA512 over the raw body."""
    if not raw_payload or not signature or not secret_key:
        return False
    expected = hmac.new(secret_key.encode("utf-8"), raw_payload, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def paystack_initialize_transaction(
    *,
    secret: dict[str, Any],
    config: dict[str, Any],
    email: str,
    amount_subunit: int,
    currency: str,
    reference: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    secret_key = str(secret.get("secret_key") or "").strip()
    if not secret_key:
        raise ValueError("Paystack secret_key is not configured")
    if not email:
        raise ValueError("A customer email is required for Paystack checkout")
    if amount_subunit <= 0:
        raise ValueError("Paystack amount must be positive")
    body: dict[str, Any] = {
        "email": email,
        "amount": str(int(amount_subunit)),
        "currency": str(currency or "KES").upper(),
        "reference": reference,
        "metadata": json.dumps(metadata, separators=(",", ":")),
    }
    callback_url = str(config.get("callback_url") or "").strip()
    if callback_url:
        body["callback_url"] = saas_providers._safe_url(callback_url, allowed_schemes=("https", "http"))
    status, response, elapsed = saas_providers._json_request(
        f"{_paystack_base(config)}/transaction/initialize",
        method="POST",
        headers=_bearer(secret_key),
        body=body,
        timeout=15,
    )
    if not 200 <= status < 300 or not isinstance(response, dict) or not bool(response.get("status")):
        raise RuntimeError(f"Paystack transaction initialization failed ({status})")
    data = response.get("data") or {}
    if not isinstance(data, dict) or not data.get("reference") or not data.get("authorization_url"):
        raise RuntimeError("Paystack did not return a transaction reference and authorization URL")
    return {
        "provider": PAYSTACK_CODE,
        "reference": str(data.get("reference")),
        "authorization_url": str(data.get("authorization_url")),
        "access_code": data.get("access_code"),
        "latency_ms": elapsed,
    }


def paystack_verify_transaction(
    *,
    secret: dict[str, Any],
    config: dict[str, Any],
    reference: str,
) -> dict[str, Any]:
    secret_key = str(secret.get("secret_key") or "").strip()
    if not secret_key:
        raise ValueError("Paystack secret_key is not configured")
    ref = urllib.parse.quote(str(reference or "").strip(), safe="-._=")
    if not ref:
        raise ValueError("Paystack transaction reference is required")
    status, response, elapsed = saas_providers._json_request(
        f"{_paystack_base(config)}/transaction/verify/{ref}",
        headers={"Authorization": f"Bearer {secret_key}"},
        timeout=12,
    )
    if not 200 <= status < 300 or not isinstance(response, dict) or not bool(response.get("status")):
        raise RuntimeError(f"Paystack transaction verification failed ({status})")
    data = response.get("data") or {}
    if not isinstance(data, dict):
        raise RuntimeError("Paystack verification response is invalid")
    return {"provider": PAYSTACK_CODE, "data": data, "latency_ms": elapsed}


def paystack_health(*, secret: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    secret_key = str(secret.get("secret_key") or "").strip()
    if not secret_key:
        raise ValueError("Paystack secret_key is not configured")
    status, response, elapsed = saas_providers._json_request(
        f"{_paystack_base(config)}/transaction?perPage=1",
        headers={"Authorization": f"Bearer {secret_key}"},
        timeout=8,
    )
    if not 200 <= status < 300:
        raise RuntimeError(f"Paystack health check failed ({status})")
    return {
        "ok": True,
        "provider": PAYSTACK_CODE,
        "latency_ms": elapsed,
        "reachable": isinstance(response, dict),
    }


def _mpesa_base(config: dict[str, Any]) -> str:
    environment = str(config.get("environment") or "sandbox").strip().lower()
    if environment == "production":
        return "https://api.safaricom.co.ke"
    return "https://sandbox.safaricom.co.ke"


def mpesa_access_token(*, secret: dict[str, Any], config: dict[str, Any]) -> str:
    consumer_key = str(config.get("consumer_key") or "").strip()
    consumer_secret = str(secret.get("consumer_secret") or "").strip()
    if not consumer_key or not consumer_secret:
        raise ValueError("Daraja consumer_key and consumer_secret are required")
    basic = base64.b64encode(f"{consumer_key}:{consumer_secret}".encode("utf-8")).decode("ascii")
    status, response, _ = saas_providers._json_request(
        f"{_mpesa_base(config)}/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": f"Basic {basic}"},
        timeout=10,
    )
    token = response.get("access_token") if isinstance(response, dict) else None
    if not 200 <= status < 300 or not token:
        raise RuntimeError(f"Daraja OAuth failed ({status})")
    return str(token)


def normalize_ke_phone(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]
    elif digits.startswith("7") and len(digits) == 9:
        digits = "254" + digits
    if not (digits.startswith("254") and 12 <= len(digits) <= 13):
        raise ValueError("M-PESA phone must be a Kenyan MSISDN, for example 2547XXXXXXXX")
    return digits


def _mpesa_password(shortcode: str, passkey: str, timestamp: str) -> str:
    raw = f"{shortcode}{passkey}{timestamp}".encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def mpesa_stk_push(
    *,
    secret: dict[str, Any],
    config: dict[str, Any],
    amount_kes: int,
    phone: str,
    account_reference: str,
    description: str,
    callback_url: str,
) -> dict[str, Any]:
    shortcode = str(config.get("shortcode") or "").strip()
    passkey = str(secret.get("passkey") or "").strip()
    if not shortcode or not passkey:
        raise ValueError("Daraja shortcode and passkey are required")
    if amount_kes <= 0:
        raise ValueError("M-PESA amount must be positive")
    phone = normalize_ke_phone(phone)
    timestamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    token = mpesa_access_token(secret=secret, config=config)
    body = {
        "BusinessShortCode": shortcode,
        "Password": _mpesa_password(shortcode, passkey, timestamp),
        "Timestamp": timestamp,
        "TransactionType": str(config.get("transaction_type") or "CustomerPayBillOnline"),
        "Amount": int(amount_kes),
        "PartyA": phone,
        "PartyB": shortcode,
        "PhoneNumber": phone,
        "CallBackURL": saas_providers._safe_url(callback_url),
        "AccountReference": str(account_reference or "AMOPORTAL")[:12],
        "TransactionDesc": str(description or "AMO Portal")[:13],
    }
    status, response, elapsed = saas_providers._json_request(
        f"{_mpesa_base(config)}/mpesa/stkpush/v1/processrequest",
        method="POST",
        headers=_bearer(token),
        body=body,
        timeout=15,
    )
    if not 200 <= status < 300 or not isinstance(response, dict):
        raise RuntimeError(f"M-PESA STK Push failed ({status})")
    checkout_id = str(response.get("CheckoutRequestID") or "").strip()
    merchant_id = str(response.get("MerchantRequestID") or "").strip()
    response_code = str(response.get("ResponseCode") or "")
    if not checkout_id or response_code not in {"0", ""}:
        raise RuntimeError(str(response.get("ResponseDescription") or "M-PESA rejected the STK Push"))
    return {
        "provider": "mpesa_daraja",
        "checkout_request_id": checkout_id,
        "merchant_request_id": merchant_id or None,
        "customer_message": response.get("CustomerMessage"),
        "latency_ms": elapsed,
    }


def mpesa_query_stk(
    *,
    secret: dict[str, Any],
    config: dict[str, Any],
    checkout_request_id: str,
) -> dict[str, Any]:
    shortcode = str(config.get("shortcode") or "").strip()
    passkey = str(secret.get("passkey") or "").strip()
    if not shortcode or not passkey:
        raise ValueError("Daraja shortcode and passkey are required")
    timestamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    token = mpesa_access_token(secret=secret, config=config)
    status, response, elapsed = saas_providers._json_request(
        f"{_mpesa_base(config)}/mpesa/stkpushquery/v1/query",
        method="POST",
        headers=_bearer(token),
        body={
            "BusinessShortCode": shortcode,
            "Password": _mpesa_password(shortcode, passkey, timestamp),
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        },
        timeout=15,
    )
    if not 200 <= status < 300 or not isinstance(response, dict):
        raise RuntimeError(f"M-PESA STK status query failed ({status})")
    return {"provider": "mpesa_daraja", "data": response, "latency_ms": elapsed}


def _quickbooks_api_base(config: dict[str, Any]) -> str:
    environment = str(config.get("environment") or "sandbox").strip().lower()
    default = "https://quickbooks.api.intuit.com" if environment == "production" else "https://sandbox-quickbooks.api.intuit.com"
    return saas_providers._safe_url(str(config.get("api_base_url") or default))


def quickbooks_authorization_url(*, config: dict[str, Any], state: str) -> str:
    client_id = str(config.get("client_id") or "").strip()
    redirect_uri = str(config.get("redirect_uri") or "").strip()
    if not client_id or not redirect_uri:
        raise ValueError("QuickBooks client_id and redirect_uri must be configured")
    params = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "scope": "com.intuit.quickbooks.accounting",
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return f"https://appcenter.intuit.com/connect/oauth2?{params}"


def _quickbooks_token_request(
    *,
    client_id: str,
    client_secret: str,
    fields: dict[str, str],
) -> dict[str, Any]:
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    body = urllib.parse.urlencode(fields).encode("utf-8")
    status, response, _ = saas_providers._json_request(
        "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        method="POST",
        headers={
            "Authorization": f"Basic {basic}",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body=body,
        timeout=15,
    )
    if not 200 <= status < 300 or not isinstance(response, dict) or not response.get("access_token"):
        raise RuntimeError(f"QuickBooks OAuth token exchange failed ({status})")
    return response


def quickbooks_exchange_code(
    *,
    secret: dict[str, Any],
    config: dict[str, Any],
    code: str,
) -> dict[str, Any]:
    client_id = str(config.get("client_id") or "").strip()
    client_secret = str(secret.get("client_secret") or "").strip()
    redirect_uri = str(config.get("redirect_uri") or "").strip()
    if not client_id or not client_secret or not redirect_uri:
        raise ValueError("QuickBooks client_id, client_secret and redirect_uri are required")
    return _quickbooks_token_request(
        client_id=client_id,
        client_secret=client_secret,
        fields={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
    )


def quickbooks_refresh_tokens(*, secret: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    client_id = str(config.get("client_id") or "").strip()
    client_secret = str(secret.get("client_secret") or "").strip()
    refresh_token = str(secret.get("refresh_token") or "").strip()
    if not client_id or not client_secret or not refresh_token:
        raise ValueError("QuickBooks client_id, client_secret and refresh_token are required")
    return _quickbooks_token_request(
        client_id=client_id,
        client_secret=client_secret,
        fields={"grant_type": "refresh_token", "refresh_token": refresh_token},
    )


def quickbooks_request(
    *,
    secret: dict[str, Any],
    config: dict[str, Any],
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | list[Any] | str, float]:
    access_token = str(secret.get("access_token") or "").strip()
    realm_id = str(config.get("realm_id") or "").strip()
    if not access_token or not realm_id:
        raise ValueError("QuickBooks is not linked: access_token and realm_id are required")
    minor = str(config.get("minor_version") or "75").strip()
    separator = "&" if "?" in path else "?"
    url = f"{_quickbooks_api_base(config)}/v3/company/{urllib.parse.quote(realm_id, safe='')}/{path}{separator}minorversion={urllib.parse.quote(minor, safe='')}"
    return saas_providers._json_request(
        url,
        method=method,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json", "Content-Type": "application/json"},
        body=body,
        timeout=20,
    )


def quickbooks_health(*, secret: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    realm_id = str(config.get("realm_id") or "").strip()
    if not realm_id:
        raise ValueError("QuickBooks realm_id is not configured; complete OAuth linking first")
    status, response, elapsed = quickbooks_request(
        secret=secret,
        config=config,
        method="GET",
        path=f"companyinfo/{urllib.parse.quote(realm_id, safe='')}",
    )
    if not 200 <= status < 300:
        raise RuntimeError(f"QuickBooks health check failed ({status})")
    return {"ok": True, "provider": QUICKBOOKS_CODE, "realm_id": realm_id, "latency_ms": elapsed, "reachable": isinstance(response, dict)}


def install_commercial_integrations() -> None:
    """Add payment/accounting adapters while preserving network hardening wrappers."""
    global _INSTALLED, _ORIGINAL_CHECK_PROVIDER
    if _INSTALLED:
        return

    _register_provider(
        saas_providers.ProviderDefinition(
            PAYSTACK_CODE,
            "Paystack",
            "PAYMENTS",
            ("secret_key",),
            ("api_base_url", "callback_url"),
            "Invoice-first card, bank and mobile-money collection through Paystack.",
        )
    )
    _register_provider(
        saas_providers.ProviderDefinition(
            QUICKBOOKS_CODE,
            "QuickBooks Online",
            "ACCOUNTING",
            ("client_secret", "access_token", "refresh_token", "access_token_expires_at", "refresh_token_expires_at"),
            (
                "client_id",
                "realm_id",
                "environment",
                "redirect_uri",
                "api_base_url",
                "minor_version",
                "income_item_id",
                "tax_code_ref",
                "deposit_account_id",
                "writeback_enabled",
            ),
            "OAuth-linked QuickBooks Online accounting export for portal invoices and settlements.",
        )
    )

    _ORIGINAL_CHECK_PROVIDER = saas_providers.check_provider

    def check_provider(
        provider: str,
        *,
        secret: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = str(provider or "").strip().lower()
        if normalized == PAYSTACK_CODE:
            return paystack_health(secret=secret, config=config)
        if normalized == QUICKBOOKS_CODE:
            return quickbooks_health(secret=secret, config=config)
        assert _ORIGINAL_CHECK_PROVIDER is not None
        return _ORIGINAL_CHECK_PROVIDER(provider, secret=secret, config=config)

    saas_providers.check_provider = check_provider
    _INSTALLED = True
