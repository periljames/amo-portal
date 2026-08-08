from __future__ import annotations

import hmac
import os
import urllib.parse
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import commercial_integrations as integrations
from . import commercial_services, saas_queue, saas_services


_INSTALLED = False
_ORIGINAL_PAYSTACK_INITIALIZE = integrations.paystack_initialize_transaction


def _production_runtime() -> bool:
    return str(os.getenv("APP_ENV") or "production").strip().lower() in {
        "production",
        "prod",
        "staging",
        "stage",
    }


def _require_secure_callback(url: str, *, label: str) -> None:
    if not url:
        return
    parsed = urllib.parse.urlsplit(url)
    if not parsed.hostname:
        raise ValueError(f"{label} must be an absolute URL")
    if _production_runtime() and parsed.scheme.lower() != "https":
        raise ValueError(f"{label} must use HTTPS outside local/test environments")


def _trusted_paystack_checkout(url: str) -> str:
    parsed = urllib.parse.urlsplit(str(url or "").strip())
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or hostname not in {
        "checkout.paystack.com",
        "standard.paystack.co",
    }:
        raise RuntimeError("Paystack returned an untrusted checkout URL")
    if parsed.username or parsed.password:
        raise RuntimeError("Paystack checkout URL must not contain user credentials")
    return urllib.parse.urlunsplit(parsed)


def guarded_paystack_initialize_transaction(**kwargs) -> dict[str, Any]:
    config = dict(kwargs.get("config") or {})
    _require_secure_callback(str(config.get("callback_url") or "").strip(), label="Paystack callback_url")
    result = dict(_ORIGINAL_PAYSTACK_INITIALIZE(**kwargs))
    result["authorization_url"] = _trusted_paystack_checkout(str(result.get("authorization_url") or ""))
    return result


def _settlement_credential(
    db: Session,
    *,
    provider: str,
    tenant_id: str,
    label: str,
):
    row = saas_services.get_provider_credential(db, provider=provider, tenant_id=tenant_id)
    if row is None:
        raise ValueError(f"{label} is not configured")
    state = str(row.status or "").strip().upper()
    if state in {"DISABLED", "NOT_CONFIGURED"}:
        raise PermissionError(f"{label} settlement rejected because the provider is disabled")
    return row


def minimized_mpesa_callback(
    db: Session,
    *,
    tenant_id: str,
    invoice_id: str,
    token: str,
    payload: dict[str, Any],
):
    account = commercial_services._billing_account(db, tenant_id=tenant_id, provider="mpesa_daraja")
    if account is None or str(account.status or "").upper() != "PAYMENT_PENDING":
        raise ValueError("No pending M-PESA payment exists for this tenant")
    metadata = dict(account.metadata_json or {})
    if str(metadata.get("pending_invoice_id") or "") != invoice_id:
        raise ValueError("M-PESA callback invoice does not match the pending collection")
    if not hmac.compare_digest(str(metadata.get("callback_token") or ""), str(token or "")):
        raise PermissionError("Invalid M-PESA callback token")

    body = payload.get("Body") or {}
    stk = body.get("stkCallback") if isinstance(body, dict) else None
    if not isinstance(stk, dict) or "ResultCode" not in stk:
        raise ValueError("M-PESA callback is missing ResultCode")
    checkout_request_id = str(stk.get("CheckoutRequestID") or "").strip()
    if not checkout_request_id or checkout_request_id != str(metadata.get("checkout_request_id") or ""):
        raise ValueError("M-PESA checkout request does not match the pending collection")

    result_code = int(stk.get("ResultCode"))
    result_desc = str(stk.get("ResultDesc") or "")[:500]
    callback_items = commercial_services._mpesa_callback_items(stk) if result_code == 0 else {}
    amount = callback_items.get("Amount")
    receipt = str(callback_items.get("MpesaReceiptNumber") or "").strip() or None

    # Do not retain the full Safaricom callback. Phone number, transaction date
    # and other personal/provider metadata are unnecessary for settlement once
    # the callback has been authenticated and correlated. The server-side query
    # remains authoritative before money/access state is changed.
    return saas_queue.enqueue_job(
        db,
        job_type="MPESA_CALLBACK",
        queue_name="billing",
        tenant_id=tenant_id,
        payload={
            "invoice_id": invoice_id,
            "checkout_request_id": checkout_request_id,
            "result_code": result_code,
            "result_desc": result_desc,
            "amount_kes": str(amount) if amount is not None else None,
            "receipt_number": receipt,
            "data_minimized": True,
        },
        idempotency_key=f"mpesa:{checkout_request_id}:{result_code}",
        correlation_id=checkout_request_id,
        max_attempts=5,
        priority=5,
    )


def process_minimized_mpesa_callback(db: Session, job) -> dict[str, Any]:
    payload = dict(job.payload_json or {})
    tenant_id = str(job.tenant_id or "")
    invoice = commercial_services._invoice(
        db,
        str(payload.get("invoice_id") or ""),
        tenant_id=tenant_id,
        lock=True,
    )
    account = commercial_services._billing_account(
        db,
        tenant_id=tenant_id,
        provider="mpesa_daraja",
        lock=True,
    )
    if account is None:
        raise ValueError("M-PESA billing account is missing")
    metadata = dict(account.metadata_json or {})
    checkout_request_id = str(payload.get("checkout_request_id") or "")
    if checkout_request_id != str(metadata.get("checkout_request_id") or ""):
        raise ValueError("M-PESA callback does not match the pending checkout")

    result_code = int(payload.get("result_code"))
    if result_code != 0:
        account.status = "PAYMENT_FAILED"
        metadata.update(
            {
                "last_result_code": result_code,
                "last_result_desc": str(payload.get("result_desc") or "")[:500],
            }
        )
        account.metadata_json = metadata
        db.flush()
        return {
            "paid": False,
            "result_code": result_code,
            "result_desc": payload.get("result_desc"),
        }

    credential = _settlement_credential(
        db,
        provider="mpesa_daraja",
        tenant_id=tenant_id,
        label="M-PESA Daraja",
    )
    verification = integrations.mpesa_query_stk(
        secret=saas_services.provider_secrets(credential),
        config=credential.config_json or {},
        checkout_request_id=checkout_request_id,
    )
    verified = verification.get("data") or {}
    if not isinstance(verified, dict) or str(verified.get("ResultCode") or "") != "0":
        raise ValueError("M-PESA server-side STK query does not confirm successful settlement")

    receipt = str(payload.get("receipt_number") or "").strip()
    if not receipt:
        raise ValueError("Successful M-PESA callback is missing MpesaReceiptNumber")
    amount = Decimal(str(payload.get("amount_kes") or "0"))
    if amount <= 0:
        raise ValueError("Successful M-PESA callback is missing a positive settlement amount")
    amount_cents = int((amount * Decimal("100")).quantize(Decimal("1")))
    paid = commercial_services.mark_invoice_paid(
        db,
        invoice_id=invoice.id,
        provider="mpesa_daraja",
        provider_reference=receipt,
        actor_user_id=job.created_by,
        verified_amount_cents=amount_cents,
        verified_currency="KES",
        reason="M-PESA STK settlement confirmed by minimized callback and server-side query",
    )
    return {"paid": True, "receipt": receipt, "invoice": paid}


def install_payment_transport_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    integrations.paystack_initialize_transaction = guarded_paystack_initialize_transaction
    commercial_services.record_mpesa_callback = minimized_mpesa_callback
    commercial_services._process_mpesa_callback = process_minimized_mpesa_callback
    _INSTALLED = True
