from __future__ import annotations

import hashlib
import inspect
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import WriteSessionLocal

from . import models, providers


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _acquire_delivery_lock(db: Session, *, amo_id: str) -> None:
    """Serialize delivery decisions for one tenant inside the DB transaction."""

    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    digest = hashlib.sha256(f"resend:{amo_id}".encode("utf-8")).digest()
    lock_key = int.from_bytes(digest[:8], byteorder="big", signed=False) & 0x7FFF_FFFF_FFFF_FFFF
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})


def _resolve_provider(*, db: Session, amo_id: str):
    """Call the DB-aware resolver while retaining legacy zero-argument test fakes.

    Existing notification integrations monkeypatch this seam with a zero-argument
    callable. Signature inspection avoids catching and masking a genuine TypeError
    raised from inside the production resolver.
    """

    resolver = providers.get_email_provider
    parameters = inspect.signature(resolver).parameters.values()
    accepts_keywords = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters)
    parameter_names = {parameter.name for parameter in parameters}
    if accepts_keywords or {"db", "amo_id"}.issubset(parameter_names):
        return resolver(db=db, amo_id=amo_id)
    return resolver()


def _existing_delivery(
    db: Session,
    *,
    amo_id: str,
    recipient: str,
    template_key: str,
    correlation_id: str | None,
) -> models.EmailLog | None:
    if not correlation_id:
        return None
    return (
        db.query(models.EmailLog)
        .filter(
            models.EmailLog.amo_id == amo_id,
            models.EmailLog.recipient == recipient,
            models.EmailLog.template_key == template_key,
            models.EmailLog.correlation_id == correlation_id,
            models.EmailLog.status == models.EmailStatus.SENT,
        )
        .order_by(models.EmailLog.created_at.desc())
        .first()
    )


def _enforce_rate_limits(db: Session, *, amo_id: str, config: dict) -> None:
    now = _utcnow()
    per_minute = max(1, min(int(config.get("per_minute_limit") or 10), 60))
    daily = max(1, min(int(config.get("daily_limit") or 500), 100000))
    sent_query = db.query(models.EmailLog).filter(
        models.EmailLog.amo_id == amo_id,
        models.EmailLog.status == models.EmailStatus.SENT,
    )
    recent_count = sent_query.filter(models.EmailLog.sent_at >= now - timedelta(minutes=1)).count()
    if recent_count >= per_minute:
        raise providers.EmailDeliveryBlocked(
            f"Resend portal rate limit reached: {per_minute} email(s) per minute"
        )
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_count = sent_query.filter(models.EmailLog.sent_at >= day_start).count()
    if daily_count >= daily:
        raise providers.EmailDeliveryBlocked(
            f"Resend portal daily limit reached: {daily} email(s) per UTC day"
        )


def send_email(
    template_key: str,
    recipient: Optional[str],
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
    cleaned_recipient = (recipient or "").strip()
    normalized_recipient = cleaned_recipient or "unknown"

    try:
        _acquire_delivery_lock(db, amo_id=amo_id)
        existing = _existing_delivery(
            db,
            amo_id=amo_id,
            recipient=normalized_recipient,
            template_key=template_key,
            correlation_id=correlation_id,
        )
        if existing is not None:
            return existing

        safe_context = dict(context or {})
        log = models.EmailLog(
            amo_id=amo_id,
            recipient=normalized_recipient,
            subject=subject,
            template_key=template_key,
            status=models.EmailStatus.QUEUED,
            context_json=safe_context,
            correlation_id=correlation_id,
        )
        db.add(log)
        db.flush()

        if not cleaned_recipient:
            log.status = models.EmailStatus.FAILED
            log.error = "Missing recipient email"
            db.add(log)
            if owns_session:
                db.commit()
            if critical:
                raise ValueError("Missing recipient email")
            return log

        try:
            provider, configured = _resolve_provider(db=db, amo_id=amo_id)
        except Exception as exc:
            log.status = models.EmailStatus.FAILED
            log.error = str(exc)
            db.add(log)
            if owns_session:
                db.commit()
            if critical:
                raise
            return log

        if not configured:
            log.status = models.EmailStatus.SKIPPED_NO_PROVIDER
            log.error = "Resend is not configured"
            db.add(log)
            if owns_session:
                db.commit()
            return log

        try:
            _enforce_rate_limits(db, amo_id=amo_id, config=getattr(provider, "config", {}))
            result = provider.send(
                template_key=template_key,
                recipient=cleaned_recipient,
                subject=subject,
                context=safe_context,
                correlation_id=correlation_id or f"email-log:{log.id}",
            ) or {}
            delivery = {
                "provider": str(result.get("provider") or "resend"),
                "message_id": result.get("message_id"),
                "status": "SENT",
                "mode": result.get("mode"),
                "effective_recipient": result.get("recipient") or cleaned_recipient,
                "original_recipient": result.get("original_recipient") or cleaned_recipient,
                "template_id": result.get("template_id"),
                "accepted_at": _utcnow().isoformat(),
            }
            safe_context["_delivery"] = delivery
            log.context_json = safe_context
            log.status = models.EmailStatus.SENT
            log.sent_at = _utcnow()
            log.error = None
        except providers.EmailDeliveryBlocked as exc:
            log.status = models.EmailStatus.SKIPPED_NO_PROVIDER
            log.error = str(exc)
            if critical:
                db.add(log)
                if owns_session:
                    db.commit()
                raise
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
