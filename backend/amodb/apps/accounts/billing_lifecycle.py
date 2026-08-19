from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from . import billing_access, models, services


def _term_delta(term: models.BillingTerm) -> timedelta:
    return {
        models.BillingTerm.MONTHLY: timedelta(days=30),
        models.BillingTerm.BI_ANNUAL: timedelta(days=182),
        models.BillingTerm.ANNUAL: timedelta(days=365),
    }.get(term, timedelta(days=30))


def _roll_free_period(license: models.TenantLicense, *, now: datetime) -> datetime:
    start = license.current_period_end or now
    next_end = start
    while next_end <= now:
        next_end += _term_delta(license.term)
    license.current_period_start = start
    license.current_period_end = next_end
    license.status = models.LicenseStatus.ACTIVE
    license.is_read_only = False
    return next_end


def _create_paid_renewal_obligation(
    db: Session,
    *,
    license: models.TenantLicense,
    sku: models.CatalogSKU,
    now: datetime,
) -> models.BillingInvoice:
    ended = license.current_period_end or now
    key = f"base-renewal:{license.id}:{ended.isoformat()}"[:128]
    existing = (
        db.query(models.BillingInvoice)
        .filter(
            models.BillingInvoice.amo_id == license.amo_id,
            models.BillingInvoice.idempotency_key == key,
        )
        .first()
    )
    if existing is not None:
        return existing

    amount = int(sku.amount_cents or 0)
    currency = str(sku.currency or "USD").upper()
    ledger = models.LedgerEntry(
        amo_id=license.amo_id,
        license_id=license.id,
        amount_cents=amount,
        currency=currency,
        entry_type=models.LedgerEntryType.CHARGE,
        description=json.dumps(
            {
                "event": "BASE_RENEWAL",
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

    invoice = models.BillingInvoice(
        amo_id=license.amo_id,
        license_id=license.id,
        ledger_entry_id=ledger.id,
        amount_cents=amount,
        currency=currency,
        status=models.InvoiceStatus.PENDING,
        description=json.dumps(
            {
                "source": "BASE_RENEWAL",
                "sku_code": sku.code,
                "billing_term": getattr(license.term, "value", str(license.term)),
                "subtotal_cents": amount,
                "tax_rate_bps": 0,
                "tax_amount_cents": 0,
                "total_cents": amount,
                "lock_scope": "ACCOUNT",
            },
            separators=(",", ":"),
        ),
        idempotency_key=key,
        issued_at=now,
        due_at=now,
    )
    db.add(invoice)
    services._log_billing_audit(
        db,
        amo_id=license.amo_id,
        event="RENEWAL_INVOICE_ISSUED",
        details={
            "license_id": license.id,
            "sku": sku.code,
            "amount_cents": amount,
            "currency": currency,
            "invoice_id": invoice.id,
        },
    )
    return invoice


def _expire_trials(db: Session, *, now: datetime) -> list[str]:
    grace_period = timedelta(days=7)
    rows = (
        db.query(models.TenantLicense)
        .filter(
            models.TenantLicense.status == models.LicenseStatus.TRIALING,
            models.TenantLicense.trial_ends_at.isnot(None),
            models.TenantLicense.trial_ends_at <= now,
        )
        .all()
    )
    expired: list[str] = []
    for license in rows:
        license.status = models.LicenseStatus.EXPIRED
        license.current_period_end = license.trial_ends_at
        license.trial_grace_expires_at = license.trial_grace_expires_at or license.trial_ends_at + grace_period
        license.is_read_only = now >= license.trial_grace_expires_at
        expired.append(license.id)
        services._log_billing_audit(
            db,
            amo_id=license.amo_id,
            event="TRIAL_EXPIRED_PAYMENT_REQUIRED",
            details={
                "license_id": license.id,
                "trial_ended_at": license.trial_ends_at.isoformat(),
                "grace_until": license.trial_grace_expires_at.isoformat(),
            },
        )
    return expired


def _maintain_paid_periods(db: Session, *, now: datetime) -> tuple[list[str], list[str]]:
    rows = (
        db.query(models.TenantLicense)
        .filter(
            models.TenantLicense.status == models.LicenseStatus.ACTIVE,
            models.TenantLicense.current_period_end.isnot(None),
            models.TenantLicense.current_period_end <= now,
        )
        .all()
    )
    payment_required: list[str] = []
    free_rolled: list[str] = []
    for license in rows:
        sku = db.get(models.CatalogSKU, license.sku_id)
        if sku is None:
            license.status = models.LicenseStatus.EXPIRED
            license.is_read_only = True
            payment_required.append(license.id)
            services._log_billing_audit(
                db,
                amo_id=license.amo_id,
                event="BASE_CONTRACT_CONFIGURATION_MISSING",
                details={"license_id": license.id, "sku_id": license.sku_id},
            )
            continue

        if int(sku.amount_cents or 0) <= 0:
            next_end = _roll_free_period(license, now=now)
            free_rolled.append(license.id)
            services._log_billing_audit(
                db,
                amo_id=license.amo_id,
                event="FREE_PERIOD_ROLLED",
                details={"license_id": license.id, "next_period_end": next_end.isoformat()},
            )
            continue

        _create_paid_renewal_obligation(db, license=license, sku=sku, now=now)
        license.status = models.LicenseStatus.EXPIRED
        license.is_read_only = True
        payment_required.append(license.id)
    return payment_required, free_rolled


def _usage_threshold_alerts(db: Session, *, warn_threshold: float) -> list[dict[str, Any]]:
    warn_pct = max(1, min(100, int(float(warn_threshold) * 100)))
    alerts: list[dict[str, Any]] = []
    amo_ids = [row[0] for row in db.query(models.UsageMeter.amo_id).distinct().all() if row[0]]
    for amo_id in amo_ids:
        entitlements = billing_access.resolve_entitlements(db, amo_id=amo_id)
        for meter in services.list_usage_meters(db, amo_id=amo_id):
            limit, unlimited = services._resolve_meter_limit_for_key(meter.meter_key, entitlements)
            if unlimited or not limit or limit <= 0:
                continue
            percent = int(min(100, round((int(meter.used_units or 0) / limit) * 100)))
            if percent < warn_pct:
                continue
            detail = {
                "meter": meter.meter_key,
                "used_units": int(meter.used_units or 0),
                "limit": int(limit),
                "percent": percent,
            }
            alerts.append({"amo_id": amo_id, **detail})
            services._log_billing_audit(db, amo_id=amo_id, event="USAGE_THRESHOLD", details=detail)
    return alerts


def maintain_base_contracts(
    db: Session,
    *,
    as_of: datetime | None = None,
    warn_threshold: float | None = None,
) -> dict[str, Any]:
    """Maintain base-account contracts without ever inferring payment from stored provider metadata."""
    now = as_of or datetime.now(timezone.utc)
    expired_trials = _expire_trials(db, now=now)
    payment_required, free_rolled = _maintain_paid_periods(db, now=now)
    threshold = services.DEFAULT_USAGE_WARN_THRESHOLD if warn_threshold is None else warn_threshold
    usage_alerts = _usage_threshold_alerts(db, warn_threshold=threshold)
    db.flush()
    return {
        "expired_trials": sorted(expired_trials),
        "payment_required_licenses": sorted(payment_required),
        "free_periods_rolled": sorted(free_rolled),
        "usage_alerts": usage_alerts,
    }
