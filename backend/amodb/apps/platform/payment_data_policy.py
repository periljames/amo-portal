from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import schemas as account_schemas
from amodb.apps.accounts import services as account_services

from . import commercial_access_policy, commercial_integrations as integrations
from . import commercial_services, saas_queue, saas_services


_INSTALLED = False
_ORIGINAL_ROLL = account_services.roll_billing_periods_and_alert


class LegacyBillingMutationDisabled(ValueError):
    """Raised when a retired billing mutation would bypass verified settlement."""


def _blocked_purchase(*args, **kwargs):
    raise LegacyBillingMutationDisabled(
        "Legacy direct purchase is disabled. Create a portal module invoice and settle it through the verified hosted payment workflow."
    )


def _blocked_payment_method(*args, **kwargs):
    raise LegacyBillingMutationDisabled(
        "Manual payment-method attachment is disabled. Card or bank credentials must be collected and tokenized by the configured payment provider."
    )


def _safe_trial_projection(original):
    def project(license, *, now, has_payment_method, has_overdue_invoice):
        # A database PaymentMethod row is not proof that a renewal charge was
        # authorized or settled. Expired trials therefore cannot become ACTIVE
        # solely because a provider reference exists.
        return original(
            license,
            now=now,
            has_payment_method=False,
            has_overdue_invoice=has_overdue_invoice,
        )

    return project


def _safe_legacy_subscription_projection(
    db: Session,
    *,
    license: account_models.TenantLicense,
    as_of: datetime | None = None,
) -> account_schemas.SubscriptionRead:
    now = as_of or datetime.now(timezone.utc)
    status = license.status
    read_only = bool(license.is_read_only)
    grace = license.trial_grace_expires_at
    current_period_end = license.current_period_end

    overdue = (
        db.query(account_models.BillingInvoice.id)
        .filter(
            account_models.BillingInvoice.amo_id == license.amo_id,
            account_models.BillingInvoice.status == account_models.InvoiceStatus.PENDING,
            account_models.BillingInvoice.due_at.isnot(None),
            account_models.BillingInvoice.due_at <= now,
        )
        .first()
        is not None
    )

    if status == account_models.LicenseStatus.TRIALING and license.trial_ends_at and license.trial_ends_at <= now:
        status = account_models.LicenseStatus.EXPIRED
        grace = grace or license.trial_ends_at + timedelta(days=7)
        current_period_end = license.trial_ends_at
        read_only = now >= grace
    elif status == account_models.LicenseStatus.EXPIRED:
        if license.trial_ends_at:
            grace = grace or license.trial_ends_at + timedelta(days=7)
            read_only = now >= grace
            current_period_end = current_period_end or license.trial_ends_at
        else:
            read_only = True
    elif status == account_models.LicenseStatus.CANCELLED:
        read_only = True
    elif current_period_end and current_period_end <= now:
        read_only = True
    elif overdue:
        read_only = True

    return account_schemas.SubscriptionRead(
        id=license.id,
        amo_id=license.amo_id,
        sku_id=license.sku_id,
        term=license.term,
        status=status,
        trial_started_at=license.trial_started_at,
        trial_ends_at=license.trial_ends_at,
        trial_grace_expires_at=grace,
        is_read_only=read_only,
        current_period_start=license.current_period_start,
        current_period_end=current_period_end,
        canceled_at=license.canceled_at,
    )


def _term_delta(term: account_models.BillingTerm) -> timedelta:
    return {
        account_models.BillingTerm.MONTHLY: timedelta(days=30),
        account_models.BillingTerm.BI_ANNUAL: timedelta(days=182),
        account_models.BillingTerm.ANNUAL: timedelta(days=365),
    }.get(term, timedelta(days=30))


def _prepare_legacy_renewals(
    db: Session,
    *,
    now: datetime,
) -> list[str]:
    """Turn elapsed paid legacy periods into invoices, never free extensions."""
    due = (
        db.query(account_models.TenantLicense)
        .filter(
            account_models.TenantLicense.status == account_models.LicenseStatus.ACTIVE,
            account_models.TenantLicense.current_period_end.isnot(None),
            account_models.TenantLicense.current_period_end <= now,
        )
        .all()
    )
    payment_required: list[str] = []
    for license in due:
        sku = db.get(account_models.CatalogSKU, license.sku_id)
        if sku is None:
            license.status = account_models.LicenseStatus.EXPIRED
            license.is_read_only = True
            db.add(license)
            payment_required.append(license.id)
            continue

        if int(sku.amount_cents or 0) <= 0:
            start = license.current_period_end or now
            while start <= now:
                start = start + _term_delta(license.term)
            license.current_period_start = license.current_period_end or now
            license.current_period_end = start
            license.is_read_only = False
            db.add(license)
            account_services._log_billing_audit(
                db,
                amo_id=license.amo_id,
                event="FREE_PERIOD_ROLLED",
                details={"license_id": license.id, "next_period_end": start.isoformat()},
            )
            continue

        ended = license.current_period_end or now
        key = f"legacy-renewal:{license.id}:{ended.isoformat()}"[:128]
        existing = (
            db.query(account_models.BillingInvoice)
            .filter(
                account_models.BillingInvoice.amo_id == license.amo_id,
                account_models.BillingInvoice.idempotency_key == key,
            )
            .first()
        )
        if existing is None:
            ledger = account_models.LedgerEntry(
                amo_id=license.amo_id,
                license_id=license.id,
                amount_cents=int(sku.amount_cents or 0),
                currency=str(sku.currency or "USD").upper(),
                entry_type=account_models.LedgerEntryType.CHARGE,
                description=json.dumps(
                    {
                        "event": "LEGACY_BASE_RENEWAL",
                        "sku_code": sku.code,
                        "license_id": license.id,
                    },
                    separators=(",", ":"),
                ),
                idempotency_key=key,
                recorded_at=now,
            )
            db.add(ledger)
            db.flush()
            invoice = account_models.BillingInvoice(
                amo_id=license.amo_id,
                license_id=license.id,
                ledger_entry_id=ledger.id,
                amount_cents=int(sku.amount_cents or 0),
                currency=str(sku.currency or "USD").upper(),
                status=account_models.InvoiceStatus.PENDING,
                description=json.dumps(
                    {
                        "source": "LEGACY_BASE_RENEWAL",
                        "sku_code": sku.code,
                        "billing_term": getattr(license.term, "value", str(license.term)),
                        "subtotal_cents": int(sku.amount_cents or 0),
                        "tax_rate_bps": 0,
                        "tax_amount_cents": 0,
                        "total_cents": int(sku.amount_cents or 0),
                        "lock_scope": "ACCOUNT",
                    },
                    separators=(",", ":"),
                ),
                idempotency_key=key,
                issued_at=now,
                due_at=now,
            )
            db.add(invoice)
            account_services._log_billing_audit(
                db,
                amo_id=license.amo_id,
                event="RENEWAL_INVOICE_ISSUED",
                details={
                    "license_id": license.id,
                    "sku": sku.code,
                    "amount_cents": int(sku.amount_cents or 0),
                    "currency": str(sku.currency or "USD").upper(),
                },
            )

        license.status = account_models.LicenseStatus.EXPIRED
        license.is_read_only = True
        db.add(license)
        payment_required.append(license.id)
    if due:
        db.flush()
    return payment_required


def _secure_billing_maintenance(
    db: Session,
    *,
    as_of: datetime | None = None,
    warn_threshold: float = account_services.DEFAULT_USAGE_WARN_THRESHOLD,
) -> dict[str, Any]:
    now = as_of or datetime.now(timezone.utc)
    grace = timedelta(days=7)

    # Expired trials require a deliberate paid checkout; a stored provider
    # reference cannot auto-convert them.
    trials = (
        db.query(account_models.TenantLicense)
        .filter(
            account_models.TenantLicense.status == account_models.LicenseStatus.TRIALING,
            account_models.TenantLicense.trial_ends_at.isnot(None),
            account_models.TenantLicense.trial_ends_at <= now,
        )
        .all()
    )
    for license in trials:
        license.status = account_models.LicenseStatus.EXPIRED
        license.current_period_end = license.trial_ends_at
        if not license.trial_grace_expires_at:
            license.trial_grace_expires_at = license.trial_ends_at + grace
        license.is_read_only = now >= license.trial_grace_expires_at
        db.add(license)
        account_services._log_billing_audit(
            db,
            amo_id=license.amo_id,
            event="TRIAL_EXPIRED_PAYMENT_REQUIRED",
            details={
                "license_id": license.id,
                "trial_ended_at": license.trial_ends_at.isoformat(),
                "grace_until": license.trial_grace_expires_at.isoformat(),
                "reason": "Provider reference alone is not verified payment settlement.",
            },
        )

    renewal_due = _prepare_legacy_renewals(db, now=now)
    if trials or renewal_due:
        db.flush()

    summary = _ORIGINAL_ROLL(db, as_of=now, warn_threshold=warn_threshold)
    summary["payment_required_licenses"] = sorted(set(renewal_due))
    return summary


def _safe_paystack_webhook(
    db: Session,
    *,
    raw_payload: bytes,
    signature: str,
):
    """Verify the callback, then persist only the fields needed for re-verification.

    Paystack authorization/card objects are intentionally not written into the
    durable job payload. The worker verifies the transaction server-side from the
    opaque reference before any accounting or entitlement mutation.
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
        raise ValueError("Paystack event is missing portal tenant, invoice or reference metadata")

    credential = commercial_services._provider_credential(db, integrations.PAYSTACK_CODE, tenant_id=tenant_id)
    secret = saas_services.provider_secrets(credential)
    if not integrations.verify_paystack_signature(raw_payload, signature, str(secret.get("secret_key") or "")):
        raise PermissionError("Invalid Paystack webhook signature")

    return saas_queue.enqueue_job(
        db,
        job_type="PAYSTACK_WEBHOOK",
        queue_name="billing",
        tenant_id=tenant_id,
        payload={
            "event_type": event_type,
            "credential_id": credential.id,
            "invoice_id": invoice_id,
            "reference": reference,
            "data_minimized": True,
        },
        idempotency_key=f"{event_type}:{reference}",
        correlation_id=reference,
        max_attempts=6,
        priority=5,
    )


def install_payment_data_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # Retire mutation paths that accept caller-supplied payment references and
    # activate licences before a provider has verified settlement.
    account_services.purchase_sku = _blocked_purchase
    account_services.add_payment_method = _blocked_payment_method

    # Existing payment-method rows remain readable/removable for migration and
    # audit, but can no longer prove payment or renew/convert access.
    account_services.roll_billing_periods_and_alert = _secure_billing_maintenance
    account_services._project_subscription_runtime = _safe_legacy_subscription_projection
    commercial_access_policy._project_subscription = _safe_trial_projection(
        commercial_access_policy._project_subscription
    )

    # Signed callbacks are admitted, but full provider authorization/card
    # objects are not persisted in our durable queue.
    commercial_services.record_paystack_webhook = _safe_paystack_webhook
    _INSTALLED = True
