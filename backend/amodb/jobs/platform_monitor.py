"""Periodic platform monitor: infrastructure + health snapshot writer.

The Operations Control Center and System Infrastructure superadmin views read
``platform_infrastructure_snapshots`` and ``platform_health_snapshots``. Those
tables previously had no periodic writer, so host CPU/memory, database
connections and API throughput rendered as "N/A" / "No Prometheus sample"
whenever an external Prometheus was not configured.

This module provides the lightweight collectors that the scheduled worker
(``portal_scheduler_main``) drives on a fixed cadence, plus a heartbeat so the
worker roster reflects the collector as online.
"""
from __future__ import annotations

import logging

from amodb.database import WriteSessionLocal
from amodb.apps.platform import diagnostics, models, network_diagnostics, services

logger = logging.getLogger(__name__)

INFRASTRUCTURE_WORKER_NAME = "platform_monitor"
HEALTH_WORKER_NAME = "platform_health_runner"


def _touch_heartbeat(db, name: str, worker_type: str = "monitor") -> None:
    hb = (
        db.query(models.PlatformWorkerHeartbeat)
        .filter(models.PlatformWorkerHeartbeat.worker_name == name)
        .first()
    )
    if hb is None:
        db.add(
            models.PlatformWorkerHeartbeat(
                worker_name=name, worker_type=worker_type, status="ONLINE"
            )
        )
    else:
        hb.status = "ONLINE"
        hb.last_seen_at = services.now_utc()


def capture_infrastructure_once() -> dict | None:
    """Write one infrastructure snapshot and refresh the collector heartbeat."""
    db = WriteSessionLocal()
    try:
        snap = services.capture_infrastructure_snapshot(db)
        _touch_heartbeat(db, INFRASTRUCTURE_WORKER_NAME)
        db.commit()
        return {
            "captured_at": snap.captured_at.isoformat() if snap.captured_at else None,
            "cpu_percent": snap.cpu_percent,
            "memory_percent": snap.memory_percent,
            "db_connections_active": snap.db_connections_active,
            "status": snap.status,
        }
    except Exception:
        logger.exception("platform infrastructure snapshot failed")
        try:
            db.rollback()
        except Exception:
            pass
        return None
    finally:
        db.close()


def capture_health_once(include_network: bool = False) -> dict | None:
    """Run the diagnostics probe and persist a health snapshot + heartbeat."""
    db = WriteSessionLocal()
    try:
        result = diagnostics.run_health_probe(db, include_network=include_network)
        services.create_health_snapshot(db, result)
        _touch_heartbeat(db, HEALTH_WORKER_NAME, worker_type="scheduler")
        db.commit()
        return {"status": result.get("status")}
    except Exception:
        logger.exception("platform health probe failed")
        try:
            db.rollback()
        except Exception:
            pass
        return None
    finally:
        db.close()


def run_network_probes_once(*, prune_days: int = 30) -> dict | None:
    """Run server->internet and server<->database probes, log them, and prune old rows."""
    db = WriteSessionLocal()
    try:
        internet = network_diagnostics.run_internet_speedtest()
        network_diagnostics.persist_probe(db, scenario="server_internet", source="scheduled", data=internet)
        database = network_diagnostics.run_database_throughput(db)
        network_diagnostics.persist_probe(db, scenario="server_database", source="scheduled", data=database)
        network_diagnostics.prune(db, days=prune_days)
        _touch_heartbeat(db, INFRASTRUCTURE_WORKER_NAME)
        db.commit()
        return {
            "internet_download_mbps": round((internet.get("download_bps") or 0) / 1_000_000, 2),
            "internet_ok": internet.get("ok"),
            "database_latency_ms": database.get("latency_ms"),
        }
    except Exception:
        logger.exception("network probe cycle failed")
        try:
            db.rollback()
        except Exception:
            pass
        return None
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    print(capture_infrastructure_once())
    print(capture_health_once(include_network=False))
    print(run_network_probes_once())
