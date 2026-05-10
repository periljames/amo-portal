from __future__ import annotations

import logging

from sqlalchemy import text

from amodb.database import WriteSessionLocal
from amodb.apps.platform import diagnostics, metrics, models, services

logger = logging.getLogger(__name__)


def run_once() -> dict:
    db = WriteSessionLocal()
    try:
        result = diagnostics.run_health_probe(db, include_network=True)
        services.create_health_snapshot(db, result)
        hb = db.query(models.PlatformWorkerHeartbeat).filter(models.PlatformWorkerHeartbeat.worker_name == "platform_health_runner").first()
        if not hb:
            hb = models.PlatformWorkerHeartbeat(worker_name="platform_health_runner", worker_type="scheduler", status="ONLINE")
            db.add(hb)
        else:
            hb.status = "ONLINE"
            hb.last_seen_at = services.now_utc()
        db.commit()
        return result
    except Exception as exc:
        logger.exception("Platform health runner failed")
        try:
            db.rollback()
            row = models.PlatformHealthSnapshot(status="CRITICAL", details_json={"error": str(exc)[:500]})
            db.add(row); db.commit()
        except Exception:
            db.rollback()
        return {"status": "CRITICAL", "error": str(exc)}
    finally:
        db.close()


if __name__ == "__main__":
    print(run_once())
