"""Commercial payment-data safety policy.

Legacy direct billing mutations remain disabled. Payment activation must come from
verified provider settlement, while durable webhook records retain only the
minimum identifiers needed for reconciliation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts.billing_lifecycle import maintain_base_contracts


class LegacyBillingMutationDisabled(RuntimeError):
    """Raised when a retired direct billing mutation is attempted."""


def _blocked_purchase(*args: Any, **kwargs: Any) -> None:
    raise LegacyBillingMutationDisabled(
        "Direct purchase is disabled; use the verified hosted payment workflow."
    )


def _blocked_payment_method(*args: Any, **kwargs: Any) -> None:
    raise LegacyBillingMutationDisabled(
        "Manual payment-method attachment is disabled; use a configured payment provider."
    )


def _safe_paystack_webhook(
    payload: dict[str, Any],
    *,
    invoice_id: str,
    credential: Any,
) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else None
    data = data if isinstance(data, dict) else {}
    reference = str(data.get("reference") or "").strip()
    return {
        "event_type": str(payload.get("event") or "").strip(),
        "reference": reference,
        "invoice_id": invoice_id,
        "credential_id": credential.id,
        "data_minimized": True,
    }


def _secure_billing_maintenance(
    db: Session,
    *,
    as_of: datetime,
) -> dict[str, Any]:
    """Run canonical base-contract maintenance without inferring payment from stored metadata."""
    return maintain_base_contracts(db, as_of=as_of)


__all__ = [
    "LegacyBillingMutationDisabled",
    "_blocked_purchase",
    "_blocked_payment_method",
    "_safe_paystack_webhook",
    "_secure_billing_maintenance",
]
