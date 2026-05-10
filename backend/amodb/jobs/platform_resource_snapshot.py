from __future__ import annotations

from amodb.database import WriteSessionLocal
from amodb.apps.accounts import models as account_models
from amodb.apps.platform import models, services, metrics


def run_once() -> dict:
    db = WriteSessionLocal()
    created = 0
    try:
        live = metrics.live_summary()
        for amo in db.query(account_models.AMO).all():
            row = models.PlatformTenantResourceSnapshot(
                tenant_id=amo.id,
                api_requests_1h=0,
                api_requests_24h=0,
                storage_used_bytes=0,
                file_count=0,
                quota_percent=0,
                details_json={"source": "scheduled_snapshot", "live_metrics": live},
            )
            db.add(row); created += 1
        db.commit()
        return {"created": created}
    except Exception as exc:
        db.rollback(); return {"created": created, "error": str(exc)}
    finally:
        db.close()


if __name__ == "__main__":
    print(run_once())
