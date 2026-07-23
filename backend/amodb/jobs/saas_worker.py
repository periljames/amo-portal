from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import models as platform_models
from amodb.apps.platform import saas_models as models
from amodb.apps.platform import saas_providers, saas_services
from amodb.database import WriteSessionLocal, close_session_safely


ACTIVE_SUBSCRIPTION_STATES = {"active", "trialing"}
SUSPENDED_SUBSCRIPTION_STATES = {"past_due", "unpaid", "incomplete_expired", "paused"}
DISABLED_SUBSCRIPTION_STATES = {"canceled", "cancelled"}
TENANT_MUTATING_STRIPE_EVENTS = {
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_failed",
}


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


def _verified_stripe_tenant(
    job: models.SaaSJob,
    *,
    event_type: str,
    declared_tenant_id: str,
) -> str:
    verified_tenant_id = str(
        (job.payload_json or {}).get("verified_tenant_id") or ""
    ).strip()
    if event_type in TENANT_MUTATING_STRIPE_EVENTS and not verified_tenant_id:
        raise ValueError("Stripe webhook job is missing a cryptographically verified tenant")
    if (
        verified_tenant_id
        and declared_tenant_id
        and verified_tenant_id != declared_tenant_id
    ):
        raise ValueError("Stripe webhook declared tenant does not match the verified tenant")
    return verified_tenant_id


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
    declared_tenant_id = str(
        metadata.get("tenant_id") or obj.get("client_reference_id") or ""
    ).strip()
    tenant_id = _verified_stripe_tenant(
        job,
        event_type=event_type,
        declared_tenant_id=declared_tenant_id,
    )
    module_code = str(metadata.get("module_code") or "").strip()
    customer_ref = str(obj.get("customer") or "").strip() or None
    subscription_ref = str(obj.get("subscription") or obj.get("id") or "").strip() or None
    outcome: dict[str, Any] = {
        "event_type": event_type,
        "event_id": payload.get("id"),
        "verified_tenant_id": tenant_id or None,
    }

    if event_type == "checkout.session.completed":
        if not module_code:
            raise ValueError("Stripe checkout metadata is missing module_code")
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
        subscription_state = str(
            obj.get("status") or ("canceled" if event_type.endswith("deleted") else "")
        ).lower()
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
        invoice_id = str(metadata.get("portal_invoice_id") or "").strip()
        if invoice_id:
            invoice = (
                db.query(account_models.BillingInvoice)
                .filter(
                    account_models.BillingInvoice.id == invoice_id,
                    account_models.BillingInvoice.amo_id == tenant_id,
                )
                .first()
            )
            if invoice is None:
                raise ValueError("Portal invoice does not belong to the verified Stripe tenant")
            if event_type == "invoice.paid":
                invoice.status = account_models.InvoiceStatus.PAID
                invoice.paid_at = utcnow()
            else:
                invoice.status = account_models.InvoiceStatus.PENDING
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
        outcome.update({"tenant_id": tenant_id, "module_code": module_code or None, "portal_invoice_id": invoice_id or None})

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


def process_job(db: Session, job: models.SaaSJob) -> dict[str, Any]:
    if job.job_type == "PROVIDER_HEALTH_CHECK":
        return _process_provider_health(db, job)
    if job.job_type == "STRIPE_CREATE_CHECKOUT_SESSION":
        return _process_checkout(db, job)
    if job.job_type == "STRIPE_WEBHOOK":
        return _process_stripe_webhook(db, job)
    if job.job_type in {"ETIMS_FISCALIZE_INVOICE", "AI_SUPPORT_REPLY"}:
        raise RuntimeError("Non-repeatable side effects must run through amodb.jobs.saas_worker_safe")
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


def run_once(*, batch_size: int = 1, worker_id: str | None = None) -> dict[str, Any]:
    from amodb.jobs.saas_worker_safe import run_once as safe_run_once

    return safe_run_once(batch_size=batch_size, worker_id=worker_id)


def run_forever(*, poll_seconds: float = 1.0, batch_size: int = 1) -> None:
    from amodb.jobs.saas_worker_safe import run_forever as safe_run_forever

    safe_run_forever(poll_seconds=poll_seconds, batch_size=batch_size)


def main() -> None:
    from amodb.jobs.saas_worker_safe import main as safe_main

    safe_main()


if __name__ == "__main__":
    main()
