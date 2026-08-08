"""Billing maintenance job.

This script is intended for cron/Task Scheduler (e.g. hourly) to:
 - roll legacy tenant-license periods and usage alerts
 - generate governed module-renewal invoices before paid service periods end
"""

from __future__ import annotations

from datetime import datetime, timezone

from amodb.database import WriteSessionLocal
from amodb.apps.accounts import services as account_services
from amodb.apps.platform.module_renewals import generate_module_renewal_invoices


def run() -> dict:
    """Execute all billing lifecycle maintenance and return an auditable summary."""
    db = WriteSessionLocal()
    try:
        now = datetime.now(timezone.utc)
        legacy = account_services.roll_billing_periods_and_alert(db, as_of=now)
        modules = generate_module_renewal_invoices(db, as_of=now)
        db.commit()
        return {
            "legacy_billing": legacy,
            "module_commerce": modules,
        }
    finally:
        db.close()


if __name__ == "__main__":
    result = run()
    print("Billing maintenance completed:", result)
