"""Quality task reminder/escalation runner.

Safe to run from cron. This replaces the old qms_task_runner naming while
keeping the old file available until deployment scripts are updated.
"""

from __future__ import annotations

from datetime import datetime, timezone

from amodb.database import WriteSessionLocal
from amodb.apps.tasks import services as task_services


def run() -> dict:
    db = WriteSessionLocal()
    try:
        summary = task_services.run_task_runner(db, now=datetime.now(timezone.utc))
        db.commit()
        return summary
    finally:
        db.close()


if __name__ == "__main__":
    result = run()
    print("Quality task runner completed:", result)
