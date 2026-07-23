from __future__ import annotations

import json
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import saas_models as models
from . import saas_providers, saas_queue, saas_secrets


ACTIVE_CREDENTIAL_STATES = {"CONFIGURED", "HEALTHY", "UNHEALTHY"}


def _stripe_object(payload: dict[str, Any]) -> dict[str, Any]:
    value = ((payload.get("data") or {}).get("object") or {})
    return value if isinstance(value, dict) else {}


def _metadata(obj: dict[str, Any]) -> dict[str, Any]:
    value = obj.get("metadata") or {}
    result = dict(value) if isinstance(value, dict) else {}
    subscription_details = obj.get("subscription_details") or {}
    nested = subscription_details.get("metadata") if isinstance(subscription_details, dict) else None
    if isinstance(nested, dict):
        result = {**nested, **result}
    return result


def _resolved_tenant_hints(
    db: Session,
    *,
    payload: dict[str, Any],
) -> set[str]:
    obj = _stripe_object(payload)
    metadata = _metadata(obj)
    tenant_hints = {
        str(value).strip()
        for value in (metadata.get("tenant_id"), obj.get("client_reference_id"))
        if str(value or "").strip()
    }
    external_refs = {
        str(value).strip()
        for value in (obj.get("customer"), obj.get("subscription"))
        if str(value or "").strip()
    }
    if external_refs:
        rows = (
            db.query(models.SaaSBillingAccount.tenant_id)
            .filter(
                models.SaaSBillingAccount.provider == "stripe",
                or_(
                    models.SaaSBillingAccount.external_customer_ref.in_(external_refs),
                    models.SaaSBillingAccount.external_subscription_ref.in_(external_refs),
                ),
            )
            .limit(50)
            .all()
        )
        tenant_hints.update(str(row[0]) for row in rows if row and row[0])
    return tenant_hints


def _credential_candidates(
    db: Session,
    *,
    payload: dict[str, Any],
) -> list[models.SaaSProviderCredential]:
    """Return only credentials allowed to authenticate this Stripe event.

    Tenant hints order candidate lookup but are not trusted until signature
    verification succeeds. When a tenant-specific Stripe credential exists, it
    is authoritative: platform or other-tenant secrets must not authenticate
    that tenant's endpoint. Platform fallback is used only when no scoped row
    exists for any resolved tenant hint.
    """

    tenant_hints = _resolved_tenant_hints(db, payload=payload)
    if tenant_hints:
        scoped_rows = (
            db.query(models.SaaSProviderCredential)
            .filter(
                models.SaaSProviderCredential.provider == "stripe",
                models.SaaSProviderCredential.tenant_id.in_(tenant_hints),
            )
            .order_by(models.SaaSProviderCredential.updated_at.desc())
            .limit(50)
            .all()
        )
        if scoped_rows:
            # A disabled or incomplete scoped row deliberately blocks platform
            # fallback. The tenant must repair or remove that override.
            return [
                row
                for row in scoped_rows
                if row.encrypted_secret and str(row.status).upper() in ACTIVE_CREDENTIAL_STATES
            ]

    rows = (
        db.query(models.SaaSProviderCredential)
        .filter(
            models.SaaSProviderCredential.provider == "stripe",
            models.SaaSProviderCredential.encrypted_secret.isnot(None),
            models.SaaSProviderCredential.status.in_(sorted(ACTIVE_CREDENTIAL_STATES)),
        )
        .order_by(models.SaaSProviderCredential.updated_at.desc())
        .limit(5000)
        .all()
    )
    platform = [row for row in rows if row.tenant_id is None]
    fallback = [row for row in rows if row.tenant_id is not None]
    return [*platform, *fallback]


def record_stripe_webhook(
    db: Session,
    *,
    raw_payload: bytes,
    signature: str,
) -> models.SaaSJob:
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Stripe webhook payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Stripe webhook payload must be an object")

    matched: models.SaaSProviderCredential | None = None
    for credential in _credential_candidates(db, payload=payload):
        secret = saas_secrets.decrypt_secret(credential.encrypted_secret)
        webhook_secret = str(secret.get("webhook_secret") or "").strip()
        if webhook_secret and saas_providers.verify_stripe_signature(
            raw_payload,
            signature,
            webhook_secret,
        ):
            matched = credential
            break
    if matched is None:
        raise PermissionError("Invalid Stripe webhook signature")

    tenant_hints = _resolved_tenant_hints(db, payload=payload)
    matched_tenant = str(matched.tenant_id or "").strip()
    if matched_tenant:
        if tenant_hints and matched_tenant not in tenant_hints:
            raise PermissionError("Stripe webhook tenant does not match the verified endpoint secret")
        verified_tenant_id = matched_tenant
    else:
        if len(tenant_hints) > 1:
            raise PermissionError("Stripe webhook tenant resolution is ambiguous")
        verified_tenant_id = next(iter(tenant_hints), "")

    external_id = str(payload.get("id") or "").strip()
    if not external_id:
        raise ValueError("Stripe event id is required")
    event = (
        db.query(account_models.WebhookEvent)
        .filter(
            account_models.WebhookEvent.provider == account_models.PaymentProvider.STRIPE,
            account_models.WebhookEvent.external_event_id == external_id,
        )
        .first()
    )
    if not event:
        event = account_models.WebhookEvent(
            provider=account_models.PaymentProvider.STRIPE,
            external_event_id=external_id,
            signature=signature[:256],
            event_type=str(payload.get("type") or "")[:128],
            payload=raw_payload.decode("utf-8"),
            status=account_models.WebhookStatus.RECEIVED,
        )
        db.add(event)
        db.flush()
    return saas_queue.enqueue_job(
        db,
        job_type="STRIPE_WEBHOOK",
        queue_name="billing",
        tenant_id=verified_tenant_id or None,
        payload={
            "webhook_event_id": event.id,
            "verified_credential_id": matched.id,
            "verified_tenant_id": verified_tenant_id or None,
        },
        idempotency_key=external_id,
        correlation_id=external_id,
        max_attempts=8,
        priority=5,
    )
