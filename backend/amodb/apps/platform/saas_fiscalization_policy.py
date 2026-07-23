from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from . import saas_models as models
from . import saas_services


_INSTALLED = False
_ORIGINAL_ENQUEUE: Callable[..., models.SaaSJob] | None = None
BLOCKED_EXISTING_STATES = {
    "FISCALIZED",
    "RECONCILIATION_REQUIRED",
    "SUBMITTING",
    "SUBMITTED",
    "FAILED",
}


def validate_fiscalization_enqueue(
    db: Session,
    *,
    invoice_id: str,
) -> None:
    """Reject any request that could overwrite a terminal or uncertain state."""

    row = (
        db.query(models.SaaSInvoiceFiscalization)
        .filter(models.SaaSInvoiceFiscalization.invoice_id == invoice_id)
        .first()
    )
    if row is None:
        return
    current = str(row.status or "").strip().upper()
    if current == "FISCALIZED":
        raise ValueError("Invoice is already fiscalized and cannot be submitted again")
    if current == "RECONCILIATION_REQUIRED":
        raise ValueError(
            "Invoice requires eTIMS reconciliation before any further submission"
        )
    if current in {"SUBMITTING", "SUBMITTED"}:
        raise ValueError("Invoice fiscalization is already in progress")
    if current == "FAILED":
        raise ValueError(
            "Failed non-repeatable fiscalization must be reviewed before a new submission"
        )


def install_fiscalization_enqueue_policy() -> None:
    global _INSTALLED, _ORIGINAL_ENQUEUE
    if _INSTALLED:
        return

    _ORIGINAL_ENQUEUE = saas_services.enqueue_fiscalization

    def guarded_enqueue_fiscalization(
        db: Session,
        *,
        invoice_id: str,
        provider: str,
        actor_user_id: str,
    ) -> models.SaaSJob:
        validate_fiscalization_enqueue(db, invoice_id=invoice_id)
        assert _ORIGINAL_ENQUEUE is not None
        return _ORIGINAL_ENQUEUE(
            db,
            invoice_id=invoice_id,
            provider=provider,
            actor_user_id=actor_user_id,
        )

    saas_services.enqueue_fiscalization = guarded_enqueue_fiscalization
    _INSTALLED = True
