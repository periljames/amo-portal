"""Scheduled billing lifecycle maintenance.

Runs the two supported commercial contract models:
- base-account contracts stored as TenantLicense records;
- explicit module subscriptions with independent renewal obligations.
"""

from __future__ import annotations

from datetime import datetime, timezone

from amodb.apps.accounts.billing_lifecycle import maintain_base_contracts
from amodb.apps.platform.module_renewals import generate_module_renewal_invoices
from amodb.database import WriteSessionLocal, close_session_safely


def run() -> dict:
    """Execute billing lifecycle maintenance and return an auditable summary."""
    db = WriteSessionLocal()
    try:
        now = datetime.now(timezone.utc)
        base_contracts = maintain_base_contracts(db, as_of=now)
        module_contracts = generate_module_renewal_invoices(db, as_of=now)
        db.commit()
        return {
            "base_contracts": base_contracts,
            "module_contracts": module_contracts,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        close_session_safely(db)


if __name__ == "__main__":
    print("Billing maintenance completed:", run())
