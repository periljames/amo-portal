from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone

from sqlalchemy import text

from amodb.database import WriteSessionLocal
from amodb.apps.platform import models, saas_models, saas_providers, saas_services, services

DEFAULT_PROVIDERS = [
    ("stripe", "Stripe"),
    ("google_workspace", "Google Workspace"),
    ("zoom_education", "Zoom Education SDK"),
    ("aws_s3", "AWS S3"),
    ("resend", "Resend"),
    ("zendesk", "Zendesk"),
    ("jira", "Jira"),
    ("generic_webhook", "Generic Webhook"),
]


def _elapsed_ms(started: float) -> int:
    return max(0, int(round((time.perf_counter() - started) * 1000)))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _acquire_health_lock(db) -> bool:
    """Allow one worker replica to decide whether the periodic probe is due."""

    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return True
    digest = hashlib.sha256(b"amo-portal:platform-integration-health").digest()
    lock_key = int.from_bytes(digest[:8], byteorder="big", signed=False) & 0x7FFF_FFFF_FFFF_FFFF
    return bool(
        db.execute(
            text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        ).scalar()
    )


def _check_resend_credentials(db) -> dict[str, int]:
    checked = 0
    healthy = 0
    unhealthy = 0
    rows = (
        db.query(saas_models.SaaSProviderCredential)
        .filter(
            saas_models.SaaSProviderCredential.provider == "resend",
            saas_models.SaaSProviderCredential.status != "DISABLED",
        )
        .all()
    )
    for row in rows:
        checked += 1
        started = time.perf_counter()
        try:
            result = saas_providers.check_provider(
                "resend",
                secret=saas_services.provider_secrets(row),
                config=row.config_json or {},
            )
            row.status = "HEALTHY"
            row.last_health_detail = str(result.get("detail") or "Resend API authentication passed")[:2000]
            row.last_latency_ms = int(result.get("latency_ms") or _elapsed_ms(started))
            healthy += 1
        except Exception as exc:
            row.status = "UNHEALTHY"
            row.last_health_detail = str(exc)[:2000]
            row.last_latency_ms = _elapsed_ms(started)
            unhealthy += 1
        row.last_checked_at = services.now_utc()
    return {"checked": checked, "healthy": healthy, "unhealthy": unhealthy}


def run_once(*, min_interval_seconds: int = 0) -> dict:
    db = WriteSessionLocal()
    updated = 0
    try:
        if not _acquire_health_lock(db):
            db.rollback()
            return {"skipped": True, "reason": "another worker owns the health-check lock"}

        now = services.now_utc()
        tracker = (
            db.query(models.PlatformIntegrationProvider)
            .filter(models.PlatformIntegrationProvider.provider == "resend")
            .first()
        )
        minimum = max(0, int(min_interval_seconds or 0))
        if minimum and tracker and tracker.last_checked_at:
            elapsed = (now - _as_utc(tracker.last_checked_at)).total_seconds()
            if elapsed < minimum:
                db.rollback()
                return {
                    "skipped": True,
                    "reason": "health check is not due",
                    "seconds_until_due": max(0, int(minimum - elapsed)),
                }

        for provider, display_name in DEFAULT_PROVIDERS:
            row = db.query(models.PlatformIntegrationProvider).filter(models.PlatformIntegrationProvider.provider == provider).first()
            if not row:
                row = models.PlatformIntegrationProvider(provider=provider, display_name=display_name, status="NOT_CONFIGURED")
                db.add(row)
                updated += 1
            row.last_checked_at = now
        resend = _check_resend_credentials(db)
        db.commit()
        return {"updated": updated, "resend": resend}
    except Exception as exc:
        db.rollback()
        return {"updated": updated, "error": str(exc)}
    finally:
        db.close()


if __name__ == "__main__":
    print(run_once())
