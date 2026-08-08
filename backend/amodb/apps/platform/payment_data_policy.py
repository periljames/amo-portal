from __future__ import annotations

import json

from sqlalchemy.orm import Session

from . import commercial_integrations as integrations
from . import commercial_services, saas_queue, saas_services


_INSTALLED = False


def _safe_paystack_webhook(
    db: Session,
    *,
    raw_payload: bytes,
    signature: str,
):
    """Persist only identifiers required for server-side payment verification."""
    payload = json.loads(raw_payload.decode("utf-8"))
    event_type = str(payload.get("event") or "").strip().lower()
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        raise ValueError("Paystack event data is invalid")

    metadata = commercial_services._metadata_dict(data.get("metadata"))
    tenant_id = str(metadata.get("tenant_id") or "").strip()
    invoice_id = str(metadata.get("portal_invoice_id") or "").strip()
    reference = str(data.get("reference") or "").strip()
    if not tenant_id or not invoice_id or not reference:
        raise ValueError("Paystack event is missing portal tenant, invoice or reference metadata")

    credential = commercial_services._provider_credential(db, integrations.PAYSTACK_CODE, tenant_id=tenant_id)
    secret = saas_services.provider_secrets(credential)
    if not integrations.verify_paystack_signature(raw_payload, signature, str(secret.get("secret_key") or "")):
        raise PermissionError("Invalid Paystack webhook signature")

    return saas_queue.enqueue_job(
        db,
        job_type="PAYSTACK_WEBHOOK",
        queue_name="billing",
        tenant_id=tenant_id,
        payload={
            "event_type": event_type,
            "credential_id": credential.id,
            "invoice_id": invoice_id,
            "reference": reference,
            "data_minimized": True,
        },
        idempotency_key=f"{event_type}:{reference}",
        correlation_id=reference,
        max_attempts=6,
        priority=5,
    )


def install_payment_data_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    commercial_services.record_paystack_webhook = _safe_paystack_webhook
    _INSTALLED = True
