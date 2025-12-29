"""Billing maintenance job.

This script is intended for cron/Task Scheduler (e.g. hourly) to:
 - roll active/trial subscription periods forward
 - log audit entries when usage meters near their entitlement limits
"""

from __future__ import annotations

from datetime import datetime, timezone

from amodb.database import WriteSessionLocal
from amodb.apps.accounts import services as account_services


def run() -> dict:
    """Execute the maintenance job and return a summary dict."""
    db = WriteSessionLocal()
    try:
        summary = account_services.roll_billing_periods_and_alert(
            db,
            as_of=datetime.now(timezone.utc),
        )
        db.commit()
        return summary
    finally:
        db.close()


if __name__ == "__main__":
    result = run()
    print("Billing maintenance completed:", result)
