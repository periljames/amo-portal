from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import saas_models, saas_services
from amodb.jobs import saas_worker


def _webhook_job(event_id: str = "event-1") -> SimpleNamespace:
    return SimpleNamespace(
        id="webhook-job",
        tenant_id="amo-1",
        payload_json={
            "webhook_event_id": event_id,
            "verified_tenant_id": "amo-1",
        },
    )


def _checkout_event(session_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        payload=json.dumps({
            "id": "evt-checkout",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": session_id,
                    "client_reference_id": "amo-1",
                    "payment_status": "paid",
                    "customer": "cus-1",
                    "subscription": "sub-1",
                    "metadata": {
                        "tenant_id": "amo-1",
                        "module_code": "quality",
                        "module_price_id": "price-row-1",
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


def _pending_checkout_account() -> SimpleNamespace:
    return SimpleNamespace(
        tenant_id="amo-1",
        provider="stripe",
        status="CHECKOUT_PENDING",
        metadata_json={
            "checkout_session_id": "cs_portal",
            "module_code": "quality",
            "module_price_id": "price-row-1",
            "external_price_ref": "price_stripe_1",
        },
    )


def test_checkout_completion_rejects_non_portal_session():
    event = _checkout_event("cs_external")
    account = _pending_checkout_account()
    db = MagicMock()
    db.get.return_value = event
    query = MagicMock()
    query.filter.return_value.first.return_value = account
    db.query.return_value = query

    with pytest.raises(ValueError, match="does not match the pending portal checkout"):
        saas_worker._process_stripe_webhook(db, _webhook_job())


def test_checkout_completion_accepts_matching_pending_session(monkeypatch: pytest.MonkeyPatch):
    event = _checkout_event("cs_portal")
    account = _pending_checkout_account()
    price = SimpleNamespace(id="price-row-1", module_code="quality", external_price_ref="price_stripe_1")
    db = MagicMock()

    def get(model, identifier):
        if model is account_models.WebhookEvent:
            return event
        if model is saas_models.SaaSModulePrice:
            return price
        raise AssertionError((model, identifier))

    db.get.side_effect = get
    query = MagicMock()
    query.filter.return_value.first.return_value = account
    db.query.return_value = query
    set_module_state = MagicMock()
    monkeypatch.setattr(saas_worker, "_set_module_state", set_module_state)
    monkeypatch.setattr(saas_worker, "_upsert_billing_account", lambda *args, **kwargs: account)

    result = saas_worker._process_stripe_webhook(db, _webhook_job())

    assert result["module_code"] == "quality"
    set_module_state.assert_called_once()
    assert event.status is account_models.WebhookStatus.PROCESSED


def test_tenant_health_check_marks_inherited_credential_non_mutating(monkeypatch: pytest.MonkeyPatch):
    platform_credential = SimpleNamespace(id="platform-smtp", provider="smtp", tenant_id=None, status="HEALTHY")

    def resolve(db, *, provider, tenant_id=None, allow_platform_fallback=True):
        if tenant_id and not allow_platform_fallback:
            return None
        return platform_credential

    captured: dict[str, object] = {}
    monkeypatch.setattr(saas_services, "get_provider_credential", resolve)
    monkeypatch.setattr(
        saas_services.saas_queue,
        "enqueue_job",
        lambda db, **kwargs: captured.update(kwargs) or SimpleNamespace(id="health-job"),
    )

    saas_services.enqueue_provider_health(
        MagicMock(), provider="smtp", tenant_id="amo-1", actor_user_id="admin-1"
    )

    assert captured["payload"]["mutate_credential_status"] is False
    assert captured["payload"]["credential_scope"] == "__platform__"


def test_disabled_provider_cannot_enqueue_health_check(monkeypatch: pytest.MonkeyPatch):
    disabled = SimpleNamespace(id="tenant-disabled", provider="stripe", tenant_id="amo-1", status="DISABLED")
    monkeypatch.setattr(saas_services, "get_provider_credential", lambda *args, **kwargs: disabled)
    enqueue = MagicMock()
    monkeypatch.setattr(saas_services.saas_queue, "enqueue_job", enqueue)

    with pytest.raises(ValueError, match="Disabled providers cannot be health checked"):
        saas_services.enqueue_provider_health(
            MagicMock(), provider="stripe", tenant_id="amo-1", actor_user_id="admin-1"
        )

    enqueue.assert_not_called()


def test_inherited_health_check_does_not_mutate_platform_row(monkeypatch: pytest.MonkeyPatch):
    credential = SimpleNamespace(
        id="platform-smtp",
        provider="smtp",
        tenant_id=None,
        status="CONFIGURED",
        encrypted_secret="encrypted",
        config_json={},
        last_checked_at=None,
        last_latency_ms=None,
        last_health_detail=None,
    )
    job = SimpleNamespace(
        tenant_id="amo-1",
        payload_json={"credential_id": credential.id, "mutate_credential_status": False},
    )
    db = MagicMock()
    db.get.return_value = credential
    monkeypatch.setattr(saas_worker.saas_services, "provider_secrets", lambda row: {"password": "secret"})
    monkeypatch.setattr(saas_worker.saas_providers, "check_provider", lambda *args, **kwargs: {"ok": True, "latency_ms": 5})

    result = saas_worker._process_provider_health(db, job)

    assert result["ok"] is True
    assert credential.status == "CONFIGURED"
    assert credential.last_checked_at is None
    db.flush.assert_not_called()


def test_disabled_provider_is_not_revived_by_queued_health_job(monkeypatch: pytest.MonkeyPatch):
    credential = SimpleNamespace(
        id="tenant-stripe", provider="stripe", tenant_id="amo-1", status="DISABLED"
    )
    job = SimpleNamespace(tenant_id="amo-1", payload_json={"credential_id": credential.id})
    db = MagicMock()
    db.get.return_value = credential
    check = MagicMock()
    monkeypatch.setattr(saas_worker.saas_providers, "check_provider", check)

    with pytest.raises(ValueError, match="Disabled providers cannot be health checked"):
        saas_worker._process_provider_health(db, job)

    check.assert_not_called()
    assert credential.status == "DISABLED"


def test_checkout_worker_rechecks_current_stripe_status(monkeypatch: pytest.MonkeyPatch):
    credential = SimpleNamespace(
        id="tenant-stripe",
        provider="stripe",
        tenant_id="amo-1",
        status="DISABLED",
        encrypted_secret="encrypted",
        config_json={},
    )
    job = SimpleNamespace(
        tenant_id="amo-1",
        idempotency_key="checkout-1",
        payload_json={
            "provider_credential_id": credential.id,
            "module_price_id": "price-row-1",
            "module_code": "quality",
            "external_price_ref": "price_stripe_1",
        },
    )
    db = MagicMock()
    db.get.return_value = credential
    create_session = MagicMock()
    monkeypatch.setattr(saas_worker.saas_providers, "create_stripe_checkout_session", create_session)

    with pytest.raises(ValueError, match="Stripe provider is disabled or not operational"):
        saas_worker._process_checkout(db, job)

    create_session.assert_not_called()
