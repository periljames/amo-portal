from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import module_renewals


_INSTALLED = False
_ORIGINAL_GENERATE = module_renewals.generate_module_renewal_invoices


def _details(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def normalize_pending_module_renewal_scope(db: Session) -> int:
    rows = (
        db.query(account_models.BillingInvoice)
        .filter(
            account_models.BillingInvoice.status == account_models.InvoiceStatus.PENDING,
            account_models.BillingInvoice.description.contains('"source":"MODULE_RENEWAL"'),
        )
        .all()
    )
    changed = 0
    for invoice in rows:
        details = _details(invoice.description)
        if not details or details.get("source") != "MODULE_RENEWAL":
            continue
        if details.get("lock_scope") == "MODULE":
            continue
        details["lock_scope"] = "MODULE"
        invoice.description = json.dumps(details, separators=(",", ":"))
        changed += 1
    if changed:
        db.flush()
    return changed


def generate_scoped_module_renewal_invoices(
    db: Session,
    *,
    as_of=None,
):
    result = _ORIGINAL_GENERATE(db, as_of=as_of)
    changed = normalize_pending_module_renewal_scope(db)
    if isinstance(result, dict):
        result = {**result, "normalized_module_lock_scope": changed}
    return result


def install_module_renewal_scope_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    module_renewals.generate_module_renewal_invoices = generate_scoped_module_renewal_invoices
    _INSTALLED = True
