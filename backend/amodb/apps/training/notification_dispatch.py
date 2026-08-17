from __future__ import annotations

"""Durable external delivery for Training notifications.

The Training domain already owns an in-app ``TrainingNotification`` record and a
versioned/idempotent ``TrainingWorkflowInstance`` runtime.  This module reuses
those primitives instead of adding a parallel message table:

* one NOTIFICATION_OUTBOX workflow per notification/channel;
* QUEUED -> SENDING -> SENT, or retryable failure -> RETRY_SCHEDULED -> FAILED;
* tenant policy chooses external channels;
* provider message identifiers, attempts and errors remain auditable in data_json;
* the unique workflow idempotency constraint prevents duplicate sends.

External channels are opt-in per tenant.  Supported policy shapes include:

    {"external_channels": ["EMAIL", "WHATSAPP"]}

or the compatibility booleans ``email_enabled`` / ``whatsapp_enabled``.
"""

import json
import os
import smtplib
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Any

from sqlalchemy.orm import Session

from ..accounts import models as account_models
from . import models as training_models
from . import operating_models

UTC = timezone.utc
OUTBOX_WORKFLOW_TYPE = "NOTIFICATION_OUTBOX"
ACTIVE_DELIVERY_STATES = ("QUEUED", "RETRY_SCHEDULED")
TERMINAL_DELIVERY_STATES = ("SENT", "DELIVERED", "READ", "FAILED")


def _now() -> datetime:
    return datetime.now(UTC)


def _normalise_channels(policy: dict[str, Any] | None) -> tuple[str, ...]:
    raw = dict(policy or {})
    selected: list[str] = []
    configured = raw.get("external_channels")
    if isinstance(configured, (list, tuple, set)):
        selected.extend(str(item).strip().upper() for item in configured if str(item).strip())
    if raw.get("email_enabled"):
        selected.append("EMAIL")
    if raw.get("whatsapp_enabled"):
        selected.append("WHATSAPP")
    # IN_APP is already persisted as TrainingNotification; never duplicate it here.
    return tuple(dict.fromkeys(item for item in selected if item in {"EMAIL", "WHATSAPP"}))


def retry_delay_seconds(attempt_no: int, *, base_seconds: int = 60, ceiling_seconds: int = 6 * 60 * 60) -> int:
    """Bounded exponential retry delay used by the scheduled worker."""
    attempt = max(1, int(attempt_no or 1))
    return min(int(ceiling_seconds), int(base_seconds) * (2 ** (attempt - 1)))


def _preferred_phone(user: object) -> str | None:
    for name in ("phone", "phone_number", "mobile", "mobile_number", "whatsapp_number"):
        value = str(getattr(user, name, None) or "").strip()
        if value:
            return value
    return None


def _absolute_action_link(path: str | None) -> str | None:
    if not path:
        return None
    raw = str(path).strip()
    if raw.startswith("https://") or raw.startswith("http://"):
        return raw
    base = str(os.getenv("APP_PUBLIC_BASE_URL") or os.getenv("PLATFORM_API_BASE_URL") or "").strip().rstrip("/")
    if not base:
        return raw
    return f"{base}/{raw.lstrip('/')}"


def _message_body(notification: training_models.TrainingNotification) -> str:
    parts = [str(notification.body or "").strip()]
    action = _absolute_action_link(notification.link_path)
    if action:
        parts.extend(["", f"Open: {action}"])
    return "\n".join(part for part in parts if part is not None).strip()


def _outbox_data(
    *,
    notification: training_models.TrainingNotification,
    user: account_models.User,
    channel: str,
    address: str | None,
) -> dict[str, Any]:
    return {
        "notification_id": str(notification.id),
        "recipient_user_id": str(notification.user_id),
        "channel": channel,
        "delivery_address": address,
        "title": notification.title,
        "body": _message_body(notification),
        "link_path": notification.link_path,
        "notification_dedupe_key": notification.dedupe_key,
        "severity": str(getattr(notification.severity, "value", notification.severity)),
        "attempt_count": 0,
        "provider_message_id": None,
        "last_error": None,
        "next_attempt_at": None,
        "sent_at": None,
        "delivered_at": None,
        "read_at": None,
    }


def sync_notifications_to_outbox(db: Session, *, limit: int = 1000) -> dict[str, int]:
    """Materialise tenant-enabled external deliveries for existing in-app notifications."""
    summary = {"scanned": 0, "queued": 0, "deduped": 0, "missing_recipient": 0}
    settings_by_amo = {
        str(row.amo_id): row
        for row in db.query(operating_models.TrainingOperatingSettings).all()
    }
    rows = (
        db.query(training_models.TrainingNotification)
        .order_by(training_models.TrainingNotification.created_at.desc())
        .limit(max(1, min(int(limit or 1000), 5000)))
        .all()
    )
    users: dict[tuple[str, str], account_models.User | None] = {}
    for notification in rows:
        summary["scanned"] += 1
        amo_id = str(notification.amo_id)
        settings = settings_by_amo.get(amo_id)
        policy = settings.notification_policy if settings and isinstance(settings.notification_policy, dict) else {}
        channels = _normalise_channels(policy)
        if not channels:
            continue
        key = (amo_id, str(notification.user_id))
        if key not in users:
            users[key] = (
                db.query(account_models.User)
                .filter(account_models.User.id == notification.user_id, account_models.User.amo_id == notification.amo_id)
                .first()
            )
        user = users[key]
        if user is None:
            summary["missing_recipient"] += len(channels)
            continue
        for channel in channels:
            idempotency_key = f"notification:{notification.id}:{channel.lower()}"
            existing = (
                db.query(operating_models.TrainingWorkflowInstance.id)
                .filter(
                    operating_models.TrainingWorkflowInstance.amo_id == notification.amo_id,
                    operating_models.TrainingWorkflowInstance.workflow_type == OUTBOX_WORKFLOW_TYPE,
                    operating_models.TrainingWorkflowInstance.idempotency_key == idempotency_key,
                )
                .first()
            )
            if existing:
                summary["deduped"] += 1
                continue
            address = str(getattr(user, "email", None) or "").strip() if channel == "EMAIL" else _preferred_phone(user)
            workflow = operating_models.TrainingWorkflowInstance(
                amo_id=notification.amo_id,
                workflow_type=OUTBOX_WORKFLOW_TYPE,
                title=f"{channel}: {notification.title}"[:255],
                status="QUEUED",
                subject_user_id=str(notification.user_id),
                owner_user_id=str(notification.created_by_user_id) if notification.created_by_user_id else None,
                due_at=_now(),
                data_json=_outbox_data(notification=notification, user=user, channel=channel, address=address),
                validation_result={},
                provenance={"source": "TrainingNotification", "notification_id": str(notification.id)},
                idempotency_key=idempotency_key,
                revision_no=1,
                created_by_user_id=str(notification.created_by_user_id) if notification.created_by_user_id else None,
            )
            db.add(workflow)
            summary["queued"] += 1
    return summary


def _deliver_email(*, address: str, subject: str, body: str) -> str:
    host = str(os.getenv("SMTP_HOST") or "").strip()
    port = int(os.getenv("SMTP_PORT") or 587)
    sender = str(os.getenv("SMTP_FROM") or "").strip()
    if not host or not sender:
        raise RuntimeError("SMTP provider is not configured")
    if not address or "@" not in address:
        raise RuntimeError("Recipient has no valid email address")
    message = EmailMessage()
    message_id = make_msgid()
    message["Message-ID"] = message_id
    message["From"] = sender
    message["To"] = address
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(host, port, timeout=15) as client:
        if str(os.getenv("SMTP_STARTTLS", "1")).strip().lower() not in {"0", "false", "no"}:
            client.starttls()
        username = str(os.getenv("SMTP_USER") or "").strip()
        password = str(os.getenv("SMTP_PASS") or "")
        if username:
            client.login(username, password)
        client.send_message(message)
    return message_id


def _deliver_whatsapp(*, address: str, body: str) -> str:
    url = str(os.getenv("WHATSAPP_WEBHOOK_URL") or "").strip()
    if not url:
        raise RuntimeError("WhatsApp provider is not configured")
    if not address:
        raise RuntimeError("Recipient has no WhatsApp/phone address")
    payload = json.dumps({"to": address, "message": body}).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    token = str(os.getenv("WHATSAPP_WEBHOOK_BEARER") or "").strip()
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - tenant-configured provider endpoint
        raw = response.read().decode("utf-8", errors="replace")
        status_code = getattr(response, "status", 200)
    provider_id: str | None = None
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                provider_id = str(parsed.get("message_id") or parsed.get("id") or "").strip() or None
        except json.JSONDecodeError:
            provider_id = None
    return provider_id or f"http:{status_code}"


def _record_transition(
    db: Session,
    *,
    workflow: operating_models.TrainingWorkflowInstance,
    prior: str,
    new: str,
    detail: dict[str, Any],
) -> None:
    workflow.revision_no = int(workflow.revision_no or 0) + 1
    workflow.updated_at = _now()
    db.add(
        training_models.TrainingAuditLog(
            amo_id=workflow.amo_id,
            actor_user_id=None,
            action="NOTIFICATION_OUTBOX_TRANSITION",
            entity_type="TrainingWorkflowInstance",
            entity_id=str(workflow.id),
            details={"from": prior, "to": new, **detail},
        )
    )


def process_outbox(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 100,
    max_attempts: int = 5,
) -> dict[str, int]:
    """Deliver queued messages synchronously inside the dedicated scheduler worker."""
    clock = now or _now()
    summary = {"attempted": 0, "sent": 0, "retry_scheduled": 0, "failed": 0}
    rows = (
        db.query(operating_models.TrainingWorkflowInstance)
        .filter(
            operating_models.TrainingWorkflowInstance.workflow_type == OUTBOX_WORKFLOW_TYPE,
            operating_models.TrainingWorkflowInstance.status.in_(ACTIVE_DELIVERY_STATES),
            (operating_models.TrainingWorkflowInstance.due_at.is_(None) | (operating_models.TrainingWorkflowInstance.due_at <= clock)),
        )
        .order_by(operating_models.TrainingWorkflowInstance.due_at.asc(), operating_models.TrainingWorkflowInstance.created_at.asc())
        .limit(max(1, min(int(limit or 100), 1000)))
        .all()
    )
    for workflow in rows:
        summary["attempted"] += 1
        prior = str(workflow.status)
        data = dict(workflow.data_json or {})
        attempt_count = int(data.get("attempt_count") or 0) + 1
        data["attempt_count"] = attempt_count
        data["last_attempt_at"] = clock.isoformat()
        workflow.status = "SENDING"
        workflow.data_json = data
        _record_transition(db, workflow=workflow, prior=prior, new="SENDING", detail={"attempt_count": attempt_count})
        db.flush()
        try:
            channel = str(data.get("channel") or "").upper()
            address = str(data.get("delivery_address") or "").strip()
            subject = str(data.get("title") or "Training notification")
            body = str(data.get("body") or "")
            if channel == "EMAIL":
                provider_id = _deliver_email(address=address, subject=subject, body=body)
            elif channel == "WHATSAPP":
                provider_id = _deliver_whatsapp(address=address, body=body)
            else:
                raise RuntimeError(f"Unsupported Training notification channel: {channel or 'blank'}")
            data["provider_message_id"] = provider_id
            data["last_error"] = None
            data["sent_at"] = clock.isoformat()
            data["next_attempt_at"] = None
            workflow.status = "SENT"
            workflow.completed_at = clock
            workflow.due_at = None
            workflow.data_json = data
            _record_transition(db, workflow=workflow, prior="SENDING", new="SENT", detail={"attempt_count": attempt_count, "provider_message_id": provider_id})
            summary["sent"] += 1
        except Exception as exc:  # provider boundary; failure details are persisted for operations
            error = f"{type(exc).__name__}: {exc}"[:4000]
            data["last_error"] = error
            if attempt_count >= max(1, int(max_attempts or 1)):
                workflow.status = "FAILED"
                workflow.completed_at = clock
                workflow.due_at = None
                data["next_attempt_at"] = None
                summary["failed"] += 1
                next_state = "FAILED"
            else:
                delay = retry_delay_seconds(attempt_count)
                next_attempt = clock + timedelta(seconds=delay)
                workflow.status = "RETRY_SCHEDULED"
                workflow.due_at = next_attempt
                data["next_attempt_at"] = next_attempt.isoformat()
                summary["retry_scheduled"] += 1
                next_state = "RETRY_SCHEDULED"
            workflow.data_json = data
            _record_transition(db, workflow=workflow, prior="SENDING", new=next_state, detail={"attempt_count": attempt_count, "last_error": error, "next_attempt_at": data.get("next_attempt_at")})
    return summary


__all__ = [
    "ACTIVE_DELIVERY_STATES",
    "OUTBOX_WORKFLOW_TYPE",
    "TERMINAL_DELIVERY_STATES",
    "process_outbox",
    "retry_delay_seconds",
    "sync_notifications_to_outbox",
]
