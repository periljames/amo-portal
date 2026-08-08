from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
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


def _expire_ended_trials_before_legacy_roll(
    db: Session,
    *,
    as_of: datetime | None = None,
    warn_threshold: float = account_services.DEFAULT_USAGE_WARN_THRESHOLD,
) -> dict[str, Any]:
    now = as_of or datetime.now(timezone.utc)
    grace = timedelta(days=7)
    ended = (
        db.query(account_models.TenantLicense)
        .filter(
            account_models.TenantLicense.status == account_models.LicenseStatus.TRIALING,
            account_models.TenantLicense.trial_ends_at.isnot(None),
            account_models.TenantLicense.trial_ends_at <= now,
        )
        .all()
    )
    for license in ended:
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
    if ended:
        db.flush()
    return _ORIGINAL_ROLL(db, as_of=now, warn_threshold=warn_threshold)


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
    # audit, but can no longer auto-convert a trial into paid service.
    account_services.roll_billing_periods_and_alert = _expire_ended_trials_before_legacy_roll
    commercial_access_policy._project_subscription = _safe_trial_projection(
        commercial_access_policy._project_subscription
    )

    # Signed callbacks are admitted, but full provider authorization/card
    # objects are not persisted in our durable queue.
    commercial_services.record_paystack_webhook = _safe_paystack_webhook
    _INSTALLED = True
