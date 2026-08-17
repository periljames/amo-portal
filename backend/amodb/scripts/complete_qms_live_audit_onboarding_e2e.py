"""Ensure deterministic QMS Live Audit CI users satisfy current onboarding gates.

The production onboarding contract is intentionally minimal: a user is complete
when no mandatory password change is pending. Keep this helper aligned with
accounts/router_onboarding.py instead of importing a historical onboarding
module that no longer exists.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from amodb.main import app as _app  # noqa: F401,E402
from amodb.apps.accounts import models as account_models  # noqa: E402
from amodb.database import WriteSessionLocal  # noqa: E402


FIXTURE_PATH = Path(os.environ.get("E2E_QMS_LIVE_FIXTURE", "/tmp/qms-live-audit-real-e2e.json"))


def main() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    db = WriteSessionLocal()
    try:
        user_ids = (fixture["realtime_user_a_id"], fixture["realtime_user_b_id"])
        users = (
            db.query(account_models.User)
            .filter(
                account_models.User.amo_id == fixture["amo_id"],
                account_models.User.id.in_(user_ids),
            )
            .all()
        )
        if {str(user.id) for user in users} != set(user_ids):
            raise RuntimeError("Real-time QMS browser users were not seeded in the expected tenant")

        now = datetime.now(timezone.utc)
        for user in users:
            user.must_change_password = False
            if user.password_changed_at is None:
                user.password_changed_at = now
        db.commit()
        print("Confirmed both real-time QMS browser users satisfy current onboarding gates")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
