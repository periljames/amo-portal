"""Commercial projection of the legacy/base tenant licence state.

The projection is deliberately pure: stored payment-method/provider metadata is
not settlement evidence and therefore cannot reactivate an elapsed paid or trial
period. Verified settlement is handled by the commercial settlement service.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from amodb.apps.accounts import models as account_models


@dataclass(frozen=True)
class CommercialAccessProjection:
    status: account_models.LicenseStatus
    is_read_only: bool
    trial_grace_expires_at: datetime | None


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _project_subscription(
    license: account_models.TenantLicense,
    *,
    now: datetime,
    has_payment_method: bool,
    has_overdue_invoice: bool,
) -> CommercialAccessProjection:
    """Project access without treating a stored payment reference as payment."""
    del has_payment_method  # Metadata presence is intentionally not settlement evidence.

    current_status = license.status
    is_read_only = bool(license.is_read_only)
    grace = _aware(license.trial_grace_expires_at)
    trial_end = _aware(license.trial_ends_at)
    period_end = _aware(license.current_period_end)
    now = _aware(now) or datetime.now(timezone.utc)

    if current_status == account_models.LicenseStatus.TRIALING and trial_end and trial_end <= now:
        grace = grace or trial_end + timedelta(days=7)
        return CommercialAccessProjection(
            status=account_models.LicenseStatus.EXPIRED,
            is_read_only=now >= grace,
            trial_grace_expires_at=grace,
        )

    if current_status == account_models.LicenseStatus.ACTIVE:
        if has_overdue_invoice or (period_end is not None and period_end <= now):
            return CommercialAccessProjection(
                status=account_models.LicenseStatus.ACTIVE,
                is_read_only=True,
                trial_grace_expires_at=grace,
            )

    return CommercialAccessProjection(
        status=current_status,
        is_read_only=is_read_only,
        trial_grace_expires_at=grace,
    )


__all__ = ["CommercialAccessProjection", "_project_subscription"]
