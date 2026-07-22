from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import models as platform_models

from . import saas_models as models
from . import saas_providers, saas_secrets, saas_services


class NonRepeatableJobError(RuntimeError):
    """A side effect must not be automatically attempted again."""


def _invoice_payload(invoice: account_models.BillingInvoice, *, submission_reference: str) -> dict[str, Any]:
    return {
        "submission_reference": submission_reference,
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "tenant_id": invoice.amo_id,
        "currency": invoice.currency,
        "subtotal_cents": invoice.subtotal_cents,
        "tax_cents": invoice.tax_cents,
        "total_cents": invoice.total_cents,
        "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
        "due_at": invoice.due_at.isoformat() if invoice.due_at else None,
    }


def process_etims_fiscalization(
    db: Session,
    *,
    job: models.SaaSJob,
) -> dict[str, Any]:
    payload = job.payload_json or {}
    fiscalization = db.get(models.SaaSInvoiceFiscalization, str(payload.get("fiscalization_id") or ""))
    credential = db.get(models.SaaSProviderCredential, str(payload.get("credential_id") or ""))
    if fiscalization is None or credential is None:
        raise ValueError("Fiscalization record or credential is missing")
    invoice = db.get(account_models.BillingInvoice, fiscalization.invoice_id)
    if invoice is None:
        raise ValueError("Invoice is missing")

    if fiscalization.status == "FISCALIZED":
        return saas_services.fiscalization_payload(fiscalization) or {}
    if fiscalization.status in {"SUBMITTING", "RECONCILIATION_REQUIRED"}:
        raise NonRepeatableJobError(
            "eTIMS submission state is uncertain; reconcile with the certified adapter before any new attempt"
        )

    secret = saas_secrets.decrypt_secret(credential.encrypted_secret)
    request_payload = _invoice_payload(
        invoice,
        submission_reference=f"amo-portal:{job.idempotency_key}",
    )
    fiscalization.status = "SUBMITTING"
    fiscalization.request_json = request_payload
    fiscalization.submitted_at = saas_services.utcnow()
    fiscalization.last_error = None
    db.commit()

    try:
        result = saas_providers.fiscalize_etims_invoice(
            provider=credential.provider,
            secret=secret,
            config=credential.config_json or {},
            invoice_payload=request_payload,
        )
    except Exception as exc:
        # A transport exception cannot prove whether the certified control unit
        # accepted the invoice. Do not blindly POST it again.
        fiscalization = db.get(models.SaaSInvoiceFiscalization, fiscalization.id)
        if fiscalization is not None:
            fiscalization.status = "RECONCILIATION_REQUIRED"
            fiscalization.last_error = str(exc)[:4000]
            fiscalization.response_json = {
                "submission_reference": request_payload["submission_reference"],
                "detail": "Provider outcome is uncertain; manual reconciliation required.",
            }
            db.commit()
        raise NonRepeatableJobError(str(exc)) from exc

    fiscalization = db.get(models.SaaSInvoiceFiscalization, fiscalization.id)
    if fiscalization is None:
        raise NonRepeatableJobError("Fiscalization row disappeared after provider submission")
    fiscalization.status = "FISCALIZED"
    fiscalization.fiscal_document_number = result.get("fiscal_document_number")
    fiscalization.control_unit_serial = result.get("control_unit_serial")
    fiscalization.receipt_signature = result.get("receipt_signature")
    fiscalization.response_json = result.get("raw") or result
    fiscalization.fiscalized_at = saas_services.utcnow()
    fiscalization.last_error = None
    db.commit()
    return saas_services.fiscalization_payload(fiscalization) or {}


def process_ai_support_reply(
    db: Session,
    *,
    job: models.SaaSJob,
) -> dict[str, Any]:
    existing = (
        db.query(models.SaaSSupportTicketMessage)
        .filter(models.SaaSSupportTicketMessage.source_job_id == job.id)
        .first()
    )
    if existing is not None:
        return {"ticket_id": existing.ticket_id, "message_id": existing.id, "replayed": False}

    payload = job.payload_json or {}
    ticket_id = str(payload.get("ticket_id") or "")
    credential = db.get(models.SaaSProviderCredential, str(payload.get("credential_id") or ""))
    ticket = db.get(platform_models.PlatformSupportTicket, ticket_id)
    detail = db.get(models.SaaSSupportTicketDetail, ticket_id)
    if credential is None or ticket is None or detail is None:
        raise ValueError("Support ticket or OpenAI credential is missing")

    messages = (
        db.query(models.SaaSSupportTicketMessage)
        .filter(models.SaaSSupportTicketMessage.ticket_id == ticket_id)
        .order_by(models.SaaSSupportTicketMessage.created_at.asc())
        .all()
    )
    secret = saas_secrets.decrypt_secret(credential.encrypted_secret)
    draft = saas_providers.generate_openai_support_response(
        secret=secret,
        config=credential.config_json or {},
        ticket={
            "title": ticket.title,
            "description": detail.description,
            "priority": ticket.priority,
            "category": detail.category,
        },
        messages=[{"author_type": row.author_type, "body": row.body} for row in messages],
    )
    reply = str(draft.get("reply") or "").strip()
    if not reply:
        raise NonRepeatableJobError("AI provider returned an empty support draft")

    message = models.SaaSSupportTicketMessage(
        ticket_id=ticket_id,
        author_user_id=job.created_by,
        author_type="AI_ASSISTANT",
        visibility="PUBLIC",
        body=reply,
        source_job_id=job.id,
    )
    db.add(message)
    ticket.updated_at = saas_services.utcnow()
    db.commit()
    db.refresh(message)
    return {
        "ticket_id": ticket_id,
        "message_id": message.id,
        "provider": draft.get("provider"),
        "model": draft.get("model"),
        "usage": draft.get("usage"),
    }
