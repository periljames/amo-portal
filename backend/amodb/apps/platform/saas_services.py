from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import services as account_services

from . import models as platform_models
from . import saas_models as models
from . import saas_providers, saas_queue, saas_secrets


MODULE_CODE_MAX = 64
MODULE_STATUSES = {"ENABLED", "DISABLED", "TRIAL", "SUSPENDED"}
BILLING_TERMS = {"MONTHLY", "ANNUAL", "BI_ANNUAL", "ONE_TIME"}
SUPPORT_STATUSES = {"OPEN", "PENDING", "IN_PROGRESS", "RESOLVED", "CLOSED"}
SUPPORT_PRIORITIES = {"LOW", "NORMAL", "HIGH", "URGENT", "CRITICAL"}
OPERATIONAL_PROVIDER_STATUSES = frozenset({"CONFIGURED", "HEALTHY"})
ACTIVE_AI_JOB_STATUSES = frozenset({"PENDING", "RUNNING", "RETRY"})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_operational_provider(credential: Any, *, label: str) -> None:
    status = str(getattr(credential, "status", "") or "").strip().upper()
    if credential is None or status not in OPERATIONAL_PROVIDER_STATUSES:
        raise ValueError(f"{label} provider is disabled or not operational")


def _ticket_ai_jobs(db: Session, *, ticket_id: str, tenant_id: str | None) -> list[models.SaaSJob]:
    scope = tenant_id or "__platform__"
    rows = (
        db.query(models.SaaSJob)
        .filter(
            models.SaaSJob.job_type == "AI_SUPPORT_REPLY",
            models.SaaSJob.tenant_scope == scope,
        )
        .order_by(models.SaaSJob.created_at.asc(), models.SaaSJob.id.asc())
        .all()
    )
    return [row for row in rows if str((row.payload_json or {}).get("ticket_id") or "") == ticket_id]


def normalize_module_code(value: str) -> str:
    code = (value or "").strip().lower().replace("-", "_")
    if not code or len(code) > MODULE_CODE_MAX or not all(ch.isalnum() or ch == "_" for ch in code):
        raise ValueError("module_code must contain only letters, numbers and underscores")
    return code


def provider_scope(tenant_id: str | None) -> str:
    return tenant_id or "__platform__"


def provider_payload(row: models.SaaSProviderCredential) -> dict[str, Any]:
    definition = saas_providers.PROVIDERS.get(row.provider)
    return {
        "id": row.id,
        "provider": row.provider,
        "display_name": row.display_name,
        "category": row.category,
        "tenant_id": row.tenant_id,
        "scope": "TENANT" if row.tenant_id else "PLATFORM",
        "status": row.status,
        "config": saas_secrets.redact_mapping(row.config_json or {}),
        "has_secret": bool(row.encrypted_secret),
        "secret_fingerprint": row.secret_fingerprint,
        "secret_fields": list(definition.secret_fields) if definition else [],
        "config_fields": list(definition.config_fields) if definition else [],
        "last_checked_at": row.last_checked_at,
        "last_latency_ms": row.last_latency_ms,
        "last_health_detail": row.last_health_detail,
        "configured_at": row.configured_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def get_provider_credential(
    db: Session,
    *,
    provider: str,
    tenant_id: str | None = None,
    allow_platform_fallback: bool = True,
) -> models.SaaSProviderCredential | None:
    normalized = (provider or "").strip().lower()
    if tenant_id:
        row = (
            db.query(models.SaaSProviderCredential)
            .filter(
                models.SaaSProviderCredential.provider == normalized,
                models.SaaSProviderCredential.tenant_id == tenant_id,
            )
            .first()
        )
        if row or not allow_platform_fallback:
            return row
    return (
        db.query(models.SaaSProviderCredential)
        .filter(
            models.SaaSProviderCredential.provider == normalized,
            models.SaaSProviderCredential.tenant_id.is_(None),
        )
        .first()
    )


def provider_secrets(row: models.SaaSProviderCredential) -> dict[str, Any]:
    return saas_secrets.decrypt_secret(row.encrypted_secret)


def list_provider_credentials(db: Session, *, tenant_id: str | None = None) -> list[dict[str, Any]]:
    query = db.query(models.SaaSProviderCredential)
    if tenant_id:
        query = query.filter(
            or_(
                models.SaaSProviderCredential.tenant_id == tenant_id,
                models.SaaSProviderCredential.tenant_id.is_(None),
            )
        )
    else:
        query = query.filter(models.SaaSProviderCredential.tenant_id.is_(None))
    rows = query.order_by(models.SaaSProviderCredential.category, models.SaaSProviderCredential.provider).all()
    by_provider = {row.provider: row for row in rows if row.tenant_id == tenant_id}
    for row in rows:
        by_provider.setdefault(row.provider, row)
    configured = [provider_payload(row) for row in by_provider.values()]
    configured_codes = {row["provider"] for row in configured}
    for definition in saas_providers.provider_catalog():
        if definition["provider"] not in configured_codes:
            configured.append(
                {
                    **definition,
                    "id": None,
                    "tenant_id": tenant_id,
                    "scope": "TENANT" if tenant_id else "PLATFORM",
                    "status": "NOT_CONFIGURED",
                    "config": {},
                    "has_secret": False,
                    "secret_fingerprint": None,
                    "last_checked_at": None,
                    "last_latency_ms": None,
                    "last_health_detail": None,
                    "configured_at": None,
                    "created_at": None,
                    "updated_at": None,
                }
            )
    return sorted(configured, key=lambda item: (str(item.get("category")), str(item.get("display_name"))))


def upsert_provider_credential(
    db: Session,
    *,
    provider: str,
    payload: dict[str, Any],
    actor_user_id: str,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    normalized = (provider or "").strip().lower()
    definition = saas_providers.PROVIDERS.get(normalized)
    if not definition:
        raise ValueError("Unknown integration provider")
    if tenant_id and not db.get(account_models.AMO, tenant_id):
        raise ValueError("Tenant not found")

    row = get_provider_credential(
        db,
        provider=normalized,
        tenant_id=tenant_id,
        allow_platform_fallback=False,
    )
    if not row:
        row = models.SaaSProviderCredential(
            provider=normalized,
            display_name=definition.display_name,
            category=definition.category,
            tenant_id=tenant_id,
            created_by=actor_user_id,
        )
        db.add(row)

    config = payload.get("config") or {}
    if not isinstance(config, dict):
        raise ValueError("config must be an object")
    unexpected_config = set(config) - set(definition.config_fields)
    if unexpected_config:
        raise ValueError(f"Unsupported config field(s): {', '.join(sorted(unexpected_config))}")
    row.config_json = config

    if "secret" in payload:
        secret = payload.get("secret") or {}
        if not isinstance(secret, dict):
            raise ValueError("secret must be an object")
        unexpected_secret = set(secret) - set(definition.secret_fields)
        if unexpected_secret:
            raise ValueError(f"Unsupported secret field(s): {', '.join(sorted(unexpected_secret))}")
        if secret:
            row.encrypted_secret, row.secret_fingerprint = saas_secrets.encrypt_secret(secret)
        elif payload.get("clear_secret"):
            row.encrypted_secret = None
            row.secret_fingerprint = None

    enabled = bool(payload.get("enabled", True))
    row.status = "CONFIGURED" if enabled and (row.config_json or row.encrypted_secret) else "DISABLED"
    row.configured_at = utcnow() if row.status == "CONFIGURED" else row.configured_at
    row.updated_by = actor_user_id
    db.flush()
    db.add(
        platform_models.PlatformAuditLog(
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            action="saas.provider.updated",
            module="platform",
            entity_type="saas_provider_credential",
            entity_id=row.id,
            reason=str(payload.get("reason") or "Provider configuration updated")[:1000],
            details_json={
                "provider": normalized,
                "scope": provider_scope(tenant_id),
                "config": saas_secrets.redact_mapping(config),
                "has_secret": bool(row.encrypted_secret),
            },
        )
    )
    db.commit()
    db.refresh(row)
    return provider_payload(row)


def enqueue_provider_health(
    db: Session,
    *,
    provider: str,
    tenant_id: str | None,
    actor_user_id: str,
) -> models.SaaSJob:
    normalized = (provider or "").strip().lower()
    exact_row = get_provider_credential(
        db,
        provider=normalized,
        tenant_id=tenant_id,
        allow_platform_fallback=False,
    ) if tenant_id else get_provider_credential(db, provider=normalized, tenant_id=None)
    row = exact_row or get_provider_credential(db, provider=normalized, tenant_id=tenant_id)
    if not row:
        raise ValueError("Provider is not configured")
    status = str(row.status or "").strip().upper()
    if status == "DISABLED":
        raise ValueError("Disabled providers cannot be health checked")
    if status not in {"CONFIGURED", "HEALTHY", "UNHEALTHY"}:
        raise ValueError("Provider is not configured for a health check")
    inherited_platform_credential = bool(tenant_id and row.tenant_id is None)
    return saas_queue.enqueue_job(
        db,
        job_type="PROVIDER_HEALTH_CHECK",
        queue_name="integrations",
        tenant_id=tenant_id,
        payload={
            "provider": row.provider,
            "credential_id": row.id,
            "mutate_credential_status": not inherited_platform_credential,
            "credential_scope": provider_scope(row.tenant_id),
        },
        idempotency_key=f"health:{row.id}:{utcnow().strftime('%Y%m%d%H%M')}",
        correlation_id=str(uuid.uuid4()),
        created_by=actor_user_id,
        max_attempts=3,
    )


def module_price_payload(row: models.SaaSModulePrice) -> dict[str, Any]:
    return {
        "id": row.id,
        "module_code": row.module_code,
        "plan_code": row.plan_code,
        "billing_term": row.billing_term,
        "amount_cents": row.amount_cents,
        "currency": row.currency,
        "trial_days": row.trial_days,
        "tax_rate_bps": row.tax_rate_bps,
        "external_price_ref": row.external_price_ref,
        "is_active": row.is_active,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_module_prices(
    db: Session,
    *,
    module_code: str | None = None,
    include_inactive: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    query = db.query(models.SaaSModulePrice)
    if module_code:
        query = query.filter(models.SaaSModulePrice.module_code == normalize_module_code(module_code))
    if not include_inactive:
        query = query.filter(models.SaaSModulePrice.is_active.is_(True))
    total = query.count()
    rows = (
        query.order_by(
            models.SaaSModulePrice.module_code,
            models.SaaSModulePrice.plan_code,
            models.SaaSModulePrice.billing_term,
            models.SaaSModulePrice.currency,
        )
        .offset(max(0, offset))
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return {"items": [module_price_payload(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def upsert_module_price(
    db: Session,
    *,
    payload: dict[str, Any],
    actor_user_id: str,
    price_id: str | None = None,
) -> dict[str, Any]:
    row = db.get(models.SaaSModulePrice, price_id) if price_id else None
    if price_id and not row:
        raise ValueError("Module price not found")
    module_code = normalize_module_code(str(payload.get("module_code") or getattr(row, "module_code", "")))
    plan_code = str(payload.get("plan_code") or getattr(row, "plan_code", "STANDARD")).strip().upper()
    term = str(payload.get("billing_term") or getattr(row, "billing_term", "MONTHLY")).strip().upper()
    if term not in BILLING_TERMS:
        raise ValueError("Unsupported billing term")
    currency = str(payload.get("currency") or getattr(row, "currency", "USD")).strip().upper()
    amount_cents = int(payload.get("amount_cents", getattr(row, "amount_cents", -1)))
    tax_rate_bps = int(payload.get("tax_rate_bps", getattr(row, "tax_rate_bps", 0)))
    trial_days = int(payload.get("trial_days", getattr(row, "trial_days", 0)))
    if amount_cents < 0:
        raise ValueError("amount_cents cannot be negative")
    if not 0 <= tax_rate_bps <= 10000:
        raise ValueError("tax_rate_bps must be between 0 and 10000")
    if not 0 <= trial_days <= 365:
        raise ValueError("trial_days must be between 0 and 365")

    duplicate = (
        db.query(models.SaaSModulePrice)
        .filter(
            models.SaaSModulePrice.module_code == module_code,
            models.SaaSModulePrice.plan_code == plan_code,
            models.SaaSModulePrice.billing_term == term,
            models.SaaSModulePrice.currency == currency,
        )
    )
    if row:
        duplicate = duplicate.filter(models.SaaSModulePrice.id != row.id)
    if duplicate.first():
        raise ValueError("A module price already exists for this module, plan, term and currency")
    if not row:
        row = models.SaaSModulePrice(created_by=actor_user_id)
        db.add(row)
    row.module_code = module_code
    row.plan_code = plan_code
    row.billing_term = term
    row.currency = currency
    row.amount_cents = amount_cents
    row.tax_rate_bps = tax_rate_bps
    row.trial_days = trial_days
    if "external_price_ref" in payload:
        row.external_price_ref = str(payload.get("external_price_ref") or "").strip() or None
    elif not price_id:
        row.external_price_ref = None
    if "is_active" in payload:
        row.is_active = bool(payload.get("is_active"))
    elif not price_id:
        row.is_active = True
    row.updated_by = actor_user_id
    db.flush()
    db.add(
        platform_models.PlatformAuditLog(
            actor_user_id=actor_user_id,
            action="saas.module_price.updated",
            module="billing",
            entity_type="saas_module_price",
            entity_id=row.id,
            reason=str(payload.get("reason") or "Module price updated")[:1000],
            details_json=module_price_payload(row),
        )
    )
    db.commit()
    db.refresh(row)
    return module_price_payload(row)


def tenant_module_payload(row: account_models.ModuleSubscription) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if row.metadata_json:
        try:
            loaded = json.loads(row.metadata_json)
            if isinstance(loaded, dict):
                metadata = loaded
        except Exception:
            metadata = {"raw": row.metadata_json}
    return {
        "id": row.id,
        "amo_id": row.amo_id,
        "module_code": row.module_code,
        "status": getattr(row.status, "value", str(row.status)),
        "effective_from": row.effective_from,
        "effective_to": row.effective_to,
        "plan_code": row.plan_code,
        "metadata": metadata,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_tenant_modules(db: Session, *, tenant_id: str) -> list[dict[str, Any]]:
    if not db.get(account_models.AMO, tenant_id):
        raise ValueError("Tenant not found")
    rows = (
        db.query(account_models.ModuleSubscription)
        .filter(account_models.ModuleSubscription.amo_id == tenant_id)
        .order_by(account_models.ModuleSubscription.module_code.asc())
        .all()
    )
    return [tenant_module_payload(row) for row in rows]


def update_tenant_modules(
    db: Session,
    *,
    tenant_id: str,
    changes: list[dict[str, Any]],
    actor_user_id: str,
    reason: str,
) -> list[dict[str, Any]]:
    if not db.get(account_models.AMO, tenant_id):
        raise ValueError("Tenant not found")
    if not reason.strip():
        raise ValueError("A reason is required")
    now = utcnow()
    changed: list[account_models.ModuleSubscription] = []
    for item in changes:
        module_code = normalize_module_code(str(item.get("module_code") or ""))
        status_value = str(item.get("status") or "DISABLED").strip().upper()
        if status_value not in MODULE_STATUSES:
            raise ValueError(f"Unsupported module status for {module_code}")
        row = (
            db.query(account_models.ModuleSubscription)
            .filter(
                account_models.ModuleSubscription.amo_id == tenant_id,
                account_models.ModuleSubscription.module_code == module_code,
            )
            .first()
        )
        if not row:
            row = account_models.ModuleSubscription(amo_id=tenant_id, module_code=module_code)
            db.add(row)
        row.status = account_models.ModuleSubscriptionStatus(status_value)
        row.plan_code = str(item.get("plan_code") or "").strip().upper() or None
        row.effective_from = item.get("effective_from") or (now if status_value in {"ENABLED", "TRIAL"} else row.effective_from)
        row.effective_to = item.get("effective_to")
        metadata = item.get("metadata") or {}
        row.metadata_json = json.dumps(metadata, separators=(",", ":")) if metadata else None
        changed.append(row)
    db.flush()
    db.add(
        platform_models.PlatformAuditLog(
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            action="saas.tenant_modules.updated",
            module="billing",
            entity_type="module_subscription",
            entity_id=tenant_id,
            reason=reason[:1000],
            details_json={"changes": [tenant_module_payload(row) for row in changed]},
        )
    )
    db.commit()
    return list_tenant_modules(db, tenant_id=tenant_id)


def create_manual_invoice(
    db: Session,
    *,
    tenant_id: str,
    module_price_id: str,
    quantity: int,
    due_days: int,
    actor_user_id: str,
    reason: str,
    idempotency_key: str,
) -> dict[str, Any]:
    tenant = db.get(account_models.AMO, tenant_id)
    price = db.get(models.SaaSModulePrice, module_price_id)
    if not tenant:
        raise ValueError("Tenant not found")
    if not price or not price.is_active:
        raise ValueError("Active module price not found")
    quantity = max(1, min(int(quantity), 10000))
    due_days = max(0, min(int(due_days), 365))
    if not idempotency_key.strip():
        raise ValueError("idempotency_key is required")
    existing = (
        db.query(account_models.BillingInvoice)
        .filter(
            account_models.BillingInvoice.amo_id == tenant_id,
            account_models.BillingInvoice.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing:
        return invoice_payload(existing)

    subtotal = int(price.amount_cents) * quantity
    tax_amount = round(subtotal * int(price.tax_rate_bps or 0) / 10000)
    total = subtotal + tax_amount
    now = utcnow()
    ledger = account_models.LedgerEntry(
        amo_id=tenant_id,
        amount_cents=total,
        currency=price.currency,
        entry_type=account_models.LedgerEntryType.CHARGE,
        description=f"MANUAL_INVOICE:{price.module_code}:{price.plan_code}:{quantity}",
        idempotency_key=idempotency_key,
        recorded_at=now,
    )
    db.add(ledger)
    db.flush()
    description = json.dumps(
        {
            "module_code": price.module_code,
            "plan_code": price.plan_code,
            "billing_term": price.billing_term,
            "quantity": quantity,
            "unit_amount_cents": price.amount_cents,
            "subtotal_cents": subtotal,
            "tax_rate_bps": price.tax_rate_bps,
            "tax_amount_cents": tax_amount,
            "reason": reason,
        },
        separators=(",", ":"),
    )
    invoice = account_models.BillingInvoice(
        amo_id=tenant_id,
        ledger_entry_id=ledger.id,
        amount_cents=total,
        currency=price.currency,
        status=account_models.InvoiceStatus.PENDING,
        description=description,
        idempotency_key=idempotency_key,
        issued_at=now,
        due_at=now + timedelta(days=due_days),
    )
    db.add(invoice)
    db.flush()
    db.add(
        platform_models.PlatformAuditLog(
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            action="saas.invoice.created",
            module="billing",
            entity_type="billing_invoice",
            entity_id=invoice.id,
            reason=reason[:1000],
            details_json={"amount_cents": total, "currency": price.currency, "module_code": price.module_code},
        )
    )
    db.commit()
    db.refresh(invoice)
    return invoice_payload(invoice)


def invoice_payload(row: account_models.BillingInvoice) -> dict[str, Any]:
    fiscal = getattr(row, "saas_fiscalization", None)
    return {
        "id": row.id,
        "invoice_number": account_services.format_invoice_number(row),
        "amo_id": row.amo_id,
        "license_id": row.license_id,
        "amount_cents": row.amount_cents,
        "currency": row.currency,
        "status": getattr(row.status, "value", str(row.status)),
        "description": row.description,
        "issued_at": row.issued_at,
        "due_at": row.due_at,
        "paid_at": row.paid_at,
        "created_at": row.created_at,
        "fiscalization": fiscalization_payload(fiscal) if fiscal else None,
    }


def enqueue_checkout(
    db: Session,
    *,
    tenant_id: str,
    module_price_id: str,
    actor_user_id: str,
    idempotency_key: str,
) -> models.SaaSJob:
    normalized_key = idempotency_key.strip()
    if not normalized_key:
        raise ValueError("idempotency_key is required")
    tenant = (
        db.query(account_models.AMO)
        .filter(account_models.AMO.id == tenant_id)
        .with_for_update()
        .first()
    )
    if not tenant:
        raise ValueError("Tenant or active module price not found")
    existing_job = (
        db.query(models.SaaSJob)
        .filter(
            models.SaaSJob.job_type == "STRIPE_CREATE_CHECKOUT_SESSION",
            models.SaaSJob.tenant_scope == tenant_id,
            models.SaaSJob.idempotency_key == normalized_key,
        )
        .first()
    )
    if existing_job is not None:
        existing_payload = getattr(existing_job, "payload_json", None) or {}
        existing_price_id = str(existing_payload.get("module_price_id") or "").strip()
        if existing_price_id and existing_price_id != module_price_id:
            raise ValueError("idempotency_key is already used for a different checkout request")
        return existing_job
    price = db.get(models.SaaSModulePrice, module_price_id)
    if not price or not price.is_active:
        raise ValueError("Tenant or active module price not found")
    pending_account = (
        db.query(models.SaaSBillingAccount)
        .filter(
            models.SaaSBillingAccount.tenant_id == tenant_id,
            models.SaaSBillingAccount.provider == "stripe",
            models.SaaSBillingAccount.status == "CHECKOUT_PENDING",
        )
        .first()
    )
    if pending_account is not None:
        raise ValueError("Another Stripe checkout is already pending for this tenant")
    active_job = (
        db.query(models.SaaSJob)
        .filter(
            models.SaaSJob.job_type == "STRIPE_CREATE_CHECKOUT_SESSION",
            models.SaaSJob.tenant_scope == tenant_id,
            models.SaaSJob.status.in_({"PENDING", "RETRY", "RUNNING"}),
        )
        .order_by(models.SaaSJob.created_at.desc())
        .first()
    )
    if active_job is not None:
        raise ValueError("Another Stripe checkout request is already queued for this tenant")
    if not price.external_price_ref:
        raise ValueError("This module price has no external Stripe price reference")
    credential = get_provider_credential(db, provider="stripe", tenant_id=tenant_id)
    if not credential or credential.status not in {"CONFIGURED", "HEALTHY"}:
        raise ValueError("Stripe is not configured for this tenant or platform")
    return saas_queue.enqueue_job(
        db,
        job_type="STRIPE_CREATE_CHECKOUT_SESSION",
        queue_name="billing",
        tenant_id=tenant_id,
        payload={
            "provider_credential_id": credential.id,
            "module_price_id": price.id,
            "module_code": price.module_code,
            "external_price_ref": price.external_price_ref,
            "tenant_email": tenant.contact_email,
        },
        idempotency_key=normalized_key,
        correlation_id=str(uuid.uuid4()),
        created_by=actor_user_id,
        max_attempts=3,
        priority=20,
    )

def record_stripe_webhook(
    db: Session,
    *,
    raw_payload: bytes,
    signature: str,
) -> models.SaaSJob:
    credential = get_provider_credential(db, provider="stripe")
    if not credential:
        raise ValueError("Stripe is not configured")
    secret = provider_secrets(credential)
    webhook_secret = str(secret.get("webhook_secret") or "")
    if not saas_providers.verify_stripe_signature(raw_payload, signature, webhook_secret):
        raise PermissionError("Invalid Stripe webhook signature")
    payload = json.loads(raw_payload.decode("utf-8"))
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
        payload={"webhook_event_id": event.id},
        idempotency_key=external_id,
        correlation_id=external_id,
        max_attempts=8,
        priority=5,
    )


def fiscalization_payload(row: models.SaaSInvoiceFiscalization | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row.id,
        "invoice_id": row.invoice_id,
        "provider": row.provider,
        "status": row.status,
        "fiscal_document_number": row.fiscal_document_number,
        "control_unit_serial": row.control_unit_serial,
        "receipt_signature": row.receipt_signature,
        "last_error": row.last_error,
        "submitted_at": row.submitted_at,
        "fiscalized_at": row.fiscalized_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def enqueue_fiscalization(
    db: Session,
    *,
    invoice_id: str,
    provider: str,
    actor_user_id: str,
) -> models.SaaSJob:
    invoice = db.get(account_models.BillingInvoice, invoice_id)
    provider_code = provider.strip().lower()
    if not invoice:
        raise ValueError("Invoice not found")
    if provider_code not in {"etims_oscu", "etims_vscu"}:
        raise ValueError("provider must be etims_oscu or etims_vscu")
    credential = get_provider_credential(db, provider=provider_code, tenant_id=invoice.amo_id)
    if not credential:
        raise ValueError("eTIMS provider is not configured")
    require_operational_provider(credential, label="eTIMS")
    config = credential.config_json or {}
    if not bool(config.get("certified")):
        raise ValueError("Fiscalization is blocked until a KRA-tested/certified eTIMS adapter is configured")
    row = (
        db.query(models.SaaSInvoiceFiscalization)
        .filter(models.SaaSInvoiceFiscalization.invoice_id == invoice_id)
        .first()
    )
    if not row:
        row = models.SaaSInvoiceFiscalization(invoice_id=invoice_id, provider=provider_code.upper())
        db.add(row)
        db.flush()
    row.status = "QUEUED"
    return saas_queue.enqueue_job(
        db,
        job_type="ETIMS_FISCALIZE_INVOICE",
        queue_name="fiscalization",
        tenant_id=invoice.amo_id,
        payload={"fiscalization_id": row.id, "credential_id": credential.id},
        idempotency_key=f"invoice:{invoice_id}",
        correlation_id=str(uuid.uuid4()),
        created_by=actor_user_id,
        max_attempts=5,
        priority=10,
    )


def support_ticket_payload(db: Session, row: platform_models.PlatformSupportTicket, *, include_messages: bool = False) -> dict[str, Any]:
    detail = db.get(models.SaaSSupportTicketDetail, row.id)
    payload = {
        "id": row.id,
        "external_id": row.external_id,
        "provider": row.provider,
        "tenant_id": row.tenant_id,
        "title": row.title,
        "status": row.status,
        "priority": row.priority,
        "category": detail.category if detail else "GENERAL",
        "description": detail.description if detail else "",
        "requester_user_id": detail.requester_user_id if detail else None,
        "requester_email": detail.requester_email if detail else None,
        "assignee_user_id": detail.assignee_user_id if detail else None,
        "sla_due_at": detail.sla_due_at if detail else None,
        "resolved_at": detail.resolved_at if detail else None,
        "resolution": detail.resolution if detail else None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if include_messages:
        messages = (
            db.query(models.SaaSSupportTicketMessage)
            .filter(models.SaaSSupportTicketMessage.ticket_id == row.id)
            .order_by(models.SaaSSupportTicketMessage.created_at.asc())
            .all()
        )
        payload["messages"] = [
            {
                "id": message.id,
                "author_user_id": message.author_user_id,
                "author_type": message.author_type,
                "visibility": message.visibility,
                "body": message.body,
                "created_at": message.created_at,
            }
            for message in messages
        ]
    return payload


def create_support_ticket(
    db: Session,
    *,
    tenant_id: str | None,
    title: str,
    description: str,
    priority: str,
    category: str,
    requester_user_id: str | None,
    requester_email: str | None,
) -> dict[str, Any]:
    if tenant_id and not db.get(account_models.AMO, tenant_id):
        raise ValueError("Tenant not found")
    if not title.strip() or not description.strip():
        raise ValueError("Ticket title and description are required")
    normalized_priority = priority.strip().upper() or "NORMAL"
    if normalized_priority not in SUPPORT_PRIORITIES:
        raise ValueError("Unsupported support priority")
    now = utcnow()
    sla_hours = {"LOW": 72, "NORMAL": 24, "HIGH": 8, "URGENT": 2, "CRITICAL": 1}[normalized_priority]
    row = platform_models.PlatformSupportTicket(
        external_id=f"SUP-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}",
        provider="INTERNAL",
        tenant_id=tenant_id,
        title=title.strip()[:255],
        status="OPEN",
        priority=normalized_priority,
        metadata_json={},
    )
    db.add(row)
    db.flush()
    detail = models.SaaSSupportTicketDetail(
        ticket_id=row.id,
        requester_user_id=requester_user_id,
        requester_email=requester_email,
        category=(category or "GENERAL").strip().upper()[:64],
        description=description.strip(),
        sla_due_at=now + timedelta(hours=sla_hours),
    )
    db.add(detail)
    db.add(
        models.SaaSSupportTicketMessage(
            ticket_id=row.id,
            author_user_id=requester_user_id,
            author_type="USER",
            visibility="PUBLIC",
            body=description.strip(),
        )
    )
    db.commit()
    return support_ticket_payload(db, row, include_messages=True)


def list_support_tickets(
    db: Session,
    *,
    tenant_id: str | None,
    status: str | None,
    q: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    query = db.query(platform_models.PlatformSupportTicket)
    if tenant_id:
        query = query.filter(platform_models.PlatformSupportTicket.tenant_id == tenant_id)
    if status:
        query = query.filter(platform_models.PlatformSupportTicket.status == status.strip().upper())
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                platform_models.PlatformSupportTicket.title.ilike(like),
                platform_models.PlatformSupportTicket.external_id.ilike(like),
            )
        )
    total = query.count()
    rows = (
        query.order_by(platform_models.PlatformSupportTicket.updated_at.desc(), platform_models.PlatformSupportTicket.id.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return {
        "items": [support_ticket_payload(db, row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def update_support_ticket(
    db: Session,
    *,
    ticket_id: str,
    payload: dict[str, Any],
    actor_user_id: str,
) -> dict[str, Any]:
    row = db.get(platform_models.PlatformSupportTicket, ticket_id)
    detail = db.get(models.SaaSSupportTicketDetail, ticket_id)
    if not row or not detail:
        raise ValueError("Support ticket not found")
    if "status" in payload:
        status_value = str(payload["status"]).strip().upper()
        if status_value not in SUPPORT_STATUSES:
            raise ValueError("Unsupported support status")
        row.status = status_value
        if status_value in {"RESOLVED", "CLOSED"}:
            detail.resolved_at = detail.resolved_at or utcnow()
    if "priority" in payload:
        priority = str(payload["priority"]).strip().upper()
        if priority not in SUPPORT_PRIORITIES:
            raise ValueError("Unsupported support priority")
        row.priority = priority
    if "assignee_user_id" in payload:
        detail.assignee_user_id = payload.get("assignee_user_id") or None
    if "resolution" in payload:
        detail.resolution = str(payload.get("resolution") or "").strip() or None
    db.add(
        platform_models.PlatformAuditLog(
            actor_user_id=actor_user_id,
            tenant_id=row.tenant_id,
            action="saas.support_ticket.updated",
            module="support",
            entity_type="platform_support_ticket",
            entity_id=row.id,
            reason=str(payload.get("reason") or "Support ticket updated")[:1000],
            details_json={"status": row.status, "priority": row.priority, "assignee_user_id": detail.assignee_user_id},
        )
    )
    db.commit()
    return support_ticket_payload(db, row, include_messages=True)


def add_support_message(
    db: Session,
    *,
    ticket_id: str,
    author_user_id: str | None,
    author_type: str,
    body: str,
    visibility: str = "PUBLIC",
) -> dict[str, Any]:
    row = db.get(platform_models.PlatformSupportTicket, ticket_id)
    if not row:
        raise ValueError("Support ticket not found")
    if not body.strip():
        raise ValueError("Message body is required")
    message = models.SaaSSupportTicketMessage(
        ticket_id=ticket_id,
        author_user_id=author_user_id,
        author_type=author_type.strip().upper()[:32],
        visibility=visibility.strip().upper()[:32],
        body=body.strip(),
    )
    db.add(message)
    row.updated_at = utcnow()
    db.commit()
    db.refresh(message)
    return {
        "id": message.id,
        "ticket_id": ticket_id,
        "author_user_id": message.author_user_id,
        "author_type": message.author_type,
        "visibility": message.visibility,
        "body": message.body,
        "created_at": message.created_at,
    }


def enqueue_ai_support_reply(
    db: Session,
    *,
    ticket_id: str,
    actor_user_id: str,
) -> models.SaaSJob:
    ticket = db.get(platform_models.PlatformSupportTicket, ticket_id)
    if not ticket:
        raise ValueError("Support ticket not found")
    credential = get_provider_credential(db, provider="openai", tenant_id=ticket.tenant_id)
    if not credential:
        raise ValueError("OpenAI provider is not configured")
    require_operational_provider(credential, label="OpenAI")

    prior_jobs = _ticket_ai_jobs(db, ticket_id=ticket_id, tenant_id=ticket.tenant_id)
    for job in reversed(prior_jobs):
        if str(job.status or "").strip().upper() in ACTIVE_AI_JOB_STATUSES:
            return job

    request_sequence = len(prior_jobs) + 1
    request_version = int(ticket.updated_at.timestamp() * 1_000_000) if ticket.updated_at else 0
    action_key = f"ticket:{ticket_id}:ai-reply:{request_version}:{request_sequence}"
    return saas_queue.enqueue_job(
        db,
        job_type="AI_SUPPORT_REPLY",
        queue_name="ai",
        tenant_id=ticket.tenant_id,
        payload={
            "ticket_id": ticket_id,
            "credential_id": credential.id,
            "request_version": request_version,
            "request_sequence": request_sequence,
        },
        idempotency_key=action_key,
        correlation_id=str(uuid.uuid4()),
        created_by=actor_user_id,
        max_attempts=3,
        priority=50,
    )


def platform_capabilities(db: Session) -> dict[str, Any]:
    providers = list_provider_credentials(db)
    queue = saas_queue.queue_summary(db)
    return {
        "providers": providers,
        "queue": queue,
        "counts": {
            "module_prices": db.query(func.count(models.SaaSModulePrice.id)).scalar() or 0,
            "billing_accounts": db.query(func.count(models.SaaSBillingAccount.id)).scalar() or 0,
            "open_support_tickets": db.query(func.count(platform_models.PlatformSupportTicket.id)).filter(platform_models.PlatformSupportTicket.status.in_(["OPEN", "PENDING", "IN_PROGRESS"])).scalar() or 0,
            "pending_fiscalizations": db.query(func.count(models.SaaSInvoiceFiscalization.id)).filter(models.SaaSInvoiceFiscalization.status.in_(["PENDING", "QUEUED", "SUBMITTED"])).scalar() or 0,
        },
        "controls": {
            "provider_secrets_encrypted": True,
            "provider_secrets_returned_to_frontend": False,
            "billing_activation_requires_verified_webhook": True,
            "etims_requires_certified_adapter": True,
            "durable_queue": "postgresql_skip_locked",
        },
    }
