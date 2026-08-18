from __future__ import annotations

"""Durable tenant-governed external delivery for Training notifications.

In-app notifications remain canonical ``TrainingNotification`` rows. External
provider work is represented by idempotent ``TrainingWorkflowInstance`` outbox
rows. Every delivery decision that can differ by AMO is read from that tenant's
``notification_policy``; the portal does not invent reminder or retry schedules.
"""

import json
import os
import smtplib
import urllib.request
from dataclasses import dataclass
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
_ALLOWED_CHANNELS = {"EMAIL", "WHATSAPP"}


@dataclass(frozen=True)
class DeliveryPolicy:
    configured: bool
    enabled: bool
    channels: tuple[str, ...]
    mode: str
    max_attempts: int | None
    retry_base_seconds: int | None
    retry_ceiling_seconds: int | None
    escalation_user_ids: tuple[str, ...]
    error: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _int_value(value: Any, *, minimum: int, maximum: int) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if minimum <= parsed <= maximum else None


def delivery_policy(raw: dict[str, Any] | None) -> DeliveryPolicy:
    payload = dict(raw or {})
    delivery = payload.get("delivery")
    configured_channels = payload.get("external_channels")
    channels: list[str] = []
    if isinstance(configured_channels, (list, tuple)):
        channels.extend(str(item).strip().upper() for item in configured_channels if str(item).strip())
    if payload.get("email_enabled"):
        channels.append("EMAIL")
    if payload.get("whatsapp_enabled"):
        channels.append("WHATSAPP")
    channels = list(dict.fromkeys(item for item in channels if item in _ALLOWED_CHANNELS))

    if not channels:
        return DeliveryPolicy(False, False, (), "PARALLEL", None, None, None, ())
    if not isinstance(delivery, dict):
        return DeliveryPolicy(
            True,
            False,
            tuple(channels),
            "PARALLEL",
            None,
            None,
            None,
            (),
            "External Training notification channels require an explicit tenant delivery policy.",
        )
    if delivery.get("enabled") is not True:
        return DeliveryPolicy(True, False, tuple(channels), "PARALLEL", None, None, None, ())

    mode = str(delivery.get("mode") or "").strip().upper()
    if mode not in {"PARALLEL", "FALLBACK"}:
        return DeliveryPolicy(True, False, tuple(channels), mode or "UNKNOWN", None, None, None, (), "delivery.mode must be PARALLEL or FALLBACK.")
    max_attempts = _int_value(delivery.get("max_attempts"), minimum=1, maximum=20)
    retry_base = _int_value(delivery.get("retry_base_seconds"), minimum=1, maximum=86400)
    retry_ceiling = _int_value(delivery.get("retry_ceiling_seconds"), minimum=1, maximum=604800)
    if max_attempts is None or retry_base is None or retry_ceiling is None:
        return DeliveryPolicy(True, False, tuple(channels), mode, max_attempts, retry_base, retry_ceiling, (), "Enabled external delivery requires max_attempts, retry_base_seconds and retry_ceiling_seconds.")
    if retry_ceiling < retry_base:
        return DeliveryPolicy(True, False, tuple(channels), mode, max_attempts, retry_base, retry_ceiling, (), "retry_ceiling_seconds cannot be lower than retry_base_seconds.")
    escalation = delivery.get("escalation_user_ids")
    escalation_ids = tuple(dict.fromkeys(str(item).strip() for item in (escalation or []) if str(item).strip())) if isinstance(escalation, (list, tuple)) else ()
    return DeliveryPolicy(True, True, tuple(channels), mode, max_attempts, retry_base, retry_ceiling, escalation_ids)


def retry_delay_seconds(attempt_no: int, *, base_seconds: int, ceiling_seconds: int) -> int:
    attempt = max(1, int(attempt_no or 1))
    return min(int(ceiling_seconds), int(base_seconds) * (2 ** (attempt - 1)))


def _preferred_phone(user: object) -> str | None:
    for name in ("phone", "phone_number", "mobile", "mobile_number", "whatsapp_number"):
        value = str(getattr(user, name, None) or "").strip()
        if value:
            return value
    return None


def _delivery_address(user: account_models.User, channel: str) -> str | None:
    if channel == "EMAIL":
        return str(getattr(user, "email", None) or "").strip() or None
    if channel == "WHATSAPP":
        return _preferred_phone(user)
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
    policy: DeliveryPolicy,
    channel_index: int,
) -> dict[str, Any]:
    return {
        "notification_id": str(notification.id),
        "recipient_user_id": str(notification.user_id),
        "channel": channel,
        "channel_order": list(policy.channels),
        "channel_index": int(channel_index),
        "delivery_mode": policy.mode,
        "delivery_address": _delivery_address(user, channel),
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


def _queue_delivery(
    db: Session,
    *,
    notification: training_models.TrainingNotification,
    user: account_models.User,
    policy: DeliveryPolicy,
    channel_index: int,
) -> bool:
    if channel_index < 0 or channel_index >= len(policy.channels):
        return False
    channel = policy.channels[channel_index]
    idempotency_key = f"notification:{notification.id}:{channel.lower()}"
    existing = db.query(operating_models.TrainingWorkflowInstance.id).filter(
        operating_models.TrainingWorkflowInstance.amo_id == notification.amo_id,
        operating_models.TrainingWorkflowInstance.workflow_type == OUTBOX_WORKFLOW_TYPE,
        operating_models.TrainingWorkflowInstance.idempotency_key == idempotency_key,
    ).first()
    if existing:
        return False
    workflow = operating_models.TrainingWorkflowInstance(
        amo_id=notification.amo_id,
        workflow_type=OUTBOX_WORKFLOW_TYPE,
        title=f"{channel}: {notification.title}"[:255],
        status="QUEUED",
        subject_user_id=str(notification.user_id),
        owner_user_id=str(notification.created_by_user_id) if notification.created_by_user_id else None,
        due_at=_now(),
        data_json=_outbox_data(notification=notification, user=user, channel=channel, policy=policy, channel_index=channel_index),
        validation_result={},
        provenance={"source": "TrainingNotification", "notification_id": str(notification.id), "tenant_delivery_policy": True},
        idempotency_key=idempotency_key,
        revision_no=1,
        created_by_user_id=str(notification.created_by_user_id) if notification.created_by_user_id else None,
    )
    db.add(workflow)
    return True


def sync_notifications_to_outbox(db: Session, *, limit: int = 1000) -> dict[str, int]:
    summary = {"scanned": 0, "queued": 0, "deduped": 0, "missing_recipient": 0, "policy_invalid": 0}
    settings_by_amo = {str(row.amo_id): row for row in db.query(operating_models.TrainingOperatingSettings).all()}
    rows = db.query(training_models.TrainingNotification).order_by(training_models.TrainingNotification.created_at.desc()).limit(max(1, min(int(limit or 1000), 5000))).all()
    users: dict[tuple[str, str], account_models.User | None] = {}
    for notification in rows:
        summary["scanned"] += 1
        # Delivery-failure escalation rows are intentionally in-app only so a
        # provider outage cannot recursively generate provider-failure messages.
        if str(notification.dedupe_key or "").startswith("delivery-failure:"):
            continue
        settings = settings_by_amo.get(str(notification.amo_id))
        policy = delivery_policy(settings.notification_policy if settings and isinstance(settings.notification_policy, dict) else {})
        if policy.error:
            summary["policy_invalid"] += 1
            continue
        if not policy.enabled:
            continue
        key = (str(notification.amo_id), str(notification.user_id))
        if key not in users:
            users[key] = db.query(account_models.User).filter(account_models.User.id == notification.user_id, account_models.User.amo_id == notification.amo_id).first()
        user = users[key]
        if user is None:
            summary["missing_recipient"] += 1
            continue
        indexes = range(len(policy.channels)) if policy.mode == "PARALLEL" else range(min(1, len(policy.channels)))
        for channel_index in indexes:
            if _queue_delivery(db, notification=notification, user=user, policy=policy, channel_index=channel_index):
                summary["queued"] += 1
            else:
                summary["deduped"] += 1
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
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
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


def _record_transition(db: Session, *, workflow: operating_models.TrainingWorkflowInstance, prior: str, new: str, detail: dict[str, Any]) -> None:
    workflow.revision_no = int(workflow.revision_no or 0) + 1
    workflow.updated_at = _now()
    db.add(training_models.TrainingAuditLog(
        amo_id=workflow.amo_id,
        actor_user_id=None,
        action="NOTIFICATION_OUTBOX_TRANSITION",
        entity_type="TrainingWorkflowInstance",
        entity_id=str(workflow.id),
        details={"from": prior, "to": new, **detail},
    ))


def _escalate_terminal_failure(
    db: Session,
    *,
    workflow: operating_models.TrainingWorkflowInstance,
    policy: DeliveryPolicy,
    error: str,
) -> int:
    if not policy.escalation_user_ids:
        return 0
    created = 0
    source_notification_id = str((workflow.data_json or {}).get("notification_id") or "")
    for user_id in policy.escalation_user_ids:
        user = db.query(account_models.User).filter(
            account_models.User.id == user_id,
            account_models.User.amo_id == workflow.amo_id,
            account_models.User.is_active.is_(True),
        ).first()
        if user is None:
            continue
        dedupe = f"delivery-failure:{workflow.id}:{user_id}"
        exists = db.query(training_models.TrainingNotification.id).filter(
            training_models.TrainingNotification.amo_id == workflow.amo_id,
            training_models.TrainingNotification.user_id == user_id,
            training_models.TrainingNotification.dedupe_key == dedupe,
        ).first()
        if exists:
            continue
        db.add(training_models.TrainingNotification(
            amo_id=workflow.amo_id,
            user_id=user_id,
            title="Training notification delivery failed",
            body=f"External delivery failed after the tenant-configured retry/fallback policy. Source notification: {source_notification_id or 'unknown'}. Error: {error}",
            severity=training_models.TrainingNotificationSeverity.ACTION_REQUIRED,
            link_path="/training/competence/settings",
            dedupe_key=dedupe,
            created_by_user_id=None,
        ))
        created += 1
    return created


def process_outbox(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 100,
    max_attempts: int | None = None,
) -> dict[str, int]:
    """Deliver due messages using each row's current tenant delivery policy.

    ``max_attempts`` is retained only as an explicit test/operations override;
    normal production calls omit it and therefore use tenant policy exclusively.
    """
    clock = now or _now()
    summary = {"attempted": 0, "sent": 0, "retry_scheduled": 0, "failed": 0, "fallback_queued": 0, "escalated": 0, "policy_invalid": 0}
    settings_by_amo = {str(row.amo_id): row for row in db.query(operating_models.TrainingOperatingSettings).all()}
    rows = db.query(operating_models.TrainingWorkflowInstance).filter(
        operating_models.TrainingWorkflowInstance.workflow_type == OUTBOX_WORKFLOW_TYPE,
        operating_models.TrainingWorkflowInstance.status.in_(ACTIVE_DELIVERY_STATES),
        (operating_models.TrainingWorkflowInstance.due_at.is_(None) | (operating_models.TrainingWorkflowInstance.due_at <= clock)),
    ).order_by(operating_models.TrainingWorkflowInstance.due_at.asc(), operating_models.TrainingWorkflowInstance.created_at.asc()).limit(max(1, min(int(limit or 100), 1000))).all()
    for workflow in rows:
        settings = settings_by_amo.get(str(workflow.amo_id))
        policy = delivery_policy(settings.notification_policy if settings and isinstance(settings.notification_policy, dict) else {})
        data = dict(workflow.data_json or {})
        if policy.error or not policy.enabled or policy.max_attempts is None or policy.retry_base_seconds is None or policy.retry_ceiling_seconds is None:
            prior = str(workflow.status)
            error = policy.error or "Tenant external delivery policy is disabled or incomplete."
            workflow.status = "FAILED"; workflow.completed_at = clock; workflow.due_at = None
            data["last_error"] = error; data["next_attempt_at"] = None; workflow.data_json = data
            _record_transition(db, workflow=workflow, prior=prior, new="FAILED", detail={"last_error": error, "policy_invalid": True})
            summary["failed"] += 1; summary["policy_invalid"] += 1
            continue

        summary["attempted"] += 1
        prior = str(workflow.status)
        attempt_count = int(data.get("attempt_count") or 0) + 1
        data["attempt_count"] = attempt_count; data["last_attempt_at"] = clock.isoformat()
        workflow.status = "SENDING"; workflow.data_json = data
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
            data["provider_message_id"] = provider_id; data["last_error"] = None; data["sent_at"] = clock.isoformat(); data["next_attempt_at"] = None
            workflow.status = "SENT"; workflow.completed_at = clock; workflow.due_at = None; workflow.data_json = data
            _record_transition(db, workflow=workflow, prior="SENDING", new="SENT", detail={"attempt_count": attempt_count, "provider_message_id": provider_id})
            summary["sent"] += 1
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:4000]
            data["last_error"] = error
            permitted_attempts = int(max_attempts) if max_attempts is not None else int(policy.max_attempts)
            if attempt_count < max(1, permitted_attempts):
                delay = retry_delay_seconds(attempt_count, base_seconds=policy.retry_base_seconds, ceiling_seconds=policy.retry_ceiling_seconds)
                next_attempt = clock + timedelta(seconds=delay)
                workflow.status = "RETRY_SCHEDULED"; workflow.due_at = next_attempt; data["next_attempt_at"] = next_attempt.isoformat(); workflow.data_json = data
                _record_transition(db, workflow=workflow, prior="SENDING", new="RETRY_SCHEDULED", detail={"attempt_count": attempt_count, "last_error": error, "next_attempt_at": data["next_attempt_at"]})
                summary["retry_scheduled"] += 1
                continue

            workflow.status = "FAILED"; workflow.completed_at = clock; workflow.due_at = None; data["next_attempt_at"] = None; workflow.data_json = data
            fallback_created = False
            if policy.mode == "FALLBACK":
                notification_id = str(data.get("notification_id") or "")
                notification = db.query(training_models.TrainingNotification).filter(
                    training_models.TrainingNotification.id == notification_id,
                    training_models.TrainingNotification.amo_id == workflow.amo_id,
                ).first()
                user = db.query(account_models.User).filter(
                    account_models.User.id == data.get("recipient_user_id"),
                    account_models.User.amo_id == workflow.amo_id,
                ).first()
                next_index = int(data.get("channel_index") or 0) + 1
                if notification is not None and user is not None and next_index < len(policy.channels):
                    fallback_created = _queue_delivery(db, notification=notification, user=user, policy=policy, channel_index=next_index)
                    if fallback_created:
                        summary["fallback_queued"] += 1
            escalated = 0 if fallback_created else _escalate_terminal_failure(db, workflow=workflow, policy=policy, error=error)
            summary["escalated"] += escalated
            _record_transition(db, workflow=workflow, prior="SENDING", new="FAILED", detail={"attempt_count": attempt_count, "last_error": error, "fallback_queued": fallback_created, "escalated": escalated})
            summary["failed"] += 1
    return summary


__all__ = [
    "ACTIVE_DELIVERY_STATES",
    "DeliveryPolicy",
    "OUTBOX_WORKFLOW_TYPE",
    "TERMINAL_DELIVERY_STATES",
    "delivery_policy",
    "process_outbox",
    "retry_delay_seconds",
    "sync_notifications_to_outbox",
]
