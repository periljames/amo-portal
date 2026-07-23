from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import models as platform_models
from amodb.apps.platform import saas_models, saas_queue, saas_side_effects


def test_non_repeatable_jobs_have_one_attempt_and_cannot_be_manually_retried():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    saas_models.SaaSJob.__table__.create(engine)
    saas_models.SaaSJobEvent.__table__.create(engine)
    db = sessionmaker(bind=engine, future=True, expire_on_commit=False)()

    job = saas_queue.enqueue_job(
        db,
        job_type="ETIMS_FISCALIZE_INVOICE",
        payload={},
        idempotency_key="etims:invoice:one",
        max_attempts=9,
    )
    assert job.max_attempts == 1
    job.status = "DEAD"
    db.commit()
    with pytest.raises(ValueError, match="non-repeatable"):
        saas_queue.retry_job(db, job)


def test_uncertain_etims_outcome_uses_real_invoice_fields_and_requires_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
):
    fiscalization = SimpleNamespace(
        id="fiscal-1",
        invoice_id="invoice-1",
        status="PENDING",
        request_json={},
        response_json=None,
        submitted_at=None,
        fiscalized_at=None,
        last_error=None,
        fiscal_document_number=None,
        control_unit_serial=None,
        receipt_signature=None,
    )
    credential = SimpleNamespace(
        id="credential-1",
        provider="etims_oscu",
        status="CONFIGURED",
        encrypted_secret="encrypted",
        config_json={"certified": True},
    )
    invoice = SimpleNamespace(
        id="invoice-1",
        amo_id="amo-1",
        currency="KES",
        amount_cents=11600,
        description="Quality module annual subscription",
        issued_at=None,
        due_at=None,
        amo=SimpleNamespace(
            name="Example AMO",
            contact_email="billing@example.test",
            contact_phone="+254700000000",
            country="KE",
        ),
    )
    job = SimpleNamespace(
        id="job-1",
        idempotency_key="fiscalize:invoice-1",
        payload_json={
            "fiscalization_id": fiscalization.id,
            "credential_id": credential.id,
        },
    )
    db = MagicMock()

    def get(model, identifier):
        if model is saas_models.SaaSInvoiceFiscalization:
            return fiscalization
        if model is saas_models.SaaSProviderCredential:
            return credential
        if model is account_models.BillingInvoice:
            return invoice
        raise AssertionError((model, identifier))

    db.get.side_effect = get
    monkeypatch.setattr(
        saas_side_effects.saas_secrets,
        "decrypt_secret",
        lambda value: {"client_secret": "secret"},
    )
    monkeypatch.setattr(
        saas_side_effects.account_services,
        "format_invoice_number",
        lambda value: "INV-000001",
    )
    provider = MagicMock(side_effect=TimeoutError("provider timed out"))
    monkeypatch.setattr(
        saas_side_effects.saas_providers,
        "fiscalize_etims_invoice",
        provider,
    )

    with pytest.raises(saas_side_effects.NonRepeatableJobError):
        saas_side_effects.process_etims_fiscalization(db, job=job)
    assert fiscalization.status == "RECONCILIATION_REQUIRED"
    assert fiscalization.request_json == {
        "submission_reference": "amo-portal:fiscalize:invoice-1",
        "portal_invoice_id": "invoice-1",
        "invoice_number": "INV-000001",
        "issued_at": None,
        "due_at": None,
        "currency": "KES",
        "total_amount_cents": 11600,
        "description": "Quality module annual subscription",
        "buyer": {
            "tenant_id": "amo-1",
            "name": "Example AMO",
            "email": "billing@example.test",
            "phone": "+254700000000",
            "country": "KE",
        },
    }
    assert fiscalization.response_json["submission_reference"] == "amo-portal:fiscalize:invoice-1"
    assert db.commit.call_count >= 2

    with pytest.raises(saas_side_effects.NonRepeatableJobError, match="reconcile"):
        saas_side_effects.process_etims_fiscalization(db, job=job)
    assert provider.call_count == 1



@pytest.mark.parametrize(
    ("processor", "job_type", "label"),
    [
        (saas_side_effects.process_etims_fiscalization, "ETIMS_FISCALIZE_INVOICE", "eTIMS"),
        (saas_side_effects.process_ai_support_reply, "AI_SUPPORT_REPLY", "OpenAI"),
    ],
)
def test_disabled_provider_is_rejected_again_when_worker_executes(
    monkeypatch: pytest.MonkeyPatch,
    processor,
    job_type: str,
    label: str,
):
    credential = SimpleNamespace(
        id="credential-disabled",
        provider="etims_oscu" if job_type == "ETIMS_FISCALIZE_INVOICE" else "openai",
        status="DISABLED",
        encrypted_secret="encrypted",
        config_json={"certified": True},
    )
    job = SimpleNamespace(
        id="job-disabled",
        created_by="support-user",
        idempotency_key="disabled-side-effect",
        payload_json={
            "credential_id": credential.id,
            "fiscalization_id": "fiscal-disabled",
            "ticket_id": "ticket-disabled",
        },
    )
    fiscalization = SimpleNamespace(
        id="fiscal-disabled",
        invoice_id="invoice-disabled",
        status="PENDING",
    )
    ticket = SimpleNamespace(id="ticket-disabled")
    detail = SimpleNamespace(description="Support request", category="GENERAL")
    db = MagicMock()

    def get(model, identifier):
        if model is saas_models.SaaSProviderCredential:
            return credential
        if model is saas_models.SaaSInvoiceFiscalization:
            return fiscalization
        if model is platform_models.PlatformSupportTicket:
            return ticket
        if model is saas_models.SaaSSupportTicketDetail:
            return detail
        if model is account_models.BillingInvoice:
            return SimpleNamespace(id="invoice-disabled")
        raise AssertionError((model, identifier))

    db.get.side_effect = get
    db.query.return_value.filter.return_value.first.return_value = None
    decrypt = MagicMock()
    monkeypatch.setattr(saas_side_effects.saas_secrets, "decrypt_secret", decrypt)

    with pytest.raises(ValueError, match=f"{label} provider is disabled"):
        processor(db, job=job)

    decrypt.assert_not_called()

def test_ai_support_reply_uses_existing_adapter_and_is_deduplicated_by_source_job(
    monkeypatch: pytest.MonkeyPatch,
):
    job = SimpleNamespace(
        id="job-ai-1",
        created_by="support-user",
        payload_json={"ticket_id": "ticket-1", "credential_id": "credential-1"},
    )
    credential = SimpleNamespace(
        id="credential-1",
        status="HEALTHY",
        encrypted_secret="encrypted",
        config_json={"model": "test-model"},
    )
    ticket = SimpleNamespace(
        id="ticket-1",
        title="Unable to upload",
        priority="NORMAL",
        updated_at=None,
    )
    detail = SimpleNamespace(description="Upload failed", category="GENERAL")
    db = MagicMock()
    existing_holder = {"message": None}

    def query(model):
        chain = MagicMock()
        if model is saas_models.SaaSSupportTicketMessage:
            filtered = chain.filter.return_value
            filtered.first.side_effect = lambda: existing_holder["message"]
            filtered.order_by.return_value.limit.return_value.all.return_value = []
        return chain

    db.query.side_effect = query

    def get(model, identifier):
        if model is saas_models.SaaSProviderCredential:
            return credential
        if model is platform_models.PlatformSupportTicket:
            return ticket
        if model is saas_models.SaaSSupportTicketDetail:
            return detail
        raise AssertionError((model, identifier))

    db.get.side_effect = get

    def add(message):
        message.id = "message-ai-1"
        existing_holder["message"] = message

    db.add.side_effect = add
    monkeypatch.setattr(
        saas_side_effects.saas_secrets,
        "decrypt_secret",
        lambda value: {"api_key": "secret"},
    )
    provider = MagicMock(
        return_value={
            "text": "Please retry the upload and share the correlation ID.",
            "provider": "openai",
            "model": "test-model",
            "usage": {},
        }
    )
    monkeypatch.setattr(
        saas_side_effects.saas_providers,
        "openai_support_response",
        provider,
    )

    first = saas_side_effects.process_ai_support_reply(db, job=job)
    second = saas_side_effects.process_ai_support_reply(db, job=job)

    assert first["message_id"] == "message-ai-1"
    assert second == {
        "ticket_id": "ticket-1",
        "message_id": "message-ai-1",
        "replayed": False,
    }
    assert existing_holder["message"].source_job_id == job.id
    assert existing_holder["message"].body == "Please retry the upload and share the correlation ID."
    assert provider.call_count == 1
