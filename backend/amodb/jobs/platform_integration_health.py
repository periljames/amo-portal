from __future__ import annotations

from amodb.database import WriteSessionLocal
from amodb.apps.platform import models, services

DEFAULT_PROVIDERS = [
    ("stripe", "Stripe"),
    ("google_workspace", "Google Workspace"),
    ("zoom_education", "Zoom Education SDK"),
    ("aws_s3", "AWS S3"),
    ("sendgrid", "SendGrid"),
    ("zendesk", "Zendesk"),
    ("jira", "Jira"),
    ("generic_webhook", "Generic Webhook"),
]


def run_once() -> dict:
    db = WriteSessionLocal()
    updated = 0
    try:
        for provider, display_name in DEFAULT_PROVIDERS:
            row = db.query(models.PlatformIntegrationProvider).filter(models.PlatformIntegrationProvider.provider == provider).first()
            if not row:
                row = models.PlatformIntegrationProvider(provider=provider, display_name=display_name, status="NOT_CONFIGURED")
                db.add(row); updated += 1
            row.last_checked_at = services.now_utc()
        db.commit()
        return {"updated": updated}
    except Exception as exc:
        db.rollback(); return {"updated": updated, "error": str(exc)}
    finally:
        db.close()


if __name__ == "__main__":
    print(run_once())
