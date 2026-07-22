from __future__ import annotations

import argparse
import json
import os
import socket
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import models as platform_models
from amodb.apps.platform import saas_models as models
from amodb.apps.platform import saas_providers, saas_queue, saas_services
from amodb.database import WriteSessionLocal, close_session_safely


ACTIVE_SUBSCRIPTION_STATES = {"active", "trialing"}
SUSPENDED_SUBSCRIPTION_STATES = {"past_due", "unpaid", "incomplete_expired", "paused"}
DISABLED_SUBSCRIPTION_STATES = {"canceled", "cancelled"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _worker_id() -> str:
    return os.getenv("SAAS_WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}"


def _credential(db: Session, credential_id: str) -> models.SaaSProviderCredential:
    row = db.get(models.SaaSProviderCredential, credential_id)
    if not row:
        raise ValueError("Provider credential not found")
    return row


def _upsert_billing_account(
    db: Session,
    *,
    tenant_id: str,
    provider: str,
    customer_ref: str | None,
    subscription_ref: str | None,
    status: str,
    metadata: dict[str, Any] | None = None,
) -> models.SaaSBillingAccount:
    row = (
        db.query(models.SaaSBillingAccount)
        .filter(
            models.SaaSBillingAccount.tenant_id == tenant_id,
            models.SaaSBillingAccount.provider == provider,
        )
        .first()
    )
    if not row:
        row = models.SaaSBillingAccount(tenant_id=tenant_id, provider=provider)
        db.add(row)
    if customer_ref:
        row.external_customer_ref = customer_ref
    if subscription_ref:
        row.external_subscription_ref = subscription_ref
    row.status = status.upper()
    row.auto_collection = True
    row.metadata_json = metadata or row.metadata_json or {}
    db.flush()
    return row


def _set_module_state(
    db: Session,
    *,
    tenant_id: str,
    module_code: str,
    status: str,
    provider: str,
    external_subscription_ref: str | None,
) -> None:
    normalized = saas_services.normalize_module_code(module_code)
    row = (
        db.query(account_models.ModuleSubscription)
        .filter(
            account_models.ModuleSubscription.amo_id == tenant_id,
            account_models.ModuleSubscription.module_code == normalized,
        )
        .first()
    )
    if not row:
        row = account_models.ModuleSubscription(amo_id=tenant_id, module_code=normalized)
        db.add(row)
    row.status = account_models.ModuleSubscriptionStatus(status)
    if status in {"ENABLED", "TRIAL"}:
        row.effective_from = row.effective_from or utcnow()
        row.effective_to = None
    elif status == "DISABLED":
        row.effective_to = utcnow()
    row.metadata_json = json.dumps(
        {
            "billing_provider": provider,
            "external_subscription_ref": external_subscription_ref,
            "updated_by": "verified_webhook",
        },
        separators=(",", ":"),
    )


def _stripe_metadata(obj: dict[str, Any]) -> dict[str, Any]:
    metadata = obj.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    parent = obj.get("subscription_details") or {}
    parent_metadata = parent.get("metadata") if isinstance(parent, dict) else None
    if isinstance(parent_metadata, dict):
        metadata = {**parent_metadata, **metadata}
    return metadata


def _process_stripe_webhook(db: Session, job: models.SaaSJob) -> dict[str, Any]:
    event_id = str((job.payload_json or {}).get("webhook_event_id") or "")
    event = db.get(account_models.WebhookEvent, event_id)
    if not event:
        raise ValueError("Stored Stripe webhook event not found")
    payload = json.loads(event.payload)
    event_type = str(payload.get("type") or "")
    obj = ((payload.get("data") or {}).get("object") or {})
    if not isinstance(obj, dict):
        raise ValueError("Stripe event object is invalid")
    metadata = _stripe_metadata(obj)
    tenant_id = str(
        metadata.get("tenant_id")
        or obj.get("client_reference_id")
        or ""
    ).strip()
    module_code = str(metadata.get("module_code") or "").strip()
    customer_ref = str(obj.get("customer") or "").strip() or None
    subscription_ref = str(obj.get("subscription") or obj.get("id") or "").strip() or None
    outcome: dict[str, Any] = {"event_type": event_type, "event_id": payload.get("id")}

    if event_type == "checkout.session.completed":
        if not tenant_id or not module_code:
            raise ValueError("Stripe checkout metadata is missing tenant_id or module_code")
        payment_status = str(obj.get("payment_status") or "").lower()
        _upsert_billing_account(
            db,
            tenant_id=tenant_id,
            provider="stripe",
            customer_ref=customer_ref,
            subscription_ref=subscription_ref,
            status="ACTIVE" if payment_status in {"paid", "no_payment_required"} else "CHECKOUT_COMPLETED",
            metadata={"checkout_session_id": obj.get("id"), "module_code": module_code},
        )
        if payment_status in {"paid", "no_payment_required"}:
            _set_module_state(
                db,
                tenant_id=tenant_id,
                module_code=module_code,
                status="ENABLED",
                provider="stripe",
                external_subscription_ref=subscription_ref,
            )
        outcome.update({"tenant_id": tenant_id, "module_code": module_code, "payment_status": payment_status})

    elif event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        tenant_id = tenant_id or str(metadata.get("tenant_id") or "").strip()
        module_code = module_code or str(metadata.get("module_code") or "").strip()
        subscription_state = str(obj.get("status") or ("canceled" if event_type.endswith("deleted") else "")).lower()
        if not tenant_id:
            raise ValueError("Stripe subscription metadata is missing tenant_id")
        _upsert_billing_account(
            db,
            tenant_id=tenant_id,
            provider="stripe",
            customer_ref=customer_ref,
            subscription_ref=str(obj.get("id") or subscription_ref or "") or None,
            status=subscription_state or "UNKNOWN",
            metadata={"module_code": module_code, "stripe_status": subscription_state},
        )
        if module_code:
            if subscription_state in ACTIVE_SUBSCRIPTION_STATES:
                module_state = "TRIAL" if subscription_state == "trialing" else "ENABLED"
            elif subscription_state in SUSPENDED_SUBSCRIPTION_STATES:
                module_state = "SUSPENDED"
            elif subscription_state in DISABLED_SUBSCRIPTION_STATES:
                module_state = "DISABLED"
            else:
                module_state = "SUSPENDED"
            _set_module_state(
                db,
                tenant_id=tenant_id,
                module_code=module_code,
                status=module_state,
                provider="stripe",
                external_subscription_ref=str(obj.get("id") or "") or None,
            )
        outcome.update({"tenant_id": tenant_id, "module_code": module_code, "subscription_status": subscription_state})

    elif event_type in {"invoice.paid", "invoice.payment_failed"}:
        tenant_id = tenant_id or str(metadata.get("tenant_id") or "").strip()
        module_code = module_code or str(metadata.get("module_code") or "").strip()
        invoice_id = str(metadata.get("portal_invoice_id") or "").strip()
        if invoice_id:
            invoice = db.get(account_models.BillingInvoice, invoice_id)
            if invoice:
                if event_type == "invoice.paid":
                    invoice.status = account_models.InvoiceStatus.PAID
                    invoice.paid_at = utcnow()
                else:
                    invoice.status = account_models.InvoiceStatus.PENDING
        if tenant_id:
            account = _upsert_billing_account(
                db,
                tenant_id=tenant_id,
                provider="stripe",
                customer_ref=customer_ref,
                subscription_ref=subscription_ref,
                status="ACTIVE" if event_type == "invoice.paid" else "PAST_DUE",
                metadata={"last_stripe_invoice": obj.get("id"), "module_code": module_code},
            )
            if module_code and event_type == "invoice.payment_failed":
                _set_module_state(
                    db,
                    tenant_id=tenant_id,
                    module_code=module_code,
                    status="SUSPENDED",
                    provider="stripe",
                    external_subscription_ref=account.external_subscription_ref,
                )
        outcome.update({"tenant_id": tenant_id or None, "module_code": module_code or None, "portal_invoice_id": invoice_id or None})

    else:
        outcome["ignored"] = True

    event.status = account_models.WebhookStatus.PROCESSED
    event.processed_at = utcnow()
    event.attempt_count = int(event.attempt_count or 0) + 1
    event.last_error = None
    db.flush()
    return outcome


def _process_provider_health(db: Session, job: models.SaaSJob) -> dict[str, Any]:
    credential = _credential(db, str((job.payload_json or {}).get("credential_id") or ""))
    try:
        result = saas_providers.check_provider(
            credential.provider,
            secret=saas_services.provider_secrets(credential),
            config=credential.config_json or {},
        )
    except Exception as exc:
        credential.status = "UNHEALTHY"
        credential.last_checked_at = utcnow()
        credential.last_health_detail = str(exc)[:2000]
        credential.last_latency_ms = None
        db.flush()
        raise
    credential.status = "HEALTHY"
    credential.last_checked_at = utcnow()
    credential.last_latency_ms = int(float(result.get("latency_ms") or 0))
    credential.last_health_detail = "Provider health check passed."
    db.flush()
    return result


def _process_checkout(db: Session, job: models.SaaSJob) -> dict[str, Any]:
    payload = job.payload_json or {}
    credential = _credential(db, str(payload.get("provider_credential_id") or ""))
    result = saas_providers.create_stripe_checkout_session(
        secret=saas_services.provider_secrets(credential),
        config=credential.config_json or {},
        tenant_id=str(job.tenant_id),
        tenant_email=payload.get("tenant_email"),
        module_code=str(payload.get("module_code") or ""),
        price_ref=str(payload.get("external_price_ref") or ""),
        idempotency_key=job.idempotency_key,
    )
    _upsert_billing_account(
        db,
        tenant_id=str(job.tenant_id),
        provider="stripe",
        customer_ref=result.get("customer"),
        subscription_ref=result.get("subscription"),
        status="CHECKOUT_PENDING",
        metadata={"checkout_session_id": result.get("session_id"), "module_code": payload.get("module_code")},
    )
    db.flush()
    return result


def _invoice_for_etims(invoice: account_models.BillingInvoice) -> dict[str, Any]:
    tenant = invoice.amo
    return {
        "portal_invoice_id": invoice.id,
        "invoice_number": account_services.format_invoice_number(invoice),
        "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
        "currency": invoice.currency,
        "total_amount_cents": invoice.amount_cents,
        "description": invoice.description,
        "buyer": {
            "tenant_id": invoice.amo_id,
            "name": getattr(tenant, "name", None),
            "email": getattr(tenant, "contact_email", None),
            "phone": getattr(tenant, "contact_phone", None),
            "country": getattr(tenant, "country", None),
        },
    }


def _process_etims(db: Session, job: models.SaaSJob) -> dict[str, Any]:
    payload = job.payload_json or {}
    fiscal = db.get(models.SaaSInvoiceFiscalization, str(payload.get("fiscalization_id") or ""))
    credential = _credential(db, str(payload.get("credential_id") or ""))
    if not fiscal:
        raise ValueError("Fiscalization record not found")
    invoice = db.get(account_models.BillingInvoice, fiscal.invoice_id)
    if not invoice:
        raise ValueError("Invoice not found")
    fiscal.status = "SUBMITTED"
    fiscal.submitted_at = utcnow()
    fiscal.request_json = _invoice_for_etims(invoice)
    db.flush()
    try:
        result = saas_providers.fiscalize_etims_invoice(
            provider=credential.provider,
            secret=saas_services.provider_secrets(credential),
            config=credential.config_json or {},
            invoice_payload=fiscal.request_json,
        )
    except Exception as exc:
        fiscal.status = "FAILED"
        fiscal.last_error = str(exc)[:4000]
        db.flush()
        raise
    fiscal.status = "FISCALIZED"
    fiscal.fiscalized_at = utcnow()
    fiscal.fiscal_document_number = result.get("fiscal_document_number")
    fiscal.control_unit_serial = result.get("control_unit_serial")
    fiscal.receipt_signature = result.get("receipt_signature")
    fiscal.response_json = result.get("raw") or result
    fiscal.last_error = None
    db.flush()
    return saas_services.fiscalization_payload(fiscal) or {}


def _process_ai_support(db: Session, job: models.SaaSJob) -> dict[str, Any]:
    payload = job.payload_json or {}
    ticket_id = str(payload.get("ticket_id") or "")
    ticket = db.get(platform_models.PlatformSupportTicket, ticket_id)
    credential = _credential(db, str(payload.get("credential_id") or ""))
    if not ticket:
        raise ValueError("Support ticket not found")
    detail = db.get(models.SaaSSupportTicketDetail, ticket_id)
    messages = (
        db.query(models.SaaSSupportTicketMessage)
        .filter(
            models.SaaSSupportTicketMessage.ticket_id == ticket_id,
            models.SaaSSupportTicketMessage.visibility == "PUBLIC",
        )
        .order_by(models.SaaSSupportTicketMessage.created_at.desc())
        .limit(20)
        .all()
    )
    transcript = "\n".join(
        f"{message.author_type}: {message.body}" for message in reversed(messages)
    )
    instructions = (
        "You are the AMO Portal support assistant. Give a factual, safe troubleshooting reply. "
        "Do not claim that actions were performed. Do not expose secrets. Escalate aviation safety, billing disputes, "
        "security incidents, tax/fiscalization issues, or account access changes to a human support agent."
    )
    result = saas_providers.openai_support_response(
        secret=saas_services.provider_secrets(credential),
        config=credential.config_json or {},
        instructions=instructions,
        user_message=f"Ticket: {ticket.title}\nCategory: {getattr(detail, 'category', 'GENERAL')}\nConversation:\n{transcript}",
    )
    message = models.SaaSSupportTicketMessage(
        ticket_id=ticket_id,
        author_type="AI_ASSISTANT",
        visibility="PUBLIC",
        body=str(result.get("text") or ""),
    )
    db.add(message)
    ticket.updated_at = utcnow()
    db.flush()
    return {"ticket_id": ticket_id, "message_id": message.id, "provider": "openai", "usage": result.get("usage") or {}}


def process_job(db: Session, job: models.SaaSJob) -> dict[str, Any]:
    if job.job_type == "PROVIDER_HEALTH_CHECK":
        return _process_provider_health(db, job)
    if job.job_type == "STRIPE_CREATE_CHECKOUT_SESSION":
        return _process_checkout(db, job)
    if job.job_type == "STRIPE_WEBHOOK":
        return _process_stripe_webhook(db, job)
    if job.job_type == "ETIMS_FISCALIZE_INVOICE":
        return _process_etims(db, job)
    if job.job_type == "AI_SUPPORT_REPLY":
        return _process_ai_support(db, job)
    raise ValueError(f"Unsupported SaaS job type: {job.job_type}")


def _heartbeat(db: Session, worker_id: str, *, status: str = "ONLINE") -> None:
    row = (
        db.query(platform_models.PlatformWorkerHeartbeat)
        .filter(platform_models.PlatformWorkerHeartbeat.worker_name == worker_id)
        .first()
    )
    if not row:
        row = platform_models.PlatformWorkerHeartbeat(
            worker_name=worker_id,
            worker_type="saas_queue",
        )
        db.add(row)
    row.status = status
    row.last_seen_at = utcnow()
    row.metadata_json = {"queues": ["billing", "integrations", "fiscalization", "ai", "default"]}
    db.commit()


def run_once(*, batch_size: int = 10, worker_id: str | None = None) -> dict[str, Any]:
    worker_id = worker_id or _worker_id()
    db = WriteSessionLocal()
    processed = 0
    failed = 0
    try:
        _heartbeat(db, worker_id)
        jobs = saas_queue.claim_jobs(
            db,
            worker_id=worker_id,
            queue_names=("billing", "integrations", "fiscalization", "ai", "default"),
            batch_size=batch_size,
            lease_seconds=int(os.getenv("SAAS_JOB_LEASE_SECONDS", "90")),
        )
        for job in jobs:
            try:
                result = process_job(db, job)
                saas_queue.complete_job(db, job, result)
                processed += 1
            except Exception as exc:
                if job.job_type == "STRIPE_WEBHOOK":
                    event_id = str((job.payload_json or {}).get("webhook_event_id") or "")
                    event = db.get(account_models.WebhookEvent, event_id)
                    if event:
                        event.status = account_models.WebhookStatus.FAILED
                        event.attempt_count = int(event.attempt_count or 0) + 1
                        event.last_error = str(exc)[:4000]
                        db.flush()
                saas_queue.fail_job(db, job, exc, retryable=job.job_type != "AI_SUPPORT_REPLY")
                failed += 1
        _heartbeat(db, worker_id)
        return {"worker_id": worker_id, "claimed": len(jobs), "processed": processed, "failed": failed}
    finally:
        close_session_safely(db)


def run_forever(*, poll_seconds: float = 1.0, batch_size: int = 10) -> None:
    worker_id = _worker_id()
    while True:
        result = run_once(batch_size=batch_size, worker_id=worker_id)
        if result["claimed"] == 0:
            time.sleep(max(0.25, min(poll_seconds, 30.0)))


def main() -> None:
    parser = argparse.ArgumentParser(description="AMO Portal durable SaaS worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("SAAS_WORKER_BATCH_SIZE", "10")))
    parser.add_argument("--poll-seconds", type=float, default=float(os.getenv("SAAS_WORKER_POLL_SECONDS", "1")))
    args = parser.parse_args()
    if args.once:
        print(json.dumps(run_once(batch_size=args.batch_size), default=str))
    else:
        run_forever(poll_seconds=args.poll_seconds, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
