from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import saas_models, saas_services
from amodb.jobs import saas_worker


def _pending_account(*, previous_status: str | None = None) -> SimpleNamespace:
    metadata = {
        "checkout_session_id": "cs-1",
        "checkout_url": "https://checkout.stripe.test/cs-1",
        "checkout_job_id": "job-1",
        "checkout_idempotency_key": "checkout-action-1",
        "module_code": "quality",
        "module_price_id": "price-1",
        "external_price_ref": "price_stripe_1",
    }
    if previous_status:
        metadata["previous_account_status"] = previous_status
        metadata["previous_account_metadata"] = {"stripe_status": previous_status.lower()}
    return SimpleNamespace(
        tenant_id="amo-1",
        provider="stripe",
        status="CHECKOUT_PENDING",
        external_customer_ref="cus-1",
        external_subscription_ref="sub-existing",
        metadata_json=metadata,
    )


def _webhook_job() -> SimpleNamespace:
    return SimpleNamespace(
        id="webhook-job",
        tenant_id="amo-1",
        payload_json={"webhook_event_id": "stored-event", "verified_tenant_id": "amo-1"},
    )


def _checkout_event(event_type: str, payment_status: str = "unpaid") -> SimpleNamespace:
    return SimpleNamespace(
        payload=json.dumps({
            "id": f"evt-{event_type}",
            "type": event_type,
            "data": {
                "object": {
                    "id": "cs-1",
                    "client_reference_id": "amo-1",
                    "payment_status": payment_status,
                    "customer": "cus-1",
                    "subscription": "sub-new",
                    "metadata": {
                        "tenant_id": "amo-1",
                        "module_code": "quality",
                        "module_price_id": "price-1",
                        "external_price_ref": "price_stripe_1",
                    },
                }
            },
        }),
        status=account_models.WebhookStatus.RECEIVED,
        processed_at=None,
        attempt_count=0,
        last_error=None,
    )


def _run_checkout_event(monkeypatch: pytest.MonkeyPatch, event_type: str, *, previous_status: str | None = None):
    event = _checkout_event(event_type)
    account = _pending_account(previous_status=previous_status)
    db = MagicMock()
    db.get.return_value = event
    monkeypatch.setattr(
        saas_worker,
        "_validate_pending_checkout",
        lambda *_args, **_kwargs: (account, dict(account.metadata_json), "quality", "price-1", "price_stripe_1"),
    )
    upsert = MagicMock(return_value=account)
    monkeypatch.setattr(saas_worker, "_upsert_billing_account", upsert)
    set_module = MagicMock()
    monkeypatch.setattr(saas_worker, "_set_module_state", set_module)
    result = saas_worker._process_stripe_webhook(db, _webhook_job())
    return result, upsert, set_module


def test_expired_checkout_releases_new_account_pending_state(monkeypatch: pytest.MonkeyPatch):
    result, upsert, set_module = _run_checkout_event(monkeypatch, "checkout.session.expired")
    assert result["checkout_status"] == "CHECKOUT_EXPIRED"
    assert upsert.call_args.kwargs["status"] == "CHECKOUT_EXPIRED"
    set_module.assert_not_called()


def test_expired_checkout_restores_existing_account_state(monkeypatch: pytest.MonkeyPatch):
    result, upsert, _set_module = _run_checkout_event(
        monkeypatch, "checkout.session.expired", previous_status="ACTIVE"
    )
    assert result["checkout_status"] == "CHECKOUT_EXPIRED"
    assert upsert.call_args.kwargs["status"] == "ACTIVE"
    assert upsert.call_args.kwargs["metadata"]["last_checkout"]["last_checkout_event"] == "checkout.session.expired"


def test_async_failure_restores_existing_account_state(monkeypatch: pytest.MonkeyPatch):
    result, upsert, _set_module = _run_checkout_event(
        monkeypatch, "checkout.session.async_payment_failed", previous_status="PAST_DUE"
    )
    assert result["checkout_status"] == "CHECKOUT_FAILED"
    assert upsert.call_args.kwargs["status"] == "PAST_DUE"


def test_checkout_completion_uses_immutable_portal_snapshot(monkeypatch: pytest.MonkeyPatch):
    account = _pending_account()
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: account)
    lookup = MagicMock(side_effect=AssertionError("mutable catalogue must not be read"))
    monkeypatch.setattr(saas_worker, "_checkout_price", lookup)
    result = saas_worker._validate_pending_checkout(
        MagicMock(),
        tenant_id="amo-1",
        obj={"id": "cs-1"},
        metadata={
            "module_code": "quality",
            "module_price_id": "price-1",
            "external_price_ref": "price_stripe_1",
        },
    )
    assert result[2:] == ("quality", "price-1", "price_stripe_1")
    lookup.assert_not_called()


def test_subscription_event_preserves_pending_checkout(monkeypatch: pytest.MonkeyPatch):
    event = SimpleNamespace(
        payload=json.dumps({
            "id": "evt-sub",
            "type": "customer.subscription.updated",
            "data": {"object": {
                "id": "sub-existing",
                "status": "active",
                "customer": "cus-1",
                "metadata": {"tenant_id": "amo-1", "module_code": "training"},
            }},
        }),
        status=account_models.WebhookStatus.RECEIVED,
        processed_at=None,
        attempt_count=0,
        last_error=None,
    )
    account = _pending_account()
    db = MagicMock()
    db.get.return_value = event
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: account)
    upsert = MagicMock(return_value=account)
    monkeypatch.setattr(saas_worker, "_upsert_billing_account", upsert)
    monkeypatch.setattr(saas_worker, "_set_module_state", MagicMock())
    result = saas_worker._process_stripe_webhook(db, _webhook_job())
    assert result["checkout_pending_preserved"] is True
    assert upsert.call_args.kwargs["status"] == "CHECKOUT_PENDING"
    metadata = upsert.call_args.kwargs["metadata"]
    assert metadata["checkout_session_id"] == "cs-1"
    assert metadata["previous_account_status"] == "ACTIVE"


def test_invoice_event_preserves_pending_checkout(monkeypatch: pytest.MonkeyPatch):
    event = SimpleNamespace(
        payload=json.dumps({
            "id": "evt-invoice",
            "type": "invoice.paid",
            "data": {"object": {
                "id": "in-1",
                "customer": "cus-1",
                "subscription": "sub-existing",
                "metadata": {"tenant_id": "amo-1"},
            }},
        }),
        status=account_models.WebhookStatus.RECEIVED,
        processed_at=None,
        attempt_count=0,
        last_error=None,
    )
    account = _pending_account()
    db = MagicMock()
    db.get.return_value = event
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: account)
    upsert = MagicMock(return_value=account)
    monkeypatch.setattr(saas_worker, "_upsert_billing_account", upsert)
    result = saas_worker._process_stripe_webhook(db, _webhook_job())
    assert result["checkout_pending_preserved"] is True
    assert upsert.call_args.kwargs["status"] == "CHECKOUT_PENDING"
    assert upsert.call_args.kwargs["metadata"]["previous_account_status"] == "ACTIVE"


def test_worker_records_previous_account_snapshot(monkeypatch: pytest.MonkeyPatch):
    existing = SimpleNamespace(
        tenant_id="amo-1",
        provider="stripe",
        status="ACTIVE",
        external_customer_ref="cus-existing",
        external_subscription_ref="sub-existing",
        metadata_json={"stripe_status": "active"},
    )
    credential = SimpleNamespace(
        id="credential-1", provider="stripe", tenant_id="amo-1", status="HEALTHY",
        encrypted_secret="encrypted", config_json={},
    )
    price = SimpleNamespace(
        id="price-1", is_active=True, module_code="quality", external_price_ref="price_stripe_1"
    )
    job = SimpleNamespace(
        id="job-1", tenant_id="amo-1", idempotency_key="checkout-action-1",
        payload_json={
            "provider_credential_id": "credential-1", "module_price_id": "price-1",
            "module_code": "quality", "external_price_ref": "price_stripe_1",
            "tenant_email": "admin@example.test",
        },
    )
    db = MagicMock()
    monkeypatch.setattr(saas_worker, "_lock_checkout_tenant", lambda *_args, **_kwargs: SimpleNamespace(id="amo-1"))
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: existing)
    monkeypatch.setattr(saas_worker, "_credential", lambda *_args, **_kwargs: credential)
    monkeypatch.setattr(saas_worker, "_checkout_price", lambda *_args, **_kwargs: price)
    monkeypatch.setattr(saas_worker.saas_services, "provider_secrets", lambda *_args: {"secret_key": "sk_test"})
    monkeypatch.setattr(
        saas_worker.saas_providers,
        "create_stripe_checkout_session",
        lambda **_kwargs: {"session_id": "cs-new", "checkout_url": "https://checkout.stripe.test/cs-new"},
    )
    upsert = MagicMock(return_value=existing)
    monkeypatch.setattr(saas_worker, "_upsert_billing_account", upsert)
    saas_worker._process_checkout(db, job)
    metadata = upsert.call_args.kwargs["metadata"]
    assert metadata["previous_account_status"] == "ACTIVE"
    assert metadata["previous_account_metadata"] == {"stripe_status": "active"}


def test_module_price_patch_preserves_omitted_fields():
    row = SimpleNamespace(
        id="price-1", module_code="quality", plan_code="STANDARD", billing_term="MONTHLY",
        currency="USD", amount_cents=1000, tax_rate_bps=1600, trial_days=14,
        external_price_ref="price_stripe_1", is_active=False, updated_by=None,
        created_at=None, updated_at=None,
    )
    db = MagicMock()
    db.get.return_value = row
    duplicate = MagicMock()
    duplicate.filter.return_value = duplicate
    duplicate.first.return_value = None
    db.query.return_value = duplicate
    saas_services.upsert_module_price(
        db, price_id="price-1", payload={"amount_cents": 2000}, actor_user_id="admin-1"
    )
    assert row.amount_cents == 2000
    assert row.external_price_ref == "price_stripe_1"
    assert row.is_active is False


def test_module_price_patch_can_explicitly_clear_and_reactivate():
    row = SimpleNamespace(
        id="price-1", module_code="quality", plan_code="STANDARD", billing_term="MONTHLY",
        currency="USD", amount_cents=1000, tax_rate_bps=1600, trial_days=14,
        external_price_ref="price_stripe_1", is_active=False, updated_by=None,
        created_at=None, updated_at=None,
    )
    db = MagicMock()
    db.get.return_value = row
    duplicate = MagicMock()
    duplicate.filter.return_value = duplicate
    duplicate.first.return_value = None
    db.query.return_value = duplicate
    saas_services.upsert_module_price(
        db,
        price_id="price-1",
        payload={"external_price_ref": "", "is_active": True},
        actor_user_id="admin-1",
    )
    assert row.external_price_ref is None
    assert row.is_active is True


def test_matching_completed_checkout_job_is_returned_before_pending_rejection():
    tenant = SimpleNamespace(id="amo-1", contact_email="admin@example.test")
    existing_job = SimpleNamespace(
        id="job-complete", status="SUCCEEDED", idempotency_key="checkout-action-1"
    )
    tenant_query = MagicMock()
    tenant_query.filter.return_value.with_for_update.return_value.first.return_value = tenant
    job_query = MagicMock()
    job_query.filter.return_value.first.return_value = existing_job
    db = MagicMock()
    db.query.side_effect = [tenant_query, job_query]
    result = saas_services.enqueue_checkout(
        db,
        tenant_id="amo-1",
        module_price_id="price-1",
        actor_user_id="admin-1",
        idempotency_key="checkout-action-1",
    )
    assert result is existing_job
    db.get.assert_not_called()


def test_checkout_rejects_blank_idempotency_key():
    with pytest.raises(ValueError, match="idempotency_key is required"):
        saas_services.enqueue_checkout(
            MagicMock(),
            tenant_id="amo-1",
            module_price_id="price-1",
            actor_user_id="admin-1",
            idempotency_key="   ",
        )


def test_expired_checkout_is_tenant_mutating():
    assert "checkout.session.expired" in saas_worker.TENANT_MUTATING_STRIPE_EVENTS



def test_checkout_session_id_is_not_stored_as_subscription_reference(monkeypatch: pytest.MonkeyPatch):
    event = _checkout_event("checkout.session.expired")
    payload = json.loads(event.payload)
    payload["data"]["object"].pop("subscription", None)
    event.payload = json.dumps(payload)
    account = _pending_account(previous_status="ACTIVE")
    db = MagicMock()
    db.get.return_value = event
    monkeypatch.setattr(
        saas_worker,
        "_validate_pending_checkout",
        lambda *_args, **_kwargs: (account, dict(account.metadata_json), "quality", "price-1", "price_stripe_1"),
    )
    upsert = MagicMock(return_value=account)
    monkeypatch.setattr(saas_worker, "_upsert_billing_account", upsert)
    monkeypatch.setattr(saas_worker, "_set_module_state", MagicMock())
    saas_worker._process_stripe_webhook(db, _webhook_job())
    assert upsert.call_args.kwargs["subscription_ref"] is None


def test_idempotency_key_reuse_with_different_price_is_rejected():
    tenant = SimpleNamespace(id="amo-1", contact_email="admin@example.test")
    existing_job = SimpleNamespace(
        id="job-complete",
        status="SUCCEEDED",
        idempotency_key="checkout-action-1",
        payload_json={"module_price_id": "price-old"},
    )
    tenant_query = MagicMock()
    tenant_query.filter.return_value.with_for_update.return_value.first.return_value = tenant
    job_query = MagicMock()
    job_query.filter.return_value.first.return_value = existing_job
    db = MagicMock()
    db.query.side_effect = [tenant_query, job_query]
    with pytest.raises(ValueError, match="different checkout request"):
        saas_services.enqueue_checkout(
            db,
            tenant_id="amo-1",
            module_price_id="price-new",
            actor_user_id="admin-1",
            idempotency_key="checkout-action-1",
        )
