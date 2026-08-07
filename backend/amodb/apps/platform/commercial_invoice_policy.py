from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import services as account_services

from . import models as platform_models
from . import saas_models, saas_services, saas_side_effects


_INSTALLED = False


def _json_details(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def tax_cents(subtotal_cents: int, tax_rate_bps: int) -> int:
    """Round tax to the nearest cent using deterministic commercial half-up."""
    value = (Decimal(int(subtotal_cents)) * Decimal(int(tax_rate_bps))) / Decimal(10000)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def invoice_breakdown(invoice: account_models.BillingInvoice) -> dict[str, Any]:
    """Return an internally reconciled subtotal/tax/total view.

    Structured SaaS invoices carry their immutable commercial snapshot in the
    description JSON. Legacy plain-text invoices remain tax-zero unless they are
    explicitly migrated; we do not invent a tax amount after issuance.
    """
    details = _json_details(invoice.description)
    total = int(invoice.amount_cents or 0)
    if "subtotal_cents" not in details and "tax_amount_cents" not in details:
        return {
            "subtotal_cents": total,
            "tax_amount_cents": 0,
            "total_cents": total,
            "tax_rate_bps": 0,
            "tax_mode": "LEGACY_UNSPECIFIED",
            "details": details,
        }

    subtotal = int(details.get("subtotal_cents") or 0)
    tax_amount = int(details.get("tax_amount_cents") or 0)
    if subtotal < 0 or tax_amount < 0:
        raise ValueError("Invoice subtotal/tax cannot be negative")
    if subtotal + tax_amount != total:
        raise ValueError(
            "Invoice accounting breakdown does not reconcile to amount_cents"
        )
    return {
        "subtotal_cents": subtotal,
        "tax_amount_cents": tax_amount,
        "total_cents": total,
        "tax_rate_bps": int(details.get("tax_rate_bps") or 0),
        "tax_mode": str(details.get("tax_mode") or "EXCLUSIVE").upper(),
        "details": details,
    }


def _same_invoice_request(
    invoice: account_models.BillingInvoice,
    *,
    price: saas_models.SaaSModulePrice,
    quantity: int,
    subtotal: int,
    tax_amount: int,
    total: int,
) -> bool:
    details = _json_details(invoice.description)
    return bool(
        str(invoice.currency or "").upper() == str(price.currency or "").upper()
        and int(invoice.amount_cents or 0) == total
        and str(details.get("module_code") or "") == str(price.module_code)
        and str(details.get("plan_code") or "") == str(price.plan_code)
        and int(details.get("quantity") or 0) == quantity
        and int(details.get("unit_amount_cents") or 0) == int(price.amount_cents)
        and int(details.get("subtotal_cents") or 0) == subtotal
        and int(details.get("tax_amount_cents") or 0) == tax_amount
    )


def create_manual_invoice_accounting(
    db: Session,
    *,
    tenant_id: str,
    module_price_id: str,
    quantity: int,
    due_days: int,
    actor_user_id: str,
    reason: str,
    idempotency_key: str,
) -> dict[str, Any]:
    tenant = db.get(account_models.AMO, tenant_id)
    price = db.get(saas_models.SaaSModulePrice, module_price_id)
    if tenant is None:
        raise ValueError("Tenant not found")
    if price is None or not price.is_active:
        raise ValueError("Active module price not found")
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("A business reason is required for manual invoice creation")
    key = str(idempotency_key or "").strip()
    if not key:
        raise ValueError("idempotency_key is required")
    quantity = max(1, min(int(quantity), 10000))
    due_days = max(0, min(int(due_days), 365))

    subtotal = int(price.amount_cents) * quantity
    rate_bps = int(price.tax_rate_bps or 0)
    tax_amount = tax_cents(subtotal, rate_bps)
    total = subtotal + tax_amount

    existing = (
        db.query(account_models.BillingInvoice)
        .filter(
            account_models.BillingInvoice.amo_id == tenant_id,
            account_models.BillingInvoice.idempotency_key == key,
        )
        .first()
    )
    if existing is not None:
        if not _same_invoice_request(
            existing,
            price=price,
            quantity=quantity,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total=total,
        ):
            raise ValueError(
                "idempotency_key is already bound to a different invoice payload"
            )
        return saas_services.invoice_payload(existing)

    now = saas_services.utcnow()
    currency = str(price.currency or "USD").strip().upper()
    ledger = account_models.LedgerEntry(
        amo_id=tenant_id,
        amount_cents=total,
        currency=currency,
        entry_type=account_models.LedgerEntryType.CHARGE,
        description=json.dumps(
            {
                "event": "SUBSCRIPTION_INVOICE_CHARGE",
                "module_price_id": price.id,
                "module_code": price.module_code,
                "plan_code": price.plan_code,
                "quantity": quantity,
                "subtotal_cents": subtotal,
                "tax_amount_cents": tax_amount,
                "total_cents": total,
            },
            separators=(",", ":"),
        ),
        idempotency_key=key,
        recorded_at=now,
    )
    db.add(ledger)
    db.flush()

    description = json.dumps(
        {
            "module_price_id": price.id,
            "module_code": price.module_code,
            "plan_code": price.plan_code,
            "billing_term": price.billing_term,
            "quantity": quantity,
            "unit_amount_cents": int(price.amount_cents),
            "subtotal_cents": subtotal,
            "tax_rate_bps": rate_bps,
            "tax_amount_cents": tax_amount,
            "tax_mode": "EXCLUSIVE",
            "total_cents": total,
            "reason": reason,
        },
        separators=(",", ":"),
    )
    invoice = account_models.BillingInvoice(
        amo_id=tenant_id,
        ledger_entry_id=ledger.id,
        amount_cents=total,
        currency=currency,
        status=(
            account_models.InvoiceStatus.PAID
            if total == 0
            else account_models.InvoiceStatus.PENDING
        ),
        description=description,
        idempotency_key=key,
        issued_at=now,
        due_at=now if total == 0 else now + timedelta(days=due_days),
        paid_at=now if total == 0 else None,
    )
    db.add(invoice)
    db.flush()
    db.add(
        platform_models.PlatformAuditLog(
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            action="saas.invoice.created",
            module="billing",
            entity_type="billing_invoice",
            entity_id=invoice.id,
            reason=reason[:1000],
            details_json={
                "module_price_id": price.id,
                "module_code": price.module_code,
                "plan_code": price.plan_code,
                "quantity": quantity,
                "subtotal_cents": subtotal,
                "tax_rate_bps": rate_bps,
                "tax_amount_cents": tax_amount,
                "total_cents": total,
                "currency": currency,
                "tax_mode": "EXCLUSIVE",
            },
        )
    )
    db.commit()
    db.refresh(invoice)
    return saas_services.invoice_payload(invoice)


def build_invoice_view_accounting(invoice: account_models.BillingInvoice) -> dict[str, Any]:
    breakdown = invoice_breakdown(invoice)
    amo = getattr(invoice, "amo", None)
    fiscal = getattr(invoice, "saas_fiscalization", None)
    fiscal_status = str(getattr(fiscal, "status", "NOT_CONNECTED") or "NOT_CONNECTED")
    fiscal_reference = getattr(fiscal, "fiscal_document_number", None) if fiscal else None
    return {
        "id": invoice.id,
        "invoice_number": account_services.format_invoice_number(invoice),
        "amo_id": invoice.amo_id,
        "buyer_name": getattr(amo, "name", None),
        "buyer_email": getattr(amo, "contact_email", None),
        "buyer_phone": getattr(amo, "contact_phone", None),
        "license_id": invoice.license_id,
        "ledger_entry_id": invoice.ledger_entry_id,
        "amount_cents": int(invoice.amount_cents or 0),
        "currency": str(invoice.currency or "USD").upper(),
        "status": invoice.status,
        "description": invoice.description,
        "issued_at": invoice.issued_at,
        "due_at": invoice.due_at,
        "paid_at": invoice.paid_at,
        "created_at": invoice.created_at,
        "updated_at": invoice.updated_at,
        "subtotal_cents": breakdown["subtotal_cents"],
        "tax_amount_cents": breakdown["tax_amount_cents"],
        "total_cents": breakdown["total_cents"],
        "etims_status": fiscal_status,
        "etims_reference": fiscal_reference,
    }


def fiscal_invoice_payload(
    invoice: account_models.BillingInvoice,
    *,
    submission_reference: str,
) -> dict[str, Any]:
    breakdown = invoice_breakdown(invoice)
    details = breakdown["details"]
    tenant = invoice.amo
    quantity = int(details.get("quantity") or 1)
    unit_amount_cents = int(
        details.get("unit_amount_cents")
        or (breakdown["subtotal_cents"] // max(quantity, 1))
    )
    return {
        "submission_reference": submission_reference,
        "portal_invoice_id": invoice.id,
        "invoice_number": account_services.format_invoice_number(invoice),
        "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
        "due_at": invoice.due_at.isoformat() if invoice.due_at else None,
        "currency": str(invoice.currency or "USD").upper(),
        "subtotal_amount_cents": breakdown["subtotal_cents"],
        "tax_amount_cents": breakdown["tax_amount_cents"],
        "tax_rate_bps": breakdown["tax_rate_bps"],
        "tax_mode": breakdown["tax_mode"],
        "total_amount_cents": breakdown["total_cents"],
        "description": invoice.description,
        "lines": [
            {
                "description": str(
                    details.get("module_code")
                    or details.get("description")
                    or "AMO Portal subscription/service"
                ),
                "quantity": quantity,
                "unit_amount_cents": unit_amount_cents,
                "subtotal_cents": breakdown["subtotal_cents"],
                "tax_rate_bps": breakdown["tax_rate_bps"],
                "tax_amount_cents": breakdown["tax_amount_cents"],
                "total_cents": breakdown["total_cents"],
            }
        ],
        "buyer": {
            "tenant_id": invoice.amo_id,
            "name": getattr(tenant, "name", None),
            "email": getattr(tenant, "contact_email", None),
            "phone": getattr(tenant, "contact_phone", None),
            "country": getattr(tenant, "country", None),
        },
    }


def install_invoice_accounting_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    saas_services.create_manual_invoice = create_manual_invoice_accounting
    account_services.build_invoice_view = build_invoice_view_accounting
    # The certified eTIMS adapter now receives the exact same reconciled monetary
    # breakdown used by invoice documents, exports and QuickBooks writeback.
    saas_side_effects._invoice_payload = fiscal_invoice_payload
    _INSTALLED = True
