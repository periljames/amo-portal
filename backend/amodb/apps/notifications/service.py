from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from amodb.database import WriteSessionLocal

from . import models, providers


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def send_email(
    template_key: str,
    recipient: str,
    subject: str,
    context: dict,
    correlation_id: Optional[str],
    critical: bool = False,
    *,
    amo_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> models.EmailLog:
    owns_session = db is None
    db = db or WriteSessionLocal()
    if not amo_id:
        raise ValueError("amo_id is required to create an email log entry")
    log = models.EmailLog(
        amo_id=amo_id,
        recipient=recipient,
        subject=subject,
        template_key=template_key,
        status=models.EmailStatus.QUEUED,
        context_json=context or {},
        correlation_id=correlation_id,
    )
    try:
        db.add(log)
        db.flush()

        provider, configured = providers.get_email_provider()
        if not configured:
            log.status = models.EmailStatus.SKIPPED_NO_PROVIDER
            log.error = "No provider configured"
            db.add(log)
            if owns_session:
                db.commit()
            return log

        try:
            provider.send(
                template_key=template_key,
                recipient=recipient,
                subject=subject,
                context=context or {},
                correlation_id=correlation_id,
            )
            log.status = models.EmailStatus.SENT
            log.sent_at = _utcnow()
        except Exception as exc:
            log.status = models.EmailStatus.FAILED
            log.error = str(exc)
            if critical:
                db.add(log)
                if owns_session:
                    db.commit()
                raise
        db.add(log)
        if owns_session:
            db.commit()
        return log
    finally:
        if owns_session:
            db.close()
