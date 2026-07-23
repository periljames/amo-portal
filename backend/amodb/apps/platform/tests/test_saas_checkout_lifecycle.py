from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import saas_models
from amodb.jobs import saas_worker


def _job() -> SimpleNamespace:
    return SimpleNamespace(
        id="job-1",
        tenant_id="amo-1",
        idempotency_key="checkout-action-1",
        payload_json={
            "provider_credential_id": "credential-1",
            "module_price_id": "price-1",
            "module_code": "quality",
            "external_price_ref": "price_stripe_1",
            "tenant_email": "admin@example.test",
        },
    )


def _credential(status: str = "HEALTHY") -> SimpleNamespace:
    return SimpleNamespace(
        id="credential-1",
        provider="stripe",
        tenant_id="amo-1",
        status=status,
        encrypted_secret="encrypted",
        config_json={},
    )


def _price(*, active: bool = True, module_code: str = "quality", price_ref: str = "price_stripe_1") -> SimpleNamespace:
    return SimpleNamespace(
        id="price-1",
        is_active=active,
        module_code=module_code,
        external_price_ref=price_ref,
    )


def _account(status: str = "CHECKOUT_PENDING") -> SimpleNamespace:
    return SimpleNamespace(
        tenant_id="amo-1",
        provider="stripe",
        status=status,
        external_customer_ref="cus-1",
        external_subscription_ref=None,
        metadata_json={
            "checkout_session_id": "cs-1",
            "checkout_url": "https://checkout.stripe.test/session",
            "checkout_job_id": "job-1",
            "checkout_idempotency_key": "checkout-action-1",
            "module_code": "quality",
            "module_price_id": "price-1",
            "external_price_ref": "price_stripe_1",
        },
    )


def test_worker_rejects_second_checkout_while_first_session_is_pending(monkeypatch: pytest.MonkeyPatch):
    job = _job()
    job.id = "job-2"
    job.idempotency_key = "checkout-action-2"
    pending = _account()
    db = MagicMock()
    monkeypatch.setattr(saas_worker, "_lock_checkout_tenant", lambda *_args, **_kwargs: SimpleNamespace(id="amo-1"))
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: pending)
    create_session = MagicMock()
    monkeypatch.setattr(saas_worker.saas_providers, "create_stripe_checkout_session", create_session)

    with pytest.raises(ValueError, match="already pending"):
        saas_worker._process_checkout(db, job)

    create_session.assert_not_called()


def test_worker_returns_existing_session_for_same_idempotent_checkout(monkeypatch: pytest.MonkeyPatch):
    pending = _account()
    monkeypatch.setattr(saas_worker, "_lock_checkout_tenant", lambda *_args, **_kwargs: SimpleNamespace(id="amo-1"))
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: pending)

    result = saas_worker._process_checkout(MagicMock(), _job())

    assert result["session_id"] == "cs-1"
    assert result["reused"] is True


@pytest.mark.parametrize(
    "price",
    [
        _price(active=False),
        _price(module_code="training"),
        _price(price_ref="price_changed"),
    ],
)
def test_worker_revalidates_module_price_before_stripe(monkeypatch: pytest.MonkeyPatch, price: SimpleNamespace):
    db = MagicMock()
    credential = _credential()
    monkeypatch.setattr(saas_worker, "_lock_checkout_tenant", lambda *_args, **_kwargs: SimpleNamespace(id="amo-1"))
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(saas_worker, "_credential", lambda *_args, **_kwargs: credential)
    monkeypatch.setattr(saas_worker, "_checkout_price", lambda *_args, **_kwargs: price)
    create_session = MagicMock()
    monkeypatch.setattr(saas_worker.saas_providers, "create_stripe_checkout_session", create_session)

    with pytest.raises(ValueError, match="no longer active"):
        saas_worker._process_checkout(db, _job())

    create_session.assert_not_called()


def _webhook_event(event_type: str, payment_status: str) -> SimpleNamespace:
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
                    "subscription": "sub-1",
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


def _webhook_job(event_id: str = "stored-event") -> SimpleNamespace:
    return SimpleNamespace(
        id="webhook-job",
        tenant_id="amo-1",
        payload_json={"webhook_event_id": event_id, "verified_tenant_id": "amo-1"},
    )


def _run_checkout_event(monkeypatch: pytest.MonkeyPatch, event_type: str, payment_status: str):
    event = _webhook_event(event_type, payment_status)
    account = _account()
    db = MagicMock()
    db.get.return_value = event
    monkeypatch.setattr(
        saas_worker,
        "_validate_pending_checkout",
        lambda *_args, **_kwargs: (account, dict(account.metadata_json), "quality", "price-1", "price_stripe_1"),
    )
    upsert = MagicMock(return_value=account)
    set_module = MagicMock()
    monkeypatch.setattr(saas_worker, "_upsert_billing_account", upsert)
    monkeypatch.setattr(saas_worker, "_set_module_state", set_module)
    result = saas_worker._process_stripe_webhook(db, _webhook_job())
    return result, upsert, set_module


def test_unpaid_completed_checkout_remains_pending(monkeypatch: pytest.MonkeyPatch):
    result, upsert, set_module = _run_checkout_event(
        monkeypatch, "checkout.session.completed", "unpaid"
    )

    assert result["checkout_status"] == "CHECKOUT_PENDING"
    assert upsert.call_args.kwargs["status"] == "CHECKOUT_PENDING"
    set_module.assert_not_called()


def test_async_payment_success_enables_module(monkeypatch: pytest.MonkeyPatch):
    result, upsert, set_module = _run_checkout_event(
        monkeypatch, "checkout.session.async_payment_succeeded", "paid"
    )

    assert result["checkout_status"] == "ACTIVE"
    assert upsert.call_args.kwargs["status"] == "ACTIVE"
    set_module.assert_called_once()


def test_async_payment_failure_releases_pending_checkout(monkeypatch: pytest.MonkeyPatch):
    result, upsert, set_module = _run_checkout_event(
        monkeypatch, "checkout.session.async_payment_failed", "unpaid"
    )

    assert result["checkout_status"] == "CHECKOUT_FAILED"
    assert upsert.call_args.kwargs["status"] == "CHECKOUT_FAILED"
    set_module.assert_not_called()
