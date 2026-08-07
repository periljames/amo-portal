from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import (
    commercial_integrations,
    commercial_services,
    saas_providers,
    saas_queue,
    saas_services,
)


_INSTALLED = False


def _replace_provider_definition(
    definition: saas_providers.ProviderDefinition,
) -> None:
    existing = tuple(
        item
        for item in saas_providers._PROVIDER_DEFINITIONS
        if item.code != definition.code
    )
    saas_providers._PROVIDER_DEFINITIONS = (*existing, definition)
    saas_providers.PROVIDERS[definition.code] = definition


def install_commercial_safety_policy() -> None:
    """Apply commercial safety gates without widening the legacy billing API.

    This installer is intentionally small and additive. It keeps provider tokens
    out of manual admin forms, refuses unproven scale claims, validates settlement
    callbacks independently of outbound health alarms, and prevents QuickBooks
    from silently posting a portal invoice in a different accounting currency.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    # OAuth access/refresh tokens are stored programmatically after Intuit's
    # callback. Superadmins should only ever type the app client secret.
    _replace_provider_definition(
        saas_providers.ProviderDefinition(
            commercial_integrations.QUICKBOOKS_CODE,
            "QuickBooks Online",
            "ACCOUNTING",
            ("client_secret",),
            (
                "client_id",
                "realm_id",
                "environment",
                "redirect_uri",
                "api_base_url",
                "minor_version",
                "home_currency",
                "income_item_id",
                "tax_code_ref",
                "deposit_account_id",
                "writeback_enabled",
            ),
            "OAuth-linked QuickBooks Online accounting export for portal invoices and settlements.",
        )
    )

    original_capacity = commercial_services.capacity_readiness
    original_enqueue_quickbooks = commercial_services.enqueue_quickbooks_sync

    def strict_capacity_readiness(db: Session) -> dict[str, Any]:
        result = dict(original_capacity(db))
        checks = dict(result.get("checks") or {})
        # A 1,000-concurrent-tenant claim is allowed only when every declared
        # production control is present AND an actual qualifying load run was
        # retained. No configuration subset can turn the badge green.
        result["status"] = "VERIFIED" if checks and all(checks.values()) else "NOT_YET_PROVEN"
        return result

    def guarded_paystack_webhook(
        db: Session,
        *,
        raw_payload: bytes,
        signature: str,
    ):
        """Authenticate inbound settlement independently of outbound health state.

        A temporary health-check failure must not make us discard a legitimate
        signed payment callback. Explicitly DISABLED credentials still reject all
        callbacks. The worker subsequently re-verifies the transaction with
        Paystack before any invoice/module mutation.
        """
        payload = json.loads(raw_payload.decode("utf-8"))
        event_type = str(payload.get("event") or "").strip().lower()
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            raise ValueError("Paystack event data is invalid")
        metadata = commercial_services._metadata_dict(data.get("metadata"))
        tenant_id = str(metadata.get("tenant_id") or "").strip()
        invoice_id = str(metadata.get("portal_invoice_id") or "").strip()
        reference = str(data.get("reference") or "").strip()
        if not tenant_id or not invoice_id or not reference:
            raise ValueError(
                "Paystack event is missing portal tenant, invoice or reference metadata"
            )
        invoice = (
            db.query(account_models.BillingInvoice)
            .filter(
                account_models.BillingInvoice.id == invoice_id,
                account_models.BillingInvoice.amo_id == tenant_id,
            )
            .first()
        )
        if invoice is None:
            raise ValueError("Paystack callback invoice does not belong to the declared tenant")
        credential = saas_services.get_provider_credential(
            db,
            provider=commercial_integrations.PAYSTACK_CODE,
            tenant_id=tenant_id,
        )
        if credential is None:
            raise ValueError("Paystack is not configured")
        credential_status = str(credential.status or "").strip().upper()
        if credential_status in {"DISABLED", "NOT_CONFIGURED"}:
            raise PermissionError("Paystack callback rejected because the provider is disabled")
        secret = saas_services.provider_secrets(credential)
        if not commercial_integrations.verify_paystack_signature(
            raw_payload,
            signature,
            str(secret.get("secret_key") or ""),
        ):
            raise PermissionError("Invalid Paystack webhook signature")
        return saas_queue.enqueue_job(
            db,
            job_type="PAYSTACK_WEBHOOK",
            queue_name="billing",
            tenant_id=tenant_id,
            payload={
                "event": payload,
                "event_type": event_type,
                "credential_id": credential.id,
                "invoice_id": invoice_id,
                "reference": reference,
            },
            idempotency_key=f"{event_type}:{reference}",
            correlation_id=reference,
            max_attempts=6,
            priority=5,
        )

    def guarded_mpesa_callback(db: Session, job) -> dict[str, Any]:
        """Confirm a successful Daraja callback even if provider health is stale.

        The callback token and CheckoutRequestID were already checked at ingress.
        A success is still cross-checked using Daraja's server-side STK query and
        invoice amount before settlement. DISABLED credentials remain blocked.
        """
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

        callback = payload.get("callback") or {}
        body = callback.get("Body") or {}
        stk = body.get("stkCallback") if isinstance(body, dict) else None
        if not isinstance(stk, dict) or "ResultCode" not in stk:
            raise ValueError("M-PESA callback is missing ResultCode")
        callback_code = int(stk["ResultCode"])
        if callback_code != 0:
            account.status = "PAYMENT_FAILED"
            metadata.update(
                {
                    "last_result_code": callback_code,
                    "last_result_desc": stk.get("ResultDesc"),
                }
            )
            account.metadata_json = metadata
            db.flush()
            return {
                "paid": False,
                "result_code": callback_code,
                "result_desc": stk.get("ResultDesc"),
            }

        credential = saas_services.get_provider_credential(
            db,
            provider="mpesa_daraja",
            tenant_id=tenant_id,
        )
        if credential is None:
            raise ValueError("M-PESA Daraja is not configured")
        credential_status = str(credential.status or "").strip().upper()
        if credential_status in {"DISABLED", "NOT_CONFIGURED"}:
            raise PermissionError("M-PESA settlement rejected because the provider is disabled")
        verification = commercial_integrations.mpesa_query_stk(
            secret=saas_services.provider_secrets(credential),
            config=credential.config_json or {},
            checkout_request_id=checkout_request_id,
        )
        verified = verification.get("data") or {}
        if not isinstance(verified, dict) or str(verified.get("ResultCode") or "") != "0":
            raise ValueError(
                "M-PESA server-side STK query does not confirm successful settlement"
            )
        callback_items = commercial_services._mpesa_callback_items(stk)
        receipt = str(callback_items.get("MpesaReceiptNumber") or "").strip()
        if not receipt:
            raise ValueError("Successful M-PESA callback is missing MpesaReceiptNumber")
        paid_amount_kes = Decimal(str(callback_items.get("Amount") or "0"))
        verified_amount_cents = int(
            (paid_amount_kes * Decimal("100")).quantize(Decimal("1"))
        )
        paid = commercial_services.mark_invoice_paid(
            db,
            invoice_id=invoice.id,
            provider="mpesa_daraja",
            provider_reference=receipt,
            actor_user_id=job.created_by,
            verified_amount_cents=verified_amount_cents,
            verified_currency="KES",
            reason=(
                "M-PESA STK settlement confirmed by callback and server-side query"
            ),
        )
        return {"paid": True, "receipt": receipt, "invoice": paid}

    def guarded_quickbooks_sync(
        db: Session,
        *,
        invoice_id: str,
        actor_user_id: str,
    ):
        invoice = db.get(account_models.BillingInvoice, invoice_id)
        if invoice is None:
            raise ValueError("Invoice not found")
        credential = saas_services.get_provider_credential(
            db,
            provider=commercial_integrations.QUICKBOOKS_CODE,
            tenant_id=None,
            allow_platform_fallback=False,
        )
        if credential is None:
            raise ValueError("QuickBooks Online provider is not configured")
        config = dict(credential.config_json or {})
        home_currency = str(config.get("home_currency") or "").strip().upper()
        if not home_currency:
            raise ValueError(
                "QuickBooks home_currency must be configured before writeback is enabled"
            )
        invoice_currency = str(invoice.currency or "USD").strip().upper()
        if invoice_currency != home_currency:
            raise ValueError(
                "QuickBooks writeback is blocked for a non-home-currency invoice. "
                "Configure a deliberate multi-currency accounting mapping before expanding this boundary."
            )
        return original_enqueue_quickbooks(
            db,
            invoice_id=invoice_id,
            actor_user_id=actor_user_id,
        )

    commercial_services.capacity_readiness = strict_capacity_readiness
    commercial_services.record_paystack_webhook = guarded_paystack_webhook
    commercial_services._process_mpesa_callback = guarded_mpesa_callback
    commercial_services.enqueue_quickbooks_sync = guarded_quickbooks_sync
    _INSTALLED = True
