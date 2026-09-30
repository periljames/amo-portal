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
import os
import statistics

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


def _float_setting(name: str, default: float, *, minimum: float = 1.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _ema(values: list[float], *, span: int = 20) -> float | None:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return None
    alpha = 2.0 / (max(2, int(span)) + 1.0)
    value = clean[0]
    for sample in clean[1:]:
        value = alpha * sample + (1.0 - alpha) * value
    return value


def _robust_z(value: float | None, values: list[float]) -> float | None:
    if value is None or len(values) < 7:
        return None
    median = statistics.median(values)
    deviations = [abs(sample - median) for sample in values]
    mad = statistics.median(deviations)
    if mad <= 0:
        return None
    return 0.6745 * (value - median) / mad


def _adaptive_network_policy(current: dict, previous_rows: list) -> dict:
    """Classify one cheap sentinel and select the next sampling interval."""
    window = max(5, int(_float_setting("PLATFORM_NET_ADAPTIVE_WINDOW", 20, minimum=5)))
    previous = list(previous_rows[:window])
    chronological = list(reversed(previous))

    def _baseline_eligible(row) -> bool:
        adaptive = ((getattr(row, "details_json", None) or {}).get("adaptive") or {})
        return bool(getattr(row, "ok", False)) and not bool(adaptive.get("anomalous"))

    download_history = [
        float(row.download_bps)
        for row in chronological
        if _baseline_eligible(row) and getattr(row, "download_bps", None) is not None
    ]
    latency_history = [
        float(row.latency_ms)
        for row in chronological
        if _baseline_eligible(row) and getattr(row, "latency_ms", None) is not None
    ]
    ema_download = _ema(download_history, span=window)
    ema_latency = _ema(latency_history, span=window)

    details = current.get("details") or {}
    failure_kind = details.get("failure_kind")
    provider_unavailable = failure_kind == "provider_rejected"
    reasons: list[str] = []

    if not current.get("ok") and not provider_unavailable:
        reasons.append("probe_failure")

    baseline_count = min(len(download_history), len(latency_history))
    download_drop_pct = None
    latency_rise_pct = None
    download_z = None
    latency_z = None
    if current.get("ok") and baseline_count >= 5:
        current_download = current.get("download_bps")
        current_latency = current.get("latency_ms")
        if current_download is not None and ema_download and ema_download > 0:
            download_drop_pct = max(0.0, (ema_download - float(current_download)) / ema_download * 100.0)
            if download_drop_pct >= _float_setting("PLATFORM_NET_ANOMALY_DOWNLOAD_DROP_PCT", 35.0):
                reasons.append("download_drop")
        if current_latency is not None and ema_latency and ema_latency > 0:
            latency_rise_pct = max(0.0, (float(current_latency) - ema_latency) / ema_latency * 100.0)
            if (
                latency_rise_pct >= _float_setting("PLATFORM_NET_ANOMALY_LATENCY_RISE_PCT", 75.0)
                and float(current_latency) - ema_latency >= _float_setting("PLATFORM_NET_ANOMALY_LATENCY_RISE_MS", 20.0)
            ):
                reasons.append("latency_spike")

        download_z = _robust_z(
            float(current_download) if current_download is not None else None,
            download_history,
        )
        latency_z = _robust_z(
            float(current_latency) if current_latency is not None else None,
            latency_history,
        )
        if download_z is not None and download_z <= -3.5 and "download_drop" not in reasons:
            reasons.append("download_outlier")
        if latency_z is not None and latency_z >= 3.5 and "latency_spike" not in reasons:
            reasons.append("latency_outlier")

    anomalous = bool(reasons)
    first_adaptive = (
        ((getattr(previous[0], "details_json", None) or {}).get("adaptive") or {})
        if previous
        else {}
    )
    previous_anomalous = bool(first_adaptive.get("anomalous"))
    healthy_run = 1 if current.get("ok") and not anomalous else 0
    anomaly_run = 1 if anomalous else 0
    for row in previous:
        adaptive = ((getattr(row, "details_json", None) or {}).get("adaptive") or {})
        row_anomalous = bool(adaptive.get("anomalous"))
        if anomalous and adaptive and row_anomalous:
            anomaly_run += 1
            continue
        if adaptive and healthy_run and getattr(row, "ok", False) and not row_anomalous:
            healthy_run += 1
            continue
        break

    noise_cv = None
    if len(download_history) >= 5:
        mean = statistics.fmean(download_history)
        if mean > 0:
            noise_cv = statistics.pstdev(download_history) / mean

    fast = _float_setting("PLATFORM_NET_INVESTIGATION_INTERVAL_SECONDS", 60.0, minimum=30.0)
    degraded = _float_setting("PLATFORM_NET_DEGRADED_INTERVAL_SECONDS", 300.0, minimum=60.0)
    persistent = _float_setting("PLATFORM_NET_PERSISTENT_INTERVAL_SECONDS", 900.0, minimum=300.0)
    recovery = _float_setting("PLATFORM_NET_RECOVERY_INTERVAL_SECONDS", 900.0, minimum=60.0)
    stable = _float_setting("PLATFORM_NET_STABLE_INTERVAL_SECONDS", 3600.0, minimum=300.0)
    deep_stable = _float_setting("PLATFORM_NET_DEEP_STABLE_INTERVAL_SECONDS", 7200.0, minimum=900.0)

    if provider_unavailable:
        state = "provider_unavailable"
        next_delay = stable
    elif anomalous and anomaly_run <= 2:
        state = "investigating"
        next_delay = fast
    elif anomalous and anomaly_run <= 5:
        state = "degraded"
        next_delay = degraded
    elif anomalous:
        state = "persistent_degradation"
        next_delay = persistent
    elif previous_anomalous or healthy_run < 6:
        state = "recovery"
        next_delay = recovery
    elif healthy_run >= window and noise_cv is not None and noise_cv <= 0.15:
        state = "deep_stable"
        next_delay = deep_stable
    else:
        state = "stable"
        next_delay = stable

    return {
        "state": state,
        "next_delay_seconds": round(next_delay, 2),
        "anomalous": anomalous,
        "confirmed_anomaly": anomalous and previous_anomalous,
        "provider_unavailable": provider_unavailable,
        "reasons": reasons,
        "baseline_count": baseline_count,
        "healthy_run": healthy_run,
        "anomaly_run": anomaly_run,
        "ema_span": window,
        "ema_download_bps": round(ema_download, 2) if ema_download is not None else None,
        "ema_latency_ms": round(ema_latency, 2) if ema_latency is not None else None,
        "download_drop_pct": round(download_drop_pct, 2) if download_drop_pct is not None else None,
        "latency_rise_pct": round(latency_rise_pct, 2) if latency_rise_pct is not None else None,
        "download_robust_z": round(download_z, 2) if download_z is not None else None,
        "latency_robust_z": round(latency_z, 2) if latency_z is not None else None,
        "baseline_cv": round(noise_cv, 4) if noise_cv is not None else None,
    }


def run_adaptive_network_probe_once(*, prune_days: int = 30) -> dict | None:
    """Run a cheap sentinel and escalate to a bounded full test only when useful."""
    db = WriteSessionLocal()
    try:
        previous = (
            db.query(models.PlatformNetworkProbe)
            .filter(
                models.PlatformNetworkProbe.scenario == "server_internet",
                models.PlatformNetworkProbe.source == "scheduled_light",
            )
            .order_by(models.PlatformNetworkProbe.captured_at.desc())
            .limit(max(20, int(_float_setting("PLATFORM_NET_ADAPTIVE_WINDOW", 20, minimum=5))))
            .all()
        )
        sentinel = network_diagnostics.run_internet_sentinel()
        policy = _adaptive_network_policy(sentinel, previous)
        sentinel_details = dict(sentinel.get("details") or {})
        sentinel_details["adaptive"] = policy
        sentinel["details"] = sentinel_details
        network_diagnostics.persist_probe(
            db,
            scenario="server_internet",
            source="scheduled_light",
            data=sentinel,
        )

        database = network_diagnostics.run_database_latency_probe(db)
        database_details = dict(database.get("details") or {})
        database_details["adaptive_state"] = policy["state"]
        database["details"] = database_details
        network_diagnostics.persist_probe(
            db,
            scenario="server_database",
            source="scheduled_light",
            data=database,
        )

        full_history = (
            db.query(models.PlatformNetworkProbe)
            .filter(
                models.PlatformNetworkProbe.scenario == "server_internet",
                models.PlatformNetworkProbe.source == "scheduled_full",
            )
            .order_by(models.PlatformNetworkProbe.captured_at.desc())
            .limit(20)
            .all()
        )
        last_full_attempt = full_history[0] if full_history else None
        last_full_success = next((row for row in full_history if getattr(row, "ok", False)), None)
        full_refresh = _float_setting("PLATFORM_NET_FULL_REFRESH_INTERVAL_SECONDS", 43200.0, minimum=1800.0)
        full_cooldown = _float_setting("PLATFORM_NET_FULL_ANOMALY_COOLDOWN_SECONDS", 900.0, minimum=300.0)
        incident_cooldown = _float_setting("PLATFORM_NET_FULL_INCIDENT_COOLDOWN_SECONDS", 7200.0, minimum=1800.0)
        failure_backoff = _float_setting("PLATFORM_NET_FULL_FAILURE_BACKOFF_SECONDS", 3600.0, minimum=900.0)

        def _age(row) -> float | None:
            if row is None or getattr(row, "captured_at", None) is None:
                return None
            return max(0.0, (network_diagnostics._now() - row.captured_at).total_seconds())

        attempt_age = _age(last_full_attempt)
        success_age = _age(last_full_success)
        attempt_ready = attempt_age is None or attempt_age >= failure_backoff
        last_trigger = (
            ((getattr(last_full_attempt, "details_json", None) or {}).get("trigger"))
            if last_full_attempt is not None
            else None
        )
        anomaly_wait = incident_cooldown if last_trigger == "confirmed_anomaly" else full_cooldown
        anomaly_ready = attempt_age is None or attempt_age >= anomaly_wait

        full_due = False
        full_reason = None
        if not policy["provider_unavailable"]:
            if last_full_attempt is None and sentinel.get("ok"):
                full_due = True
                full_reason = "bootstrap"
            elif policy["confirmed_anomaly"] and anomaly_ready:
                full_due = True
                full_reason = "confirmed_anomaly"
            elif last_full_success is None and attempt_ready and sentinel.get("ok"):
                full_due = True
                full_reason = "retry_after_failed_full"
            elif success_age is not None and success_age >= full_refresh and attempt_ready:
                full_due = True
                full_reason = "periodic_refresh"

        full_internet = None
        full_database = None
        if full_due:
            full_internet = network_diagnostics.run_internet_speedtest()
            full_details = dict(full_internet.get("details") or {})
            full_details["trigger"] = full_reason
            full_internet["details"] = full_details
            network_diagnostics.persist_probe(
                db,
                scenario="server_internet",
                source="scheduled_full",
                data=full_internet,
            )

            full_database = network_diagnostics.run_database_throughput(db)
            db_details = dict(full_database.get("details") or {})
            db_details["trigger"] = full_reason
            full_database["details"] = db_details
            network_diagnostics.persist_probe(
                db,
                scenario="server_database",
                source="scheduled_full",
                data=full_database,
            )
            network_diagnostics.prune(db, days=prune_days)

        _touch_heartbeat(db, INFRASTRUCTURE_WORKER_NAME)
        db.commit()
        return {
            "adaptive_state": policy["state"],
            "next_delay_seconds": policy["next_delay_seconds"],
            "sentinel_ok": sentinel.get("ok"),
            "sentinel_download_mbps": round(float(sentinel["download_bps"]) / 1_000_000, 2)
            if sentinel.get("download_bps") is not None
            else None,
            "sentinel_latency_ms": sentinel.get("latency_ms"),
            "anomalous": policy["anomalous"],
            "confirmed_anomaly": policy["confirmed_anomaly"],
            "anomaly_reasons": policy["reasons"],
            "ema_download_mbps": round(float(policy["ema_download_bps"]) / 1_000_000, 2)
            if policy.get("ema_download_bps") is not None
            else None,
            "ema_latency_ms": policy.get("ema_latency_ms"),
            "full_probe_ran": full_due,
            "full_probe_reason": full_reason,
            "full_download_mbps": round(float(full_internet["download_bps"]) / 1_000_000, 2)
            if full_internet and full_internet.get("download_bps") is not None
            else None,
            "database_latency_ms": database.get("latency_ms"),
        }
    except Exception:
        logger.exception("adaptive network probe cycle failed")
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
        internet_bps = internet.get("download_bps")
        return {
            "internet_download_mbps": round(internet_bps / 1_000_000, 2) if internet_bps is not None else None,
            "internet_ok": internet.get("ok"),
            "internet_error": internet.get("error"),
            "internet_failure_kind": (internet.get("details") or {}).get("failure_kind"),
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
