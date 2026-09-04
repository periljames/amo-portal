from __future__ import annotations

import hashlib
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import WriteSessionLocal

from . import models, policy, providers


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _acquire_delivery_lock(db: Session) -> None:
    """Serialize platform-wide Resend rate decisions inside the DB transaction."""

    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    digest = hashlib.sha256(b"resend:platform-delivery").digest()
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


def _enforce_rate_limits(db: Session, *, config: dict) -> None:
    now = _utcnow()
    per_minute = max(1, min(int(config.get("per_minute_limit") or 10), 60))
    daily = max(1, min(int(config.get("daily_limit") or 500), 100000))
    sent_query = db.query(models.EmailLog).filter(models.EmailLog.status == models.EmailStatus.SENT)
    recent_count = sent_query.filter(models.EmailLog.sent_at >= now - timedelta(minutes=1)).count()
    if recent_count >= per_minute:
        raise providers.EmailDeliveryBlocked(
            f"Resend platform rate limit reached: {per_minute} email(s) per minute"
        )
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_count = sent_query.filter(models.EmailLog.sent_at >= day_start).count()
    if daily_count >= daily:
        raise providers.EmailDeliveryBlocked(
            f"Resend platform daily limit reached: {daily} email(s) per UTC day"
        )


def _requires_isolated_delivery_session(audit_context: Optional[dict]) -> bool:
    """Keep account-recovery delivery evidence independent of request teardown.

    Password-reset token creation is committed before delivery. Its email log must
    therefore also commit independently so signed provider webhooks can always
    reconcile against the stored provider message ID, even though the endpoint's
    request-owned SQLAlchemy session is closed without another commit.
    """

    purpose = str((audit_context or {}).get("purpose") or "").strip().lower()
    return purpose == "password-reset"


def _normalise_attachments(attachments: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    rows = list(attachments or [])
    if len(rows) > 10:
        raise ValueError("An email may contain at most 10 attachments")
    cleaned: list[dict[str, Any]] = []
    total_bytes = 0
    for index, row in enumerate(rows):
        filename = Path(str(row.get("filename") or "")).name.strip()
        content = row.get("content")
        if not filename:
            raise ValueError(f"attachments[{index}].filename is required")
        if not isinstance(content, (bytes, bytearray, memoryview)):
            raise ValueError(f"attachments[{index}].content must be bytes")
        payload = bytes(content)
        if not payload:
            raise ValueError(f"attachments[{index}].content is empty")
        total_bytes += len(payload)
        if total_bytes > 25 * 1024 * 1024:
            raise ValueError("Email attachments exceed the 25 MiB portal limit")
        cleaned.append({
            "filename": filename[:255],
            "content": payload,
            "content_type": str(row.get("content_type") or "application/octet-stream")[:128],
        })
    return cleaned


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
    email_class: policy.EmailClass | str = policy.EmailClass.ROUTINE,
    recipient_user_id: Optional[str] = None,
    audit_context: Optional[dict] = None,
    attachments: list[dict[str, Any]] | None = None,
) -> models.EmailLog:
    if not amo_id:
        raise ValueError("amo_id is required to create an email log entry")

    isolated_session = db is not None and _requires_isolated_delivery_session(audit_context)
    owns_session = db is None or isolated_session
    db = WriteSessionLocal() if isolated_session else (db or WriteSessionLocal())
    cleaned_recipient = (recipient or "").strip()
    normalized_recipient = cleaned_recipient or "unknown"

    try:
        _acquire_delivery_lock(db)
        existing = _existing_delivery(
            db,
            amo_id=amo_id,
            recipient=normalized_recipient,
            template_key=template_key,
            correlation_id=correlation_id,
        )
        if existing is not None:
            return existing

        delivery_context = dict(context or {})
        delivery_attachments = _normalise_attachments(attachments)
        safe_context = dict(audit_context if audit_context is not None else delivery_context)
        classification = policy.normalize_email_class(email_class, critical=critical)
        delivery_context.setdefault("_email_class", classification.value)
        safe_context["_email_class"] = classification.value
        if delivery_attachments:
            safe_context["_attachments"] = [
                {
                    "filename": item["filename"],
                    "content_type": item["content_type"],
                    "size_bytes": len(item["content"]),
                }
                for item in delivery_attachments
            ]
        log = models.EmailLog(
            amo_id=amo_id,
            recipient=normalized_recipient,
            subject=subject,
            template_key=template_key,
            status=models.EmailStatus.QUEUED,
            context_json=safe_context,
            correlation_id=correlation_id,
            delivery_status="QUEUED",
        )
        db.add(log)
        db.flush()

        if not cleaned_recipient:
            log.status = models.EmailStatus.FAILED
            log.error = "Missing recipient email"
            log.delivery_status = "FAILED"
            db.add(log)
            if owns_session:
                db.commit()
            if critical:
                raise ValueError("Missing recipient email")
            return log

        allowed, preference_reason = policy.email_allowed(
            db,
            amo_id=amo_id,
            recipient_user_id=recipient_user_id,
            recipient_email=cleaned_recipient,
            email_class=classification,
        )
        if not allowed:
            log.status = models.EmailStatus.SKIPPED_BY_PREFERENCE
            log.delivery_status = "SKIPPED_BY_PREFERENCE"
            log.error = preference_reason
            db.add(log)
            if owns_session:
                db.commit()
            return log

        try:
            provider, configured = _resolve_provider(db=db, amo_id=amo_id)
        except Exception as exc:
            log.status = models.EmailStatus.FAILED
            log.error = str(exc)
            log.delivery_status = "FAILED"
            db.add(log)
            if owns_session:
                db.commit()
            if critical:
                raise
            return log

        if not configured:
            log.status = models.EmailStatus.SKIPPED_NO_PROVIDER
            log.delivery_status = "BLOCKED"
            log.error = "Resend is not configured"
            db.add(log)
            if owns_session:
                db.commit()
            return log

        try:
            _enforce_rate_limits(db, config=getattr(provider, "config", {}))
            provider_kwargs: dict[str, Any] = {
                "template_key": template_key,
                "recipient": cleaned_recipient,
                "subject": subject,
                "context": delivery_context,
                "correlation_id": correlation_id or f"email-log:{log.id}",
            }
            if delivery_attachments:
                provider_kwargs["attachments"] = delivery_attachments
            result = provider.send(
                **provider_kwargs,
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
            log.provider = str(result.get("provider") or "resend")
            log.provider_message_id = str(result.get("message_id") or "").strip() or None
            log.delivery_status = "ACCEPTED"
        except providers.EmailDeliveryBlocked as exc:
            log.status = models.EmailStatus.SKIPPED_NO_PROVIDER
            log.error = str(exc)
            log.provider = "resend"
            log.delivery_status = "BLOCKED"
            if critical:
                db.add(log)
                if owns_session:
                    db.commit()
                raise
        except Exception as exc:
            log.status = models.EmailStatus.FAILED
            log.error = str(exc)
            log.provider = "resend"
            log.delivery_status = "FAILED"
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
