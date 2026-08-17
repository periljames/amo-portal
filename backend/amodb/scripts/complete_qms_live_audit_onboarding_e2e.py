"""Mark deterministic QMS Live Audit CI users as fully onboarded."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from amodb.main import app as _app  # noqa: F401,E402
from amodb.apps.accounts.onboarding import set_onboarding_step  # noqa: E402
from amodb.database import WriteSessionLocal  # noqa: E402


FIXTURE_PATH = Path(os.environ.get("E2E_QMS_LIVE_FIXTURE", "/tmp/qms-live-audit-real-e2e.json"))


def main() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    db = WriteSessionLocal()
    try:
        for user_id in (fixture["realtime_user_a_id"], fixture["realtime_user_b_id"]):
            for step in (1, 2, 3, 4, 5):
                set_onboarding_step(db, amo_id=fixture["amo_id"], user_id=user_id, step=step, completed=True)
        db.commit()
        print("Marked both real-time QMS browser users fully onboarded")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
