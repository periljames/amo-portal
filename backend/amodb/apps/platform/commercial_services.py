from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import services as account_services
from amodb.security import SECRET_KEY

from . import models as platform_models
from . import saas_models as models
from . import saas_queue, saas_secrets, saas_services
from . import commercial_integrations as integrations
from . import module_commerce


COMMERCIAL_JOB_TYPES = frozenset(
    {
        "PAYSTACK_INITIATE_PAYMENT",
        "PAYSTACK_WEBHOOK",
        "MPESA_STK_PUSH",
        "MPESA_CALLBACK",
        "QUICKBOOKS_SYNC_INVOICE",
    }
)

ACTIVE_COMMERCIAL_STATES = frozenset(
    {
        "ACTIVE",
        "TRIALING",
        "CHECKOUT_PENDING",
        "PAYMENT_PENDING",
        "PAST_DUE",
    }
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_description(invoice: account_models.BillingInvoice) -> dict[str, Any]:
    raw = invoice.description
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {"description": str(raw)}
    return value if isinstance(value, dict) else {"description": str(raw)}


def _invoice_payload(invoice: account_models.BillingInvoice) -> dict[str, Any]:
    return {
        "id": invoice.id,
        "invoice_number": account_services.format_invoice_number(invoice),
        "amo_id": invoice.amo_id,
        "amount_cents": int(invoice.amount_cents or 0),
        "currency": str(invoice.currency or "USD").upper(),
        "status": getattr(invoice.status, "value", str(invoice.status)),
        "issued_at": invoice.issued_at,
        "due_at": invoice.due_at,
        "paid_at": invoice.paid_at,
        "commercial": _json_description(invoice),
    }


def _audit(
    db: Session,
    *,
    actor_user_id: str | None,
    action: str,
    tenant_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        platform_models.PlatformAuditLog(
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            action=action,
            module="billing",
            entity_type=entity_type,
            entity_id=entity_id,
            reason=(reason or "")[:1000] or None,
            details_json=details or {},
        )
    )


def _invoice(
    db: Session,
    invoice_id: str,
    *,
    tenant_id: str | None = None,
    lock: bool = False,
) -> account_models.BillingInvoice:
    query = db.query(account_models.BillingInvoice).filter(account_models.BillingInvoice.id == invoice_id)
    if tenant_id:
        query = query.filter(account_models.BillingInvoice.amo_id == tenant_id)
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise ValueError("Invoice not found")
    return row


def _provider_credential(
    db: Session,
    provider: str,
    *,
    tenant_id: str | None = None,
) -> models.SaaSProviderCredential:
    row = saas_services.get_provider_credential(db, provider=provider, tenant_id=tenant_id)
    if row is None:
        raise ValueError(f"{provider} is not configured")
    saas_services.require_operational_provider(row, label=provider)
    return row


def _billing_account(
    db: Session,
    *,
    tenant_id: str,
    provider: str,
    lock: bool = False,
) -> models.SaaSBillingAccount | None:
    query = db.query(models.SaaSBillingAccount).filter(
        models.SaaSBillingAccount.tenant_id == tenant_id,
        models.SaaSBillingAccount.provider == provider,
    )
    if lock:
        query = query.with_for_update()
    return query.first()


def _upsert_billing_account(
    db: Session,
    *,
    tenant_id: str,
    provider: str,
    status: str,
    customer_ref: str | None = None,
    subscription_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> models.SaaSBillingAccount:
    row = _billing_account(db, tenant_id=tenant_id, provider=provider, lock=True)
    if row is None:
        row = models.SaaSBillingAccount(tenant_id=tenant_id, provider=provider)
        db.add(row)
    row.status = str(status or "UNKNOWN").strip().upper()
    if customer_ref:
        row.external_customer_ref = customer_ref
    if subscription_ref:
        row.external_subscription_ref = subscription_ref
    row.auto_collection = provider in {"stripe", integrations.PAYSTACK_CODE, "mpesa_daraja"}
    if metadata is not None:
        row.metadata_json = metadata
    db.flush()
    return row


def _existing_payment_ledger(
    db: Session,
    *,
    tenant_id: str,
    idempotency_key: str,
) -> account_models.LedgerEntry | None:
    return (
        db.query(account_models.LedgerEntry)
        .filter(
            account_models.LedgerEntry.amo_id == tenant_id,
            account_models.LedgerEntry.idempotency_key == idempotency_key,
        )
        .first()
    )


def _append_payment_ledger(
    db: Session,
    *,
    invoice: account_models.BillingInvoice,
    provider: str,
    provider_reference: str,
    paid_at: datetime,
) -> account_models.LedgerEntry:
    key = f"payment:{provider}:{provider_reference}"[:128]
    existing = _existing_payment_ledger(db, tenant_id=invoice.amo_id, idempotency_key=key)
    if existing is not None:
        return existing
    entry = account_models.LedgerEntry(
        amo_id=invoice.amo_id,
        license_id=invoice.license_id,
        amount_cents=int(invoice.amount_cents or 0),
        currency=str(invoice.currency or "USD").upper(),
        entry_type=account_models.LedgerEntryType.PAYMENT,
        description=json.dumps(
            {
                "invoice_id": invoice.id,
                "invoice_number": account_services.format_invoice_number(invoice),
                "provider": provider,
                "provider_reference": provider_reference,
            },
            separators=(",", ":"),
        ),
        idempotency_key=key,
        recorded_at=paid_at,
    )
    db.add(entry)
    db.flush()
    return entry


def _activation_details(invoice: account_models.BillingInvoice) -> dict[str, Any]:
    raw = invoice.description
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}

def _activation_activation_period_delta(term: str) -> timedelta:
    normalized = str(term or "MONTHLY").strip().upper()
    if normalized == "ANNUAL":
        return timedelta(days=365)
    if normalized == "BI_ANNUAL":
        return timedelta(days=182)
    return timedelta(days=30)

def _activation_activation_metadata(row: account_models.ModuleSubscription) -> dict[str, Any]:
    if not row.metadata_json:
        return {}
    try:
        value = json.loads(row.metadata_json)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}

def _restore_base_license(
    db: Session,
    *,
    invoice: account_models.BillingInvoice,
    commercial: dict[str, Any],
) -> bool:
    if str(commercial.get("source") or "").upper() != "BASE_RENEWAL":
        return False
    if not invoice.license_id:
        raise ValueError("Base renewal invoice is missing its licence reference")
    license = db.get(account_models.TenantLicense, invoice.license_id)
    if license is None or str(license.amo_id) != str(invoice.amo_id):
        raise ValueError("Base renewal licence does not match the invoice tenant")

    now = datetime.now(timezone.utc)
    term = str(commercial.get("billing_term") or getattr(license.term, "value", license.term) or "MONTHLY")
    license.status = account_models.LicenseStatus.ACTIVE
    license.is_read_only = False
    license.current_period_start = now
    license.current_period_end = now + _activation_period_delta(term)
    license.trial_grace_expires_at = None
    db.add(license)
    db.flush()
    return True


def _enable_paid_module(
    db: Session,
    *,
    invoice: account_models.BillingInvoice,
    provider: str,
    provider_reference: str,
) -> account_models.ModuleSubscription | None:
    commercial = _activation_details(invoice)
    if _restore_base_license(db, invoice=invoice, commercial=commercial):
        return None

    root_code = module_commerce.normalize_code(str(commercial.get("module_code") or ""))
    if not root_code:
        return None

    activation_codes = [
        module_commerce.normalize_code(str(value))
        for value in (commercial.get("activation_codes") or [])
        if str(value).strip()
    ]
    codes: list[str] = []
    for code in [root_code, *activation_codes]:
        if code and code not in codes:
            codes.append(code)

    now = datetime.now(timezone.utc)
    term = str(commercial.get("billing_term") or "MONTHLY").strip().upper()
    delta = _activation_period_delta(term)
    subtotal_cents = int(commercial.get("subtotal_cents") or invoice.amount_cents or 0)
    tax_amount_cents = int(commercial.get("tax_amount_cents") or 0)
    tax_rate_bps = int(commercial.get("tax_rate_bps") or 0)
    root_row: account_models.ModuleSubscription | None = None

    for code in codes:
        row = (
            db.query(account_models.ModuleSubscription)
            .filter(
                account_models.ModuleSubscription.amo_id == invoice.amo_id,
                account_models.ModuleSubscription.module_code == code,
            )
            .first()
        )
        if row is None:
            row = account_models.ModuleSubscription(
                amo_id=invoice.amo_id,
                module_code=code,
                status=account_models.ModuleSubscriptionStatus.ENABLED,
            )
            db.add(row)

        previous_end = row.effective_to
        if previous_end is not None and previous_end.tzinfo is None:
            previous_end = previous_end.replace(tzinfo=timezone.utc)
        period_start = previous_end if previous_end and previous_end > now else now
        period_end = period_start + delta

        row.status = account_models.ModuleSubscriptionStatus.ENABLED
        row.plan_code = str(commercial.get("plan_code") or row.plan_code or "STANDARD").strip().upper()
        row.effective_from = row.effective_from or period_start
        row.effective_to = period_end

        metadata = _activation_metadata(row)
        metadata.update(
            {
                "commercial_offer_only": False,
                "billing_provider": provider,
                "payment_reference": provider_reference,
                "portal_invoice_id": invoice.id,
                "contract_module_code": root_code,
                "activation_codes": activation_codes,
                "bundle_parent": root_code if code != root_code else None,
                "billing_term": term,
                "plan_code": row.plan_code,
                "subtotal_cents": subtotal_cents,
                "tax_rate_bps": tax_rate_bps,
                "tax_amount_cents": tax_amount_cents,
                "amount_cents": int(invoice.amount_cents or 0),
                "currency": str(invoice.currency or "USD").upper(),
                "current_period_start": period_start.isoformat(),
                "current_period_end": period_end.isoformat(),
                "auto_renew": bool(commercial.get("auto_renew_accepted", True)),
                "terms_version": commercial.get("terms_version"),
                "last_settled_invoice_id": invoice.id,
                "renewal_invoice_id": None,
                "updated_by": "verified_payment",
                "updated_at": now.isoformat(),
            }
        )
        row.metadata_json = json.dumps(metadata, separators=(",", ":"))
        if code == root_code:
            root_row = row

    db.flush()
    return root_row



def mark_invoice_paid(
    db: Session,
    *,
    invoice_id: str,
    provider: str,
    provider_reference: str,
    actor_user_id: str | None,
    paid_at: datetime | None = None,
    verified_amount_cents: int | None = None,
    verified_currency: str | None = None,
    reason: str = "Verified payment settlement",
) -> dict[str, Any]:
    reference = str(provider_reference or "").strip()
    if not reference:
        raise ValueError("A provider payment reference is required")
    invoice = _invoice(db, invoice_id, lock=True)
    expected_amount = int(invoice.amount_cents or 0)
    expected_currency = str(invoice.currency or "USD").upper()
    if verified_amount_cents is not None and int(verified_amount_cents) != expected_amount:
        raise ValueError("Provider amount does not match the portal invoice")
    if verified_currency is not None and str(verified_currency).upper() != expected_currency:
        raise ValueError("Provider currency does not match the portal invoice")

    if invoice.status == account_models.InvoiceStatus.PAID:
        return _invoice_payload(invoice)
    if invoice.status == account_models.InvoiceStatus.VOID:
        raise ValueError("A void invoice cannot be settled")

    paid_at = paid_at or utcnow()
    invoice.status = account_models.InvoiceStatus.PAID
    invoice.paid_at = paid_at
    payment = _append_payment_ledger(
        db,
        invoice=invoice,
        provider=provider,
        provider_reference=reference,
        paid_at=paid_at,
    )
    module = _enable_paid_module(
        db,
        invoice=invoice,
        provider=provider,
        provider_reference=reference,
    )
    account = _billing_account(db, tenant_id=invoice.amo_id, provider=provider, lock=True)
    if account is not None:
        metadata = dict(account.metadata_json or {})
        metadata.update(
            {
                "last_paid_invoice_id": invoice.id,
                "last_payment_reference": reference,
                "last_payment_amount_cents": expected_amount,
                "last_payment_currency": expected_currency,
                "last_payment_at": paid_at.isoformat(),
            }
        )
        account.status = "ACTIVE"
        account.metadata_json = metadata

    tenant = db.get(account_models.AMO, invoice.amo_id)
    conflict = bool(tenant is not None and not tenant.is_active)
    _audit(
        db,
        actor_user_id=actor_user_id,
        action="billing.invoice.settled",
        tenant_id=invoice.amo_id,
        entity_type="billing_invoice",
        entity_id=invoice.id,
        reason=reason,
        details={
            "provider": provider,
            "provider_reference": reference,
            "payment_ledger_id": payment.id,
            "module_code": getattr(module, "module_code", None),
            "administrative_status_conflict": conflict,
        },
    )
    db.commit()
    db.refresh(invoice)
    return _invoice_payload(invoice)


def record_offline_payment(
    db: Session,
    *,
    invoice_id: str,
    reference: str,
    actor_user_id: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        raise ValueError("A reason is required for a manual/offline payment")
    if not str(reference or "").strip():
        raise ValueError("A bank or offline payment reference is required")
    return mark_invoice_paid(
        db,
        invoice_id=invoice_id,
        provider="offline",
        provider_reference=str(reference).strip(),
        actor_user_id=actor_user_id,
        reason=reason,
    )


def _commercial_snapshot(invoice: account_models.BillingInvoice) -> dict[str, Any]:
    return {
        "invoice_id": invoice.id,
        "tenant_id": invoice.amo_id,
        "amount_cents": int(invoice.amount_cents or 0),
        "currency": str(invoice.currency or "USD").upper(),
        "invoice_number": account_services.format_invoice_number(invoice),
        "commercial": _json_description(invoice),
    }


def enqueue_invoice_payment(
    db: Session,
    *,
    invoice_id: str,
    provider: str,
    actor_user_id: str,
    idempotency_key: str,
    phone: str | None = None,
) -> models.SaaSJob:
    normalized_provider = str(provider or "").strip().lower()
    if normalized_provider not in {integrations.PAYSTACK_CODE, "mpesa_daraja"}:
        raise ValueError("Supported invoice collection providers are paystack and mpesa_daraja")
    key = str(idempotency_key or "").strip()
    if not key:
        raise ValueError("idempotency_key is required")
    invoice = _invoice(db, invoice_id)
    if invoice.status == account_models.InvoiceStatus.PAID:
        raise ValueError("Invoice is already paid")
    if invoice.status == account_models.InvoiceStatus.VOID:
        raise ValueError("Void invoices cannot be collected")
    tenant = db.get(account_models.AMO, invoice.amo_id)
    if tenant is None:
        raise ValueError("Invoice tenant not found")
    credential = _provider_credential(db, normalized_provider, tenant_id=invoice.amo_id)
    payload = {
        **_commercial_snapshot(invoice),
        "credential_id": credential.id,
        "tenant_email": tenant.contact_email,
        "tenant_phone": phone or tenant.contact_phone,
    }
    job_type = "PAYSTACK_INITIATE_PAYMENT" if normalized_provider == integrations.PAYSTACK_CODE else "MPESA_STK_PUSH"
    return saas_queue.enqueue_job(
        db,
        job_type=job_type,
        queue_name="billing",
        tenant_id=invoice.amo_id,
        payload=payload,
        idempotency_key=key,
        correlation_id=str(uuid.uuid4()),
        created_by=actor_user_id,
        max_attempts=1,
        priority=10,
    )


def _process_paystack_initiate(db: Session, job: models.SaaSJob) -> dict[str, Any]:
    payload = dict(job.payload_json or {})
    invoice = _invoice(db, str(payload.get("invoice_id") or ""), tenant_id=str(job.tenant_id or ""), lock=True)
    credential = db.get(models.SaaSProviderCredential, str(payload.get("credential_id") or ""))
    if credential is None:
        raise ValueError("Paystack credential is missing")
    saas_services.require_operational_provider(credential, label="Paystack")
    tenant = db.get(account_models.AMO, invoice.amo_id)
    if tenant is None:
        raise ValueError("Invoice tenant not found")
    reference = f"amo-{invoice.id}-{hashlib.sha256(str(job.idempotency_key).encode()).hexdigest()[:12]}"[:100]
    result = integrations.paystack_initialize_transaction(
        secret=saas_services.provider_secrets(credential),
        config=credential.config_json or {},
        email=str(payload.get("tenant_email") or tenant.contact_email or "").strip(),
        amount_subunit=int(invoice.amount_cents or 0),
        currency=str(invoice.currency or "USD").upper(),
        reference=reference,
        metadata={
            "tenant_id": invoice.amo_id,
            "portal_invoice_id": invoice.id,
            "invoice_number": account_services.format_invoice_number(invoice),
            "module_code": _json_description(invoice).get("module_code"),
        },
    )
    previous = _billing_account(db, tenant_id=invoice.amo_id, provider=integrations.PAYSTACK_CODE, lock=True)
    previous_meta = dict(previous.metadata_json or {}) if previous else {}
    _upsert_billing_account(
        db,
        tenant_id=invoice.amo_id,
        provider=integrations.PAYSTACK_CODE,
        status="PAYMENT_PENDING",
        customer_ref=None,
        metadata={
            **previous_meta,
            "pending_invoice_id": invoice.id,
            "reference": result["reference"],
            "authorization_url": result["authorization_url"],
            "access_code": result.get("access_code"),
            "amount_cents": int(invoice.amount_cents or 0),
            "currency": str(invoice.currency or "USD").upper(),
            "job_id": job.id,
            "created_at": utcnow().isoformat(),
        },
    )
    db.flush()
    return result


def _metadata_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}
    return {}


def record_paystack_webhook(
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



def _process_paystack_webhook(db: Session, job: models.SaaSJob) -> dict[str, Any]:
    payload = dict(job.payload_json or {})
    event_type = str(payload.get("event_type") or "").strip().lower()
    reference = str(payload.get("reference") or "").strip()
    invoice = _invoice(db, str(payload.get("invoice_id") or ""), tenant_id=str(job.tenant_id or ""), lock=True)
    credential = db.get(models.SaaSProviderCredential, str(payload.get("credential_id") or ""))
    if credential is None:
        raise ValueError("Paystack credential is missing")
    saas_services.require_operational_provider(credential, label="Paystack")
    if event_type != "charge.success":
        return {"ignored": True, "event_type": event_type, "reference": reference}
    verification = integrations.paystack_verify_transaction(
        secret=saas_services.provider_secrets(credential),
        config=credential.config_json or {},
        reference=reference,
    )
    data = verification.get("data") or {}
    if not isinstance(data, dict) or str(data.get("status") or "").lower() != "success":
        raise ValueError("Paystack transaction is not verified as successful")
    metadata = _metadata_dict(data.get("metadata"))
    if str(metadata.get("tenant_id") or "") != invoice.amo_id or str(metadata.get("portal_invoice_id") or "") != invoice.id:
        raise ValueError("Paystack verified transaction metadata does not match the portal invoice")
    paid = mark_invoice_paid(
        db,
        invoice_id=invoice.id,
        provider=integrations.PAYSTACK_CODE,
        provider_reference=reference,
        actor_user_id=job.created_by,
        verified_amount_cents=int(data.get("amount") or 0),
        verified_currency=str(data.get("currency") or ""),
        reason="Paystack transaction verified server-side",
    )
    return {"verified": True, "reference": reference, "invoice": paid}


def _callback_token(*, tenant_id: str, invoice_id: str, idempotency_key: str) -> str:
    material = f"{tenant_id}:{invoice_id}:{idempotency_key}".encode("utf-8")
    return hmac.new(SECRET_KEY.encode("utf-8"), material, hashlib.sha256).hexdigest()


def _callback_url(base: str, *, tenant_id: str, invoice_id: str, token: str) -> str:
    clean = saas_services.saas_providers._safe_url(base) if hasattr(saas_services, "saas_providers") else base
    parsed = urllib.parse.urlsplit(clean)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.extend([("tenant_id", tenant_id), ("invoice_id", invoice_id), ("token", token)])
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment))


def _process_mpesa_stk(db: Session, job: models.SaaSJob) -> dict[str, Any]:
    payload = dict(job.payload_json or {})
    tenant_id = str(job.tenant_id or "")
    invoice = _invoice(db, str(payload.get("invoice_id") or ""), tenant_id=tenant_id, lock=True)
    if str(invoice.currency or "").upper() != "KES":
        raise ValueError("Direct M-PESA collection currently requires a KES invoice")
    if int(invoice.amount_cents or 0) % 100 != 0:
        raise ValueError("M-PESA invoice amount must resolve to a whole KES amount")
    credential = db.get(models.SaaSProviderCredential, str(payload.get("credential_id") or ""))
    if credential is None:
        raise ValueError("M-PESA credential is missing")
    saas_services.require_operational_provider(credential, label="M-PESA Daraja")
    config = dict(credential.config_json or {})
    base_callback = str(config.get("callback_url") or "").strip()
    if not base_callback:
        raise ValueError("M-PESA callback_url is not configured")
    token = _callback_token(tenant_id=tenant_id, invoice_id=invoice.id, idempotency_key=str(job.idempotency_key))
    callback = _append_callback_query(base_callback, tenant_id=tenant_id, invoice_id=invoice.id, token=token)
    result = integrations.mpesa_stk_push(
        secret=saas_services.provider_secrets(credential),
        config=config,
        amount_kes=int(invoice.amount_cents or 0) // 100,
        phone=str(payload.get("tenant_phone") or ""),
        account_reference=account_services.format_invoice_number(invoice),
        description="AMO Portal bill",
        callback_url=callback,
    )
    previous = _billing_account(db, tenant_id=tenant_id, provider="mpesa_daraja", lock=True)
    previous_meta = dict(previous.metadata_json or {}) if previous else {}
    _upsert_billing_account(
        db,
        tenant_id=tenant_id,
        provider="mpesa_daraja",
        status="PAYMENT_PENDING",
        metadata={
            **previous_meta,
            "pending_invoice_id": invoice.id,
            "checkout_request_id": result["checkout_request_id"],
            "merchant_request_id": result.get("merchant_request_id"),
            "callback_token": token,
            "amount_kes": int(invoice.amount_cents or 0) // 100,
            "currency": "KES",
            "job_id": job.id,
            "created_at": utcnow().isoformat(),
        },
    )
    db.flush()
    return result


def _append_callback_query(base: str, *, tenant_id: str, invoice_id: str, token: str) -> str:
    clean = saas_services.saas_providers._safe_url(base) if hasattr(saas_services, "saas_providers") else base
    parsed = urllib.parse.urlsplit(clean)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.extend([("tenant_id", tenant_id), ("invoice_id", invoice_id), ("token", token)])
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment))


def _settlement_credential(
    db: Session,
    *,
    provider: str,
    tenant_id: str,
    label: str,
):
    row = saas_services.get_provider_credential(db, provider=provider, tenant_id=tenant_id)
    if row is None:
        raise ValueError(f"{label} is not configured")
    state = str(row.status or "").strip().upper()
    if state in {"DISABLED", "NOT_CONFIGURED"}:
        raise PermissionError(f"{label} settlement rejected because the provider is disabled")
    return row


def record_mpesa_callback(
    db: Session,
    *,
    tenant_id: str,
    invoice_id: str,
    token: str,
    payload: dict[str, Any],
):
    account = commercial_services._billing_account(db, tenant_id=tenant_id, provider="mpesa_daraja")
    if account is None or str(account.status or "").upper() != "PAYMENT_PENDING":
        raise ValueError("No pending M-PESA payment exists for this tenant")
    metadata = dict(account.metadata_json or {})
    if str(metadata.get("pending_invoice_id") or "") != invoice_id:
        raise ValueError("M-PESA callback invoice does not match the pending collection")
    if not hmac.compare_digest(str(metadata.get("callback_token") or ""), str(token or "")):
        raise PermissionError("Invalid M-PESA callback token")

    body = payload.get("Body") or {}
    stk = body.get("stkCallback") if isinstance(body, dict) else None
    if not isinstance(stk, dict) or "ResultCode" not in stk:
        raise ValueError("M-PESA callback is missing ResultCode")
    checkout_request_id = str(stk.get("CheckoutRequestID") or "").strip()
    if not checkout_request_id or checkout_request_id != str(metadata.get("checkout_request_id") or ""):
        raise ValueError("M-PESA checkout request does not match the pending collection")

    result_code = int(stk.get("ResultCode"))
    result_desc = str(stk.get("ResultDesc") or "")[:500]
    callback_items = commercial_services._mpesa_callback_items(stk) if result_code == 0 else {}
    amount = callback_items.get("Amount")
    receipt = str(callback_items.get("MpesaReceiptNumber") or "").strip() or None

    # Do not retain the full Safaricom callback. Phone number, transaction date
    # and other personal/provider metadata are unnecessary for settlement once
    # the callback has been authenticated and correlated. The server-side query
    # remains authoritative before money/access state is changed.
    return saas_queue.enqueue_job(
        db,
        job_type="MPESA_CALLBACK",
        queue_name="billing",
        tenant_id=tenant_id,
        payload={
            "invoice_id": invoice_id,
            "checkout_request_id": checkout_request_id,
            "result_code": result_code,
            "result_desc": result_desc,
            "amount_kes": str(amount) if amount is not None else None,
            "receipt_number": receipt,
            "data_minimized": True,
        },
        idempotency_key=f"mpesa:{checkout_request_id}:{result_code}",
        correlation_id=checkout_request_id,
        max_attempts=5,
        priority=5,
    )



def _mpesa_callback_items(stk: dict[str, Any]) -> dict[str, Any]:
    metadata = stk.get("CallbackMetadata") or {}
    items = metadata.get("Item") if isinstance(metadata, dict) else []
    result: dict[str, Any] = {}
    for item in items or []:
        if isinstance(item, dict) and item.get("Name"):
            result[str(item["Name"])] = item.get("Value")
    return result


def _process_mpesa_callback(db: Session, job) -> dict[str, Any]:
    payload = dict(job.payload_json or {})
    tenant_id = str(job.tenant_id or "")
    invoice = commercial_services._invoice(
        db,
        str(payload.get("invoice_id") or ""),
        tenant_id=tenant_id,
        lock=True,
    )
    account = commercial_services._billing_account(
        db,
        tenant_id=tenant_id,
        provider="mpesa_daraja",
        lock=True,
    )
    if account is None:
        raise ValueError("M-PESA billing account is missing")
    metadata = dict(account.metadata_json or {})
    checkout_request_id = str(payload.get("checkout_request_id") or "")
    if checkout_request_id != str(metadata.get("checkout_request_id") or ""):
        raise ValueError("M-PESA callback does not match the pending checkout")

    result_code = int(payload.get("result_code"))
    if result_code != 0:
        account.status = "PAYMENT_FAILED"
        metadata.update(
            {
                "last_result_code": result_code,
                "last_result_desc": str(payload.get("result_desc") or "")[:500],
            }
        )
        account.metadata_json = metadata
        db.flush()
        return {
            "paid": False,
            "result_code": result_code,
            "result_desc": payload.get("result_desc"),
        }

    credential = _settlement_credential(
        db,
        provider="mpesa_daraja",
        tenant_id=tenant_id,
        label="M-PESA Daraja",
    )
    verification = integrations.mpesa_query_stk(
        secret=saas_services.provider_secrets(credential),
        config=credential.config_json or {},
        checkout_request_id=checkout_request_id,
    )
    verified = verification.get("data") or {}
    if not isinstance(verified, dict) or str(verified.get("ResultCode") or "") != "0":
        raise ValueError("M-PESA server-side STK query does not confirm successful settlement")

    receipt = str(payload.get("receipt_number") or "").strip()
    if not receipt:
        raise ValueError("Successful M-PESA callback is missing MpesaReceiptNumber")
    amount = Decimal(str(payload.get("amount_kes") or "0"))
    if amount <= 0:
        raise ValueError("Successful M-PESA callback is missing a positive settlement amount")
    amount_cents = int((amount * Decimal("100")).quantize(Decimal("1")))
    paid = commercial_services.mark_invoice_paid(
        db,
        invoice_id=invoice.id,
        provider="mpesa_daraja",
        provider_reference=receipt,
        actor_user_id=job.created_by,
        verified_amount_cents=amount_cents,
        verified_currency="KES",
        reason="M-PESA STK settlement confirmed by minimized callback and server-side query",
    )
    return {"paid": True, "receipt": receipt, "invoice": paid}



def _state_payload(tenant_id: str) -> str:
    payload = json.dumps(
        {"tenant_id": tenant_id, "nonce": secrets.token_urlsafe(12), "iat": int(utcnow().timestamp())},
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(SECRET_KEY.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _verify_state(state: str, *, max_age_seconds: int = 900) -> str:
    encoded, sep, signature = str(state or "").partition(".")
    if not sep or not encoded or not signature:
        raise PermissionError("Invalid QuickBooks OAuth state")
    expected = hmac.new(SECRET_KEY.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise PermissionError("Invalid QuickBooks OAuth state")
    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception as exc:
        raise PermissionError("Invalid QuickBooks OAuth state") from exc
    issued = int(payload.get("iat") or 0)
    if issued <= 0 or abs(int(utcnow().timestamp()) - issued) > max_age_seconds:
        raise PermissionError("QuickBooks OAuth state expired")
    tenant_id = str(payload.get("tenant_id") or "").strip()
    if tenant_id != "__platform__":
        raise PermissionError("QuickBooks OAuth state has an invalid scope")
    return tenant_id


def quickbooks_authorize(db: Session) -> dict[str, Any]:
    credential = saas_services.get_provider_credential(db, provider=integrations.QUICKBOOKS_CODE, tenant_id=None)
    if credential is None:
        raise ValueError("QuickBooks Online provider is not configured")
    secret = saas_services.provider_secrets(credential)
    if not str(secret.get("client_secret") or "").strip():
        raise ValueError("QuickBooks client_secret must be configured before linking")
    state = _state_payload("__platform__")
    return {
        "authorization_url": integrations.quickbooks_authorization_url(config=credential.config_json or {}, state=state),
        "state": state,
    }


def quickbooks_oauth_callback(
    db: Session,
    *,
    code: str,
    state: str,
    realm_id: str,
) -> dict[str, Any]:
    _verify_state(state)
    credential = saas_services.get_provider_credential(db, provider=integrations.QUICKBOOKS_CODE, tenant_id=None)
    if credential is None:
        raise ValueError("QuickBooks Online provider is not configured")
    current_secret = saas_services.provider_secrets(credential)
    tokens = integrations.quickbooks_exchange_code(
        secret=current_secret,
        config=credential.config_json or {},
        code=code,
    )
    now_epoch = int(utcnow().timestamp())
    merged_secret = {
        **current_secret,
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token") or current_secret.get("refresh_token"),
        "access_token_expires_at": now_epoch + int(tokens.get("expires_in") or 3600),
        "refresh_token_expires_at": now_epoch + int(tokens.get("x_refresh_token_expires_in") or 0),
    }
    credential.encrypted_secret, credential.secret_fingerprint = saas_secrets.encrypt_secret(merged_secret)
    credential.config_json = {**dict(credential.config_json or {}), "realm_id": str(realm_id or "").strip()}
    credential.status = "CONFIGURED"
    credential.configured_at = utcnow()
    _audit(
        db,
        actor_user_id=None,
        action="accounting.quickbooks.linked",
        entity_type="saas_provider_credential",
        entity_id=credential.id,
        reason="QuickBooks OAuth callback",
        details={"realm_id": str(realm_id or "").strip()},
    )
    db.commit()
    return {"linked": True, "realm_id": str(realm_id or "").strip()}


def _refresh_quickbooks(db: Session, credential: models.SaaSProviderCredential) -> dict[str, Any]:
    secret = saas_services.provider_secrets(credential)
    expires_at = int(secret.get("access_token_expires_at") or 0)
    if secret.get("access_token") and expires_at > int(utcnow().timestamp()) + 120:
        return secret
    tokens = integrations.quickbooks_refresh_tokens(secret=secret, config=credential.config_json or {})
    now_epoch = int(utcnow().timestamp())
    merged = {
        **secret,
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token") or secret.get("refresh_token"),
        "access_token_expires_at": now_epoch + int(tokens.get("expires_in") or 3600),
        "refresh_token_expires_at": now_epoch + int(tokens.get("x_refresh_token_expires_in") or 0),
    }
    credential.encrypted_secret, credential.secret_fingerprint = saas_secrets.encrypt_secret(merged)
    db.flush()
    return merged


def enqueue_quickbooks_sync(
    db: Session,
    *,
    invoice_id: str,
    actor_user_id: str,
) -> models.SaaSJob:
    invoice = _invoice(db, invoice_id)
    credential = _provider_credential(db, integrations.QUICKBOOKS_CODE, tenant_id=None)
    if not bool((credential.config_json or {}).get("writeback_enabled")):
        raise ValueError("QuickBooks writeback is disabled; enable it only after account/tax mappings are verified")
    return saas_queue.enqueue_job(
        db,
        job_type="QUICKBOOKS_SYNC_INVOICE",
        queue_name="integrations",
        tenant_id=invoice.amo_id,
        payload={"invoice_id": invoice.id, "credential_id": credential.id},
        idempotency_key=f"quickbooks:invoice:{invoice.id}:{invoice.updated_at.isoformat() if invoice.updated_at else 'v1'}",
        correlation_id=invoice.id,
        created_by=actor_user_id,
        max_attempts=1,
        priority=30,
    )


def _qbo_query(
    *,
    secret: dict[str, Any],
    config: dict[str, Any],
    query: str,
) -> list[dict[str, Any]]:
    encoded = urllib.parse.quote(query, safe="")
    status, response, _ = integrations.quickbooks_request(
        secret=secret,
        config=config,
        method="GET",
        path=f"query?query={encoded}",
    )
    if not 200 <= status < 300 or not isinstance(response, dict):
        raise RuntimeError(f"QuickBooks query failed ({status})")
    query_response = response.get("QueryResponse") or {}
    if not isinstance(query_response, dict):
        return []
    for key in ("Customer", "Invoice", "Payment"):
        value = query_response.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _qbo_customer(
    *,
    secret: dict[str, Any],
    config: dict[str, Any],
    tenant: account_models.AMO,
) -> str:
    display = f"{tenant.name} [{tenant.amo_code}]"[:100]
    escaped = display.replace("'", "\\'")
    rows = _qbo_query(secret=secret, config=config, query=f"select * from Customer where DisplayName = '{escaped}'")
    if rows and rows[0].get("Id"):
        return str(rows[0]["Id"])
    status, response, _ = integrations.quickbooks_request(
        secret=secret,
        config=config,
        method="POST",
        path="customer",
        body={
            "DisplayName": display,
            "CompanyName": str(tenant.name or display)[:100],
            **({"PrimaryEmailAddr": {"Address": tenant.contact_email}} if tenant.contact_email else {}),
            **({"PrimaryPhone": {"FreeFormNumber": tenant.contact_phone}} if tenant.contact_phone else {}),
        },
    )
    customer = response.get("Customer") if isinstance(response, dict) else None
    if not 200 <= status < 300 or not isinstance(customer, dict) or not customer.get("Id"):
        raise RuntimeError(f"QuickBooks customer creation failed ({status})")
    return str(customer["Id"])


def _qbo_create_invoice(
    *,
    secret: dict[str, Any],
    config: dict[str, Any],
    invoice: account_models.BillingInvoice,
    customer_id: str,
) -> dict[str, Any]:
    invoice_number = account_services.format_invoice_number(invoice)
    escaped = invoice_number.replace("'", "\\'")
    existing = _qbo_query(secret=secret, config=config, query=f"select * from Invoice where DocNumber = '{escaped}'")
    if existing:
        return existing[0]
    details = _json_description(invoice)
    subtotal_cents = int(details.get("subtotal_cents") or invoice.amount_cents or 0)
    tax_cents = int(details.get("tax_amount_cents") or max(0, int(invoice.amount_cents or 0) - subtotal_cents))
    item_id = str(config.get("income_item_id") or "").strip()
    if not item_id:
        raise ValueError("QuickBooks income_item_id mapping is required before invoice writeback")
    tax_code = str(config.get("tax_code_ref") or "").strip()
    if tax_cents and not tax_code:
        raise ValueError("QuickBooks tax_code_ref is required before tax-bearing invoices can be synchronized")
    line_detail: dict[str, Any] = {"ItemRef": {"value": item_id}, "Qty": 1, "UnitPrice": subtotal_cents / 100}
    if tax_code:
        line_detail["TaxCodeRef"] = {"value": tax_code}
    body: dict[str, Any] = {
        "DocNumber": invoice_number,
        "CustomerRef": {"value": customer_id},
        "TxnDate": (invoice.issued_at or utcnow()).date().isoformat(),
        "DueDate": (invoice.due_at or invoice.issued_at or utcnow()).date().isoformat(),
        "PrivateNote": f"AMO Portal invoice {invoice.id}",
        "Line": [
            {
                "Amount": subtotal_cents / 100,
                "DetailType": "SalesItemLineDetail",
                "Description": str(details.get("module_code") or details.get("description") or "AMO Portal subscription")[:4000],
                "SalesItemLineDetail": line_detail,
            }
        ],
    }
    status, response, _ = integrations.quickbooks_request(secret=secret, config=config, method="POST", path="invoice", body=body)
    qbo_invoice = response.get("Invoice") if isinstance(response, dict) else None
    if not 200 <= status < 300 or not isinstance(qbo_invoice, dict) or not qbo_invoice.get("Id"):
        raise RuntimeError(f"QuickBooks invoice creation failed ({status})")
    qbo_total = Decimal(str(qbo_invoice.get("TotalAmt") or "0"))
    portal_total = Decimal(int(invoice.amount_cents or 0)) / Decimal("100")
    if abs(qbo_total - portal_total) > Decimal("0.01"):
        raise RuntimeError("QuickBooks calculated total does not match the portal invoice; tax/account mapping requires reconciliation")
    return qbo_invoice


def _qbo_create_payment(
    *,
    secret: dict[str, Any],
    config: dict[str, Any],
    invoice: account_models.BillingInvoice,
    qbo_invoice_id: str,
    customer_id: str,
) -> dict[str, Any] | None:
    if invoice.status != account_models.InvoiceStatus.PAID:
        return None
    existing = _qbo_query(
        secret=secret,
        config=config,
        query=f"select * from Payment where CustomerRef = '{customer_id}' maxresults 1000",
    )
    note = f"AMO Portal payment {invoice.id}"
    for payment in existing:
        if str(payment.get("PrivateNote") or "") == note:
            return payment
    body: dict[str, Any] = {
        "CustomerRef": {"value": customer_id},
        "TotalAmt": int(invoice.amount_cents or 0) / 100,
        "TxnDate": (invoice.paid_at or utcnow()).date().isoformat(),
        "PrivateNote": note,
        "Line": [
            {
                "Amount": int(invoice.amount_cents or 0) / 100,
                "LinkedTxn": [{"TxnId": qbo_invoice_id, "TxnType": "Invoice"}],
            }
        ],
    }
    deposit = str(config.get("deposit_account_id") or "").strip()
    if deposit:
        body["DepositToAccountRef"] = {"value": deposit}
    status, response, _ = integrations.quickbooks_request(secret=secret, config=config, method="POST", path="payment", body=body)
    payment = response.get("Payment") if isinstance(response, dict) else None
    if not 200 <= status < 300 or not isinstance(payment, dict) or not payment.get("Id"):
        raise RuntimeError(f"QuickBooks payment creation failed ({status})")
    return payment


def _process_quickbooks_sync(db: Session, job: models.SaaSJob) -> dict[str, Any]:
    payload = dict(job.payload_json or {})
    invoice = _invoice(db, str(payload.get("invoice_id") or ""), tenant_id=str(job.tenant_id or ""), lock=True)
    credential = db.get(models.SaaSProviderCredential, str(payload.get("credential_id") or ""))
    if credential is None:
        raise ValueError("QuickBooks credential is missing")
    saas_services.require_operational_provider(credential, label="QuickBooks Online")
    config = dict(credential.config_json or {})
    if not bool(config.get("writeback_enabled")):
        raise ValueError("QuickBooks writeback was disabled after this job was queued")
    secret = _refresh_quickbooks(db, credential)
    tenant = db.get(account_models.AMO, invoice.amo_id)
    if tenant is None:
        raise ValueError("Invoice tenant not found")
    account = _billing_account(db, tenant_id=invoice.amo_id, provider=integrations.QUICKBOOKS_CODE, lock=True)
    metadata = dict(account.metadata_json or {}) if account else {}
    try:
        customer_id = str(metadata.get("qbo_customer_id") or "") or _qbo_customer(secret=secret, config=config, tenant=tenant)
        qbo_invoice = _qbo_create_invoice(secret=secret, config=config, invoice=invoice, customer_id=customer_id)
        qbo_payment = _qbo_create_payment(
            secret=secret,
            config=config,
            invoice=invoice,
            qbo_invoice_id=str(qbo_invoice["Id"]),
            customer_id=customer_id,
        )
    except Exception as exc:
        _upsert_billing_account(
            db,
            tenant_id=invoice.amo_id,
            provider=integrations.QUICKBOOKS_CODE,
            status="RECONCILIATION_REQUIRED",
            metadata={**metadata, "last_error": str(exc)[:4000], "last_invoice_id": invoice.id},
        )
        db.commit()
        raise
    invoice_links = dict(metadata.get("invoice_links") or {})
    payment_links = dict(metadata.get("payment_links") or {})
    invoice_links[invoice.id] = str(qbo_invoice["Id"])
    if qbo_payment and qbo_payment.get("Id"):
        payment_links[invoice.id] = str(qbo_payment["Id"])
    _upsert_billing_account(
        db,
        tenant_id=invoice.amo_id,
        provider=integrations.QUICKBOOKS_CODE,
        status="ACTIVE",
        customer_ref=customer_id,
        metadata={
            **metadata,
            "qbo_customer_id": customer_id,
            "invoice_links": invoice_links,
            "payment_links": payment_links,
            "last_synced_invoice_id": invoice.id,
            "last_synced_at": utcnow().isoformat(),
            "last_error": None,
        },
    )
    _audit(
        db,
        actor_user_id=job.created_by,
        action="accounting.quickbooks.invoice_synced",
        tenant_id=invoice.amo_id,
        entity_type="billing_invoice",
        entity_id=invoice.id,
        reason="QuickBooks Online writeback",
        details={"qbo_invoice_id": qbo_invoice.get("Id"), "qbo_payment_id": qbo_payment.get("Id") if qbo_payment else None},
    )
    db.commit()
    return {"invoice_id": invoice.id, "qbo_invoice_id": qbo_invoice.get("Id"), "qbo_payment_id": qbo_payment.get("Id") if qbo_payment else None}


def process_job(db: Session, job: models.SaaSJob) -> dict[str, Any]:
    if job.job_type == "PAYSTACK_INITIATE_PAYMENT":
        return _process_paystack_initiate(db, job)
    if job.job_type == "PAYSTACK_WEBHOOK":
        return _process_paystack_webhook(db, job)
    if job.job_type == "MPESA_STK_PUSH":
        return _process_mpesa_stk(db, job)
    if job.job_type == "MPESA_CALLBACK":
        return _process_mpesa_callback(db, job)
    if job.job_type == "QUICKBOOKS_SYNC_INVOICE":
        return _process_quickbooks_sync(db, job)
    raise ValueError(f"Unsupported commercial job type: {job.job_type}")


def commercial_summary(db: Session, *, data_mode: str = "REAL") -> dict[str, Any]:
    mode = str(data_mode or "REAL").strip().upper()
    tenant_query = db.query(account_models.AMO.id)
    if mode == "REAL":
        tenant_query = tenant_query.filter(account_models.AMO.is_demo.is_(False))
    elif mode == "DEMO":
        tenant_query = tenant_query.filter(account_models.AMO.is_demo.is_(True))
    tenant_ids = [str(row[0]) for row in tenant_query.all()]
    if not tenant_ids:
        return {
            "currency": "USD",
            "outstanding_ar_cents": 0,
            "overdue_ar_cents": 0,
            "overdue_invoice_count": 0,
            "invoiced_30d_cents": 0,
            "collected_30d_cents": 0,
            "failed_payment_jobs_30d": 0,
            "provider_statuses": {},
            "metric_quality": {"cohort_metrics": "NOT_IMPLEMENTED"},
        }
    now = utcnow()
    since = now - timedelta(days=30)
    invoices = db.query(account_models.BillingInvoice).filter(account_models.BillingInvoice.amo_id.in_(tenant_ids))
    outstanding = int(
        invoices.with_entities(func.coalesce(func.sum(account_models.BillingInvoice.amount_cents), 0))
        .filter(account_models.BillingInvoice.status == account_models.InvoiceStatus.PENDING)
        .scalar()
        or 0
    )
    overdue_q = invoices.filter(
        account_models.BillingInvoice.status == account_models.InvoiceStatus.PENDING,
        account_models.BillingInvoice.due_at.isnot(None),
        account_models.BillingInvoice.due_at < now,
    )
    overdue_amount = int(overdue_q.with_entities(func.coalesce(func.sum(account_models.BillingInvoice.amount_cents), 0)).scalar() or 0)
    overdue_count = int(overdue_q.count())
    invoiced_30d = int(
        invoices.with_entities(func.coalesce(func.sum(account_models.BillingInvoice.amount_cents), 0))
        .filter(account_models.BillingInvoice.created_at >= since)
        .scalar()
        or 0
    )
    collected_30d = int(
        invoices.with_entities(func.coalesce(func.sum(account_models.BillingInvoice.amount_cents), 0))
        .filter(
            account_models.BillingInvoice.status == account_models.InvoiceStatus.PAID,
            account_models.BillingInvoice.paid_at.isnot(None),
            account_models.BillingInvoice.paid_at >= since,
        )
        .scalar()
        or 0
    )
    failed_jobs = int(
        db.query(func.count(models.SaaSJob.id))
        .filter(
            models.SaaSJob.tenant_id.in_(tenant_ids),
            models.SaaSJob.queue_name == "billing",
            models.SaaSJob.status.in_(["FAILED", "DEAD"]),
            models.SaaSJob.created_at >= since,
        )
        .scalar()
        or 0
    )
    providers = saas_services.list_provider_credentials(db)
    provider_statuses = {str(item.get("provider")): str(item.get("status")) for item in providers if item.get("category") in {"BILLING", "PAYMENTS", "ACCOUNTING", "TAX"}}
    return {
        "currency": "USD",
        "outstanding_ar_cents": outstanding,
        "overdue_ar_cents": overdue_amount,
        "overdue_invoice_count": overdue_count,
        "invoiced_30d_cents": invoiced_30d,
        "collected_30d_cents": collected_30d,
        "failed_payment_jobs_30d": failed_jobs,
        "provider_statuses": provider_statuses,
        "metric_quality": {
            "ar_and_collection_metrics": "AUTHORITATIVE_PORTAL_SUBLEDGER",
            "mrr_arr": "LEGACY_LICENSE_MODEL_UNTIL_MODULE_PRICE_COHORT_RECONCILIATION",
            "logo_churn": "NOT_IMPLEMENTED",
            "net_revenue_retention": "NOT_IMPLEMENTED",
            "gross_revenue_retention": "NOT_IMPLEMENTED",
        },
    }


def capacity_readiness(db: Session) -> dict[str, Any]:
    write_url = str(os.getenv("DATABASE_WRITE_URL") or os.getenv("DATABASE_URL") or "")
    read_url = str(os.getenv("DATABASE_READ_URL") or write_url)
    external_pooler = str(os.getenv("DB_EXTERNAL_POOLER") or "").strip().lower() in {"1", "true", "yes", "on"}
    verified = str(os.getenv("LOAD_TEST_1000_VERIFIED") or "").strip().lower() in {"1", "true", "yes", "on"}
    worker_cutoff = utcnow() - timedelta(minutes=2)
    workers = int(
        db.query(func.count(platform_models.PlatformWorkerHeartbeat.id))
        .filter(platform_models.PlatformWorkerHeartbeat.last_seen_at >= worker_cutoff)
        .scalar()
        or 0
    )
    tenants = int(db.query(func.count(account_models.AMO.id)).filter(account_models.AMO.is_demo.is_(False)).scalar() or 0)
    users = int(db.query(func.count(account_models.User.id)).scalar() or 0)
    queue_depth = int(
        db.query(func.count(models.SaaSJob.id)).filter(models.SaaSJob.status.in_(["PENDING", "RETRY", "RUNNING"])).scalar()
        or 0
    )
    checks = {
        "postgresql_runtime": write_url.startswith("postgresql"),
        "read_replica_or_split_read_dsn": bool(read_url and read_url != write_url),
        "external_connection_pooler": external_pooler,
        "horizontal_saas_workers": workers >= 2,
        "durable_skip_locked_queue": True,
        "bounded_platform_pagination": True,
        "verified_1000_tenant_load_test": verified,
    }
    return {
        "target_concurrent_tenants": 1000,
        "status": "VERIFIED" if verified and all(value for key, value in checks.items() if key != "read_replica_or_split_read_dsn") else "NOT_YET_PROVEN",
        "checks": checks,
        "observed": {"real_tenants": tenants, "users": users, "active_saas_workers": workers, "queue_depth": queue_depth},
        "note": "Configuration is not a capacity guarantee. LOAD_TEST_1000_VERIFIED must only be set after the repository load harness passes against the intended production topology.",
    }
