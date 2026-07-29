from __future__ import annotations

import time

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
            row.last_latency_ms = float(result.get("latency_ms") or round((time.perf_counter() - started) * 1000, 2))
            healthy += 1
        except Exception as exc:
            row.status = "UNHEALTHY"
            row.last_health_detail = str(exc)[:2000]
            row.last_latency_ms = round((time.perf_counter() - started) * 1000, 2)
            unhealthy += 1
        row.last_checked_at = services.now_utc()
    return {"checked": checked, "healthy": healthy, "unhealthy": unhealthy}


def run_once() -> dict:
    db = WriteSessionLocal()
    updated = 0
    try:
        for provider, display_name in DEFAULT_PROVIDERS:
            row = db.query(models.PlatformIntegrationProvider).filter(models.PlatformIntegrationProvider.provider == provider).first()
            if not row:
                row = models.PlatformIntegrationProvider(provider=provider, display_name=display_name, status="NOT_CONFIGURED")
                db.add(row)
                updated += 1
            row.last_checked_at = services.now_utc()
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
