from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import services as account_services

from . import models as platform_models


def _metadata(row: account_models.ModuleSubscription) -> dict[str, Any]:
    if not row.metadata_json:
        return {}
    try:
        value = json.loads(row.metadata_json)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _root_contract(row: account_models.ModuleSubscription) -> bool:
    metadata = _metadata(row)
    return (
        not bool(metadata.get("commercial_offer_only"))
        and not metadata.get("bundle_parent")
        and str(metadata.get("contract_module_code") or row.module_code) == str(row.module_code)
    )


def cancel_at_period_end(
    db: Session,
    *,
    tenant_id: str,
    module_code: str,
    actor_user_id: str,
    reason: str,
) -> dict[str, Any]:
    clean_reason = str(reason or "").strip()
    if not clean_reason:
        raise ValueError("A cancellation reason is required")
    row = (
        db.query(account_models.ModuleSubscription)
        .filter(
            account_models.ModuleSubscription.amo_id == tenant_id,
            account_models.ModuleSubscription.module_code == module_code,
        )
        .first()
    )
    if row is None:
        raise ValueError("Module subscription not found")
    metadata = _metadata(row)
    if metadata.get("bundle_parent"):
        raise ValueError("Cancel the parent bundle rather than an included module")
    metadata["auto_renew"] = False
    metadata["cancel_at_period_end"] = True
    metadata["cancel_requested_at"] = datetime.now(timezone.utc).isoformat()
    metadata["cancel_requested_by"] = actor_user_id
    metadata["cancel_reason"] = clean_reason[:1000]
    row.metadata_json = json.dumps(metadata, separators=(",", ":"))
    db.add(
        platform_models.PlatformAuditLog(
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            action="saas.module_subscription.cancel_at_period_end",
            module="billing",
            entity_type="module_subscription",
            entity_id=str(row.id),
            reason=clean_reason[:1000],
            details_json={
                "module_code": row.module_code,
                "effective_to": _aware(row.effective_to).isoformat() if row.effective_to else None,
            },
        )
    )
    db.commit()
    return {
        "module_code": row.module_code,
        "status": getattr(row.status, "value", str(row.status)),
        "auto_renew": False,
        "cancel_at_period_end": True,
        "effective_to": row.effective_to,
    }


def generate_module_renewal_invoices(
    db: Session,
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    now = as_of or datetime.now(timezone.utc)
    lead_days = max(1, min(int(os.getenv("MODULE_RENEWAL_INVOICE_LEAD_DAYS", "7") or "7"), 60))
    horizon = now + timedelta(days=lead_days)
    created: list[str] = []
    expired_nonrenewing: list[str] = []

    rows = (
        db.query(account_models.ModuleSubscription)
        .filter(
            account_models.ModuleSubscription.status.in_([
                account_models.ModuleSubscriptionStatus.ENABLED,
                account_models.ModuleSubscriptionStatus.TRIAL,
            ]),
            account_models.ModuleSubscription.effective_to.isnot(None),
            account_models.ModuleSubscription.effective_to <= horizon,
        )
        .all()
    )
    for row in rows:
        if not _root_contract(row):
            continue
        metadata = _metadata(row)
        period_end = _aware(row.effective_to)
        if period_end is None:
            continue
        if not bool(metadata.get("auto_renew", False)):
            if period_end <= now:
                expired_nonrenewing.append(str(row.id))
            continue

        renewal_invoice_id = str(metadata.get("renewal_invoice_id") or "").strip()
        if renewal_invoice_id:
            existing = db.get(account_models.BillingInvoice, renewal_invoice_id)
            if existing is not None and existing.status in {
                account_models.InvoiceStatus.PENDING,
                account_models.InvoiceStatus.PAID,
            }:
                continue
            metadata["renewal_invoice_id"] = None

        module_code = str(metadata.get("contract_module_code") or row.module_code)
        activation_codes = [str(value) for value in metadata.get("activation_codes") or [] if str(value).strip()]
        subtotal = int(metadata.get("subtotal_cents") or metadata.get("amount_cents") or 0)
        tax_amount = int(metadata.get("tax_amount_cents") or 0)
        total = int(metadata.get("amount_cents") or subtotal + tax_amount)
        if subtotal + tax_amount != total:
            raise ValueError(f"Module renewal contract {row.id} has a non-reconciling price snapshot")
        if total < 0:
            raise ValueError(f"Module renewal contract {row.id} has a negative amount")
        currency = str(metadata.get("currency") or "USD").upper()
        tax_rate_bps = int(metadata.get("tax_rate_bps") or 0)
        term = str(metadata.get("billing_term") or "MONTHLY").upper()
        plan_code = str(metadata.get("plan_code") or row.plan_code or "STANDARD").upper()
        key = f"module-renewal:{row.amo_id}:{module_code}:{period_end.isoformat()}"[:128]

        existing_invoice = (
            db.query(account_models.BillingInvoice)
            .filter(
                account_models.BillingInvoice.amo_id == row.amo_id,
                account_models.BillingInvoice.idempotency_key == key,
            )
            .first()
        )
        if existing_invoice is not None:
            metadata["renewal_invoice_id"] = existing_invoice.id
            row.metadata_json = json.dumps(metadata, separators=(",", ":"))
            continue

        ledger = account_models.LedgerEntry(
            amo_id=row.amo_id,
            amount_cents=total,
            currency=currency,
            entry_type=account_models.LedgerEntryType.CHARGE,
            description=json.dumps(
                {
                    "event": "MODULE_RENEWAL_CHARGE",
                    "module_code": module_code,
                    "period_end": period_end.isoformat(),
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
        invoice = account_models.BillingInvoice(
            amo_id=row.amo_id,
            ledger_entry_id=ledger.id,
            amount_cents=total,
            currency=currency,
            status=account_models.InvoiceStatus.PENDING,
            description=json.dumps(
                {
                    "module_code": module_code,
                    "activation_codes": activation_codes,
                    "plan_code": plan_code,
                    "billing_term": term,
                    "quantity": 1,
                    "unit_amount_cents": subtotal,
                    "subtotal_cents": subtotal,
                    "tax_rate_bps": tax_rate_bps,
                    "tax_amount_cents": tax_amount,
                    "tax_mode": "EXCLUSIVE",
                    "total_cents": total,
                    "lock_scope": "ACCOUNT",
                    "terms_version": metadata.get("terms_version"),
                    "auto_renew_accepted": True,
                    "source": "MODULE_RENEWAL",
                    "renewal_for_period_end": period_end.isoformat(),
                },
                separators=(",", ":"),
            ),
            idempotency_key=key,
            issued_at=now,
            due_at=period_end,
        )
        db.add(invoice)
        db.flush()
        metadata["renewal_invoice_id"] = invoice.id
        metadata["renewal_invoice_issued_at"] = now.isoformat()
        row.metadata_json = json.dumps(metadata, separators=(",", ":"))
        db.add(
            platform_models.PlatformAuditLog(
                actor_user_id=None,
                tenant_id=row.amo_id,
                action="saas.module_renewal.invoice_created",
                module="billing",
                entity_type="billing_invoice",
                entity_id=invoice.id,
                reason="Scheduled module renewal",
                details_json={
                    "module_code": module_code,
                    "module_subscription_id": row.id,
                    "invoice_number": account_services.format_invoice_number(invoice),
                    "amount_cents": total,
                    "currency": currency,
                    "due_at": period_end.isoformat(),
                },
            )
        )
        created.append(invoice.id)

    db.commit()
    return {
        "renewal_invoices_created": created,
        "expired_nonrenewing_contracts": expired_nonrenewing,
        "renewal_lead_days": lead_days,
    }
