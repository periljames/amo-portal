from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import commercial_services, module_commerce


_INSTALLED = False


def _details(invoice: account_models.BillingInvoice) -> dict[str, Any]:
    raw = invoice.description
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _period_delta(term: str) -> timedelta:
    normalized = str(term or "MONTHLY").strip().upper()
    if normalized == "ANNUAL":
        return timedelta(days=365)
    if normalized == "BI_ANNUAL":
        return timedelta(days=182)
    return timedelta(days=30)


def _metadata(row: account_models.ModuleSubscription) -> dict[str, Any]:
    if not row.metadata_json:
        return {}
    try:
        value = json.loads(row.metadata_json)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def enable_paid_module_contract(
    db: Session,
    *,
    invoice: account_models.BillingInvoice,
    provider: str,
    provider_reference: str,
) -> account_models.ModuleSubscription | None:
    commercial = _details(invoice)
    root_code = module_commerce.normalize_code(str(commercial.get("module_code") or ""))
    if not root_code:
        return None

    activation_codes = [
        module_commerce.normalize_code(str(value))
        for value in (commercial.get("activation_codes") or [])
        if str(value).strip()
    ]
    codes: list[str] = []
    for code in [root_code, *activation_codes]:
        if code and code not in codes:
            codes.append(code)

    now = datetime.now(timezone.utc)
    term = str(commercial.get("billing_term") or "MONTHLY").strip().upper()
    delta = _period_delta(term)
    subtotal_cents = int(commercial.get("subtotal_cents") or invoice.amount_cents or 0)
    tax_amount_cents = int(commercial.get("tax_amount_cents") or 0)
    tax_rate_bps = int(commercial.get("tax_rate_bps") or 0)
    root_row: account_models.ModuleSubscription | None = None

    for code in codes:
        row = (
            db.query(account_models.ModuleSubscription)
            .filter(
                account_models.ModuleSubscription.amo_id == invoice.amo_id,
                account_models.ModuleSubscription.module_code == code,
            )
            .first()
        )
        if row is None:
            row = account_models.ModuleSubscription(
                amo_id=invoice.amo_id,
                module_code=code,
                status=account_models.ModuleSubscriptionStatus.ENABLED,
            )
            db.add(row)

        previous_end = row.effective_to
        if previous_end is not None and previous_end.tzinfo is None:
            previous_end = previous_end.replace(tzinfo=timezone.utc)
        period_start = previous_end if previous_end and previous_end > now else now
        period_end = period_start + delta

        row.status = account_models.ModuleSubscriptionStatus.ENABLED
        row.plan_code = str(commercial.get("plan_code") or row.plan_code or "STANDARD").strip().upper()
        row.effective_from = row.effective_from or period_start
        row.effective_to = period_end

        metadata = _metadata(row)
        metadata.update(
            {
                "commercial_offer_only": False,
                "billing_provider": provider,
                "payment_reference": provider_reference,
                "portal_invoice_id": invoice.id,
                "contract_module_code": root_code,
                "activation_codes": activation_codes,
                "bundle_parent": root_code if code != root_code else None,
                "billing_term": term,
                "plan_code": row.plan_code,
                "subtotal_cents": subtotal_cents,
                "tax_rate_bps": tax_rate_bps,
                "tax_amount_cents": tax_amount_cents,
                "amount_cents": int(invoice.amount_cents or 0),
                "currency": str(invoice.currency or "USD").upper(),
                "current_period_start": period_start.isoformat(),
                "current_period_end": period_end.isoformat(),
                "auto_renew": bool(commercial.get("auto_renew_accepted", True)),
                "terms_version": commercial.get("terms_version"),
                "last_settled_invoice_id": invoice.id,
                "renewal_invoice_id": None,
                "updated_by": "verified_payment",
                "updated_at": now.isoformat(),
            }
        )
        row.metadata_json = json.dumps(metadata, separators=(",", ":"))
        if code == root_code:
            root_row = row

    db.flush()
    return root_row


def install_module_activation_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    commercial_services._enable_paid_module = enable_paid_module_contract
    _INSTALLED = True
