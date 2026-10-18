from __future__ import annotations

import uuid
from datetime import datetime, timezone
from email.utils import getaddresses
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from amodb.apps.notifications import models as notification_models
from amodb.database import get_db, get_read_db

from . import saas_models, saas_queue, saas_services
from .resend_adapter import retrieve_email, send_email, verify_webhook
from .router import require_platform_superuser


router = APIRouter(prefix="/email/resend", tags=["platform-resend-email"])

RECOMMENDED_TEMPLATE_KEYS = (
    "account-welcome",
    "password-reset",
    "email-verification",
    "audit-assignment",
    "finding-issued",
    "corrective-action-reminder",
    "corrective-action-overdue",
    "task_reminder",
    "task_escalation",
    "qms_audit_schedule_notice",
    "qms_audit_notice_memo",
    "approval-request",
    "approval-result",
    "document-review-due",
    "training-expiry-warning",
    "authorization-expiry-warning",
    "daily-digest",
    "weekly-management-summary",
)


def _credential(db: Session, tenant_id: str | None = None):
    row = saas_services.get_provider_credential(
        db,
        provider="resend",
        tenant_id=tenant_id,
        allow_platform_fallback=True,
    )
    if row is None:
        raise HTTPException(status_code=409, detail="Resend is not configured")
    if str(row.status or "").upper() == "DISABLED":
        raise HTTPException(status_code=409, detail="Resend is disabled")
    return row


def _sender(config: dict[str, Any]) -> str:
    email = str(config.get("from_email") or "onboarding@resend.dev").strip()
    name = str(config.get("from_name") or "AMO Portal").strip()
    return f"{name} <{email}>" if name else email


def _job_payload(row: saas_models.SaaSJob) -> dict[str, Any]:
    return {
        "id": row.id,
        "queue_name": row.queue_name,
        "job_type": row.job_type,
        "tenant_id": row.tenant_id,
        "status": row.status,
        "result": row.result_json,
        "attempt_count": row.attempt_count,
        "max_attempts": row.max_attempts,
        "last_error": row.last_error,
        "created_at": row.created_at,
        "finished_at": row.finished_at,
    }


@router.get("/status")
def resend_status(
    tenant_id: str | None = None,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    row = saas_services.get_provider_credential(
        db,
        provider="resend",
        tenant_id=tenant_id,
        allow_platform_fallback=True,
    )
    if row is None:
        return {
            "provider": "resend",
            "status": "NOT_CONFIGURED",
            "has_secret": False,
            "template_keys": list(RECOMMENDED_TEMPLATE_KEYS),
        }
    return {**saas_services.provider_payload(row), "template_keys": list(RECOMMENDED_TEMPLATE_KEYS)}


@router.post("/test", status_code=status.HTTP_200_OK)
def resend_test_email(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    tenant_id = str(payload.get("tenant_id") or "").strip() or None
    recipient = str(payload.get("recipient") or "").strip()
    if "@" not in recipient:
        raise HTTPException(status_code=422, detail="A valid test recipient is required")
    row = _credential(db, tenant_id)
    config = dict(row.config_json or {})
    secret = saas_services.provider_secrets(row)
    api_key = str(secret.get("api_key") or "").strip()
    if not api_key:
        raise HTTPException(status_code=409, detail="Resend api_key is not configured")

    minute_key = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    job = saas_queue.enqueue_job(
        db,
        job_type="RESEND_TEST_EMAIL",
        queue_name="integrations",
        tenant_id=tenant_id,
        payload={"recipient": recipient, "credential_id": row.id},
        idempotency_key=f"resend-test:{row.id}:{recipient.lower()}:{minute_key}",
        correlation_id=str(uuid.uuid4()),
        created_by=str(user.id),
        max_attempts=1,
    )
    if job.status == "SUCCEEDED":
        return _job_payload(job)
    if job.status not in {"PENDING", "RETRY"}:
        raise HTTPException(status_code=409, detail="A test email for this recipient was already attempted this minute")

    try:
        result = send_email(
            api_key=api_key,
            api_url=str(config.get("api_base_url") or "https://api.resend.com"),
            from_value=_sender(config),
            to_email=recipient,
            subject="AMO Portal Resend integration test",
            html=(
                "<h2>Resend integration passed</h2>"
                "<p>This message was explicitly requested by a platform superuser. "
                "Normal portal email remains controlled by the configured sending mode and rate limits.</p>"
            ),
            text="AMO Portal Resend integration passed. Normal portal email remains controlled by the configured sending mode and rate limits.",
            reply_to=str(config.get("reply_to") or "").strip() or None,
            idempotency_key=job.idempotency_key,
            tags=[{"name": "source", "value": "amo_portal_test"}],
        )
        job.status = "SUCCEEDED"
        job.result_json = result
        job.finished_at = datetime.now(timezone.utc)
        job.last_error = None
        saas_queue.add_event(db, job, "SUCCEEDED", "Resend accepted the explicit test email.", result)
        row.status = "HEALTHY"
        row.last_checked_at = datetime.now(timezone.utc)
        row.last_health_detail = f"Test email accepted by Resend as {result.get('message_id')}"
        db.commit()
        db.refresh(job)
        return _job_payload(job)
    except Exception as exc:
        job.status = "FAILED"
        job.last_error = str(exc)[:4000]
        job.finished_at = datetime.now(timezone.utc)
        saas_queue.add_event(db, job, "FAILED", "Resend test email failed.", {"error": str(exc)[:1000]})
        row.status = "UNHEALTHY"
        row.last_checked_at = datetime.now(timezone.utc)
        row.last_health_detail = str(exc)[:2000]
        db.commit()
        raise HTTPException(status_code=502, detail=f"Resend test email failed: {exc}") from exc


@router.post("/webhook", include_in_schema=False)
async def resend_webhook(request: Request, db: Session = Depends(get_db)):
    platform_credential = saas_services.get_provider_credential(
        db,
        provider="resend",
        tenant_id=None,
        allow_platform_fallback=False,
    )
    if platform_credential is None:
        raise HTTPException(status_code=404, detail="Resend webhook is not configured")
    secret = saas_services.provider_secrets(platform_credential)
    payload = await request.body()
    try:
        event = verify_webhook(
            payload=payload,
            headers=request.headers,
            signing_secret=str(secret.get("webhook_signing_secret") or ""),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid Resend webhook signature") from exc

    event_type = str(event.get("type") or "").strip().lower()
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    message_id = str((data or {}).get("email_id") or (data or {}).get("id") or "").strip()
    svix_id = str(request.headers.get("svix-id") or "").strip()
    occurred_at = datetime.now(timezone.utc)
    matched_log_id: str | None = None
    duplicate = False
    if svix_id:
        existing_event = (
            db.query(notification_models.EmailDeliveryEvent)
            .filter(
                notification_models.EmailDeliveryEvent.provider == "resend",
                notification_models.EmailDeliveryEvent.provider_event_id == svix_id,
            )
            .first()
        )
        if existing_event is not None:
            duplicate = True
            matched_log_id = existing_event.email_log_id

    row = None
    if not duplicate and message_id:
        row = (
            db.query(notification_models.EmailLog)
            .filter(
                notification_models.EmailLog.provider == "resend",
                notification_models.EmailLog.provider_message_id == message_id,
            )
            .order_by(notification_models.EmailLog.created_at.desc())
            .first()
        )
        matched_log_id = row.id if row is not None else None

    if not duplicate:
        db.add(
            notification_models.EmailDeliveryEvent(
                email_log_id=matched_log_id,
                provider="resend",
                provider_event_id=svix_id or f"{message_id}:{event_type}:{occurred_at.isoformat()}",
                provider_message_id=message_id or None,
                event_type=event_type or "unknown",
                occurred_at=occurred_at,
                payload_json=event,
            )
        )

    if row is not None and not duplicate:
        context = dict(row.context_json or {})
        delivery = context.get("_delivery") if isinstance(context.get("_delivery"), dict) else {}

        def address_set(values: Any) -> set[str]:
            if values is None:
                return set()
            raw = values if isinstance(values, (list, tuple, set)) else [values]
            parsed = getaddresses([str(item) for item in raw])
            return {address.strip().lower() for _name, address in parsed if address.strip()}

        expected = address_set(delivery.get("effective_recipients"))
        impacted = address_set((data or {}).get("to"))
        delivered = address_set(delivery.get("delivered_recipients"))
        failed = address_set(delivery.get("failed_recipients"))
        event_at = str(event.get("created_at") or (data or {}).get("created_at") or occurred_at.isoformat())

        delivery["last_event_at"] = event_at
        delivery["webhook_signature_verified"] = True
        if event_type == "email.sent":
            if str(row.delivery_status or "").upper() not in {"DELIVERED", "PARTIALLY_DELIVERED"}:
                row.delivery_status = "SENT"
        elif event_type == "email.delivered":
            delivered.update(impacted or expected)
            delivery["delivered_recipients"] = sorted(delivered)
            if not expected or expected.issubset(delivered):
                row.delivery_status = "DELIVERED"
                delivery["delivered_at"] = delivery.get("delivered_at") or event_at
            else:
                row.delivery_status = "PARTIALLY_DELIVERED"
        elif event_type == "email.delivery_delayed":
            if str(row.delivery_status or "").upper() != "DELIVERED":
                row.delivery_status = "DELIVERY_DELAYED"
        elif event_type == "email.opened":
            delivery["opened_at"] = delivery.get("opened_at") or event_at
            delivery["engagement_status"] = "OPENED"
        elif event_type == "email.clicked":
            delivery["clicked_at"] = delivery.get("clicked_at") or event_at
            delivery["engagement_status"] = "CLICKED"
        elif event_type in {"email.failed", "email.bounced", "email.suppressed"}:
            failed.update(impacted or expected)
            delivery["failed_recipients"] = sorted(failed)
            if expected and expected.issubset(failed):
                row.delivery_status = event_type.removeprefix("email.").upper()
                row.status = notification_models.EmailStatus.FAILED
            else:
                row.delivery_status = "PARTIAL_FAILURE"
            row.error = f"Resend delivery event: {event_type}"
        elif event_type == "email.complained":
            delivery["complained_at"] = delivery.get("complained_at") or event_at
            delivery["engagement_status"] = "COMPLAINED"

        try:
            provider_snapshot = retrieve_email(
                api_key=str(secret.get("api_key") or ""),
                api_url=str((platform_credential.config_json or {}).get("api_base_url") or "https://api.resend.com"),
                email_id=message_id,
            )
            delivery["provider_reconciled_at"] = datetime.now(timezone.utc).isoformat()
            delivery["provider_last_event"] = str(provider_snapshot.get("last_event") or "").strip().upper() or None
            delivery["provider_message_id_header"] = str(provider_snapshot.get("message_id") or "").strip() or None
            delivery.pop("provider_reconciliation_error", None)
        except Exception as exc:
            delivery["provider_reconciliation_error"] = str(exc)[:500]

        delivery["status"] = str(row.delivery_status or "UNKNOWN")
        context["_delivery"] = delivery
        row.context_json = context
        row.last_delivery_event_at = occurred_at

        if row.delivery_status == "DELIVERED" and str(context.get("purpose") or "").strip().lower() == "audit-notice":
            from amodb.apps.quality import models as quality_models
            from amodb.apps.quality.audit_notice_models import QualityAuditNotice, QualityAuditNoticeEvent

            notice_id = str(context.get("notice_id") or "").strip()
            notice = (
                db.query(QualityAuditNotice)
                .filter(QualityAuditNotice.id == notice_id, QualityAuditNotice.amo_id == row.amo_id)
                .with_for_update()
                .first()
                if notice_id
                else None
            )
            if notice is not None and notice.status == "GENERATED":
                actor_user_id = str(context.get("issuer_user_id") or "").strip() or None
                notice.status = "DELIVERED"
                notice.delivered_by_user_id = actor_user_id
                notice.delivered_at = occurred_at
                notice.delivery_channel = "EMAIL"
                notice.delivery_reference = f"Resend confirmed delivery · {message_id}"
                audit = (
                    db.query(quality_models.QMSAudit)
                    .filter(
                        quality_models.QMSAudit.id == notice.audit_id,
                        quality_models.QMSAudit.amo_id == notice.amo_id,
                    )
                    .first()
                )
                if audit is not None:
                    audit.upcoming_notice_sent_at = occurred_at
                db.add(
                    QualityAuditNoticeEvent(
                        amo_id=notice.amo_id,
                        audit_id=notice.audit_id,
                        notice_id=notice.id,
                        event_type="DELIVERED",
                        reason=f"Signed Resend webhook confirmed delivery for provider email {message_id}.",
                        actor_user_id=actor_user_id,
                        created_at=occurred_at,
                    )
                )
    db.commit()
    return {
        "ok": True,
        "duplicate": duplicate,
        "event_type": event_type,
        "message_id": message_id or None,
        "email_log_id": matched_log_id,
    }
