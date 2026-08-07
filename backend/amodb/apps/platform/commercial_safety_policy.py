from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import commercial_integrations, commercial_services, saas_providers, saas_services


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
    out of manual admin forms, refuses unproven scale claims, validates M-PESA
    callbacks before settlement processing, and prevents QuickBooks from silently
    posting a portal invoice in a different accounting currency.
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
    original_mpesa_callback = commercial_services._process_mpesa_callback
    original_enqueue_quickbooks = commercial_services.enqueue_quickbooks_sync

    def strict_capacity_readiness(db: Session) -> dict[str, Any]:
        result = dict(original_capacity(db))
        checks = dict(result.get("checks") or {})
        # A 1,000-concurrent-tenant claim is allowed only when every declared
        # production control is present AND an actual qualifying load run was
        # retained. No configuration subset can turn the badge green.
        result["status"] = "VERIFIED" if checks and all(checks.values()) else "NOT_YET_PROVEN"
        return result

    def guarded_mpesa_callback(db: Session, job) -> dict[str, Any]:
        callback = dict((job.payload_json or {}).get("callback") or {})
        body = callback.get("Body") or {}
        stk = body.get("stkCallback") if isinstance(body, dict) else None
        if not isinstance(stk, dict) or "ResultCode" not in stk:
            raise ValueError("M-PESA callback is missing ResultCode")
        return original_mpesa_callback(db, job)

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
    commercial_services._process_mpesa_callback = guarded_mpesa_callback
    commercial_services.enqueue_quickbooks_sync = guarded_quickbooks_sync
    _INSTALLED = True
