from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import saas_services, saas_webhooks
from amodb.apps.platform import tenant_saas_router
from amodb.apps.realtime.gateway import RealtimeGateway
from amodb.apps.realtime.schemas import RealtimeEnvelope, RealtimeKind


def _tenant_admin(amo_id: str = "amo-1"):
    return SimpleNamespace(
        id="admin-1",
        amo_id=amo_id,
        role=account_models.AccountRole.AMO_ADMIN,
        is_amo_admin=True,
        is_superuser=False,
        is_system_account=False,
    )


def _superuser():
    return SimpleNamespace(
        id="root-1",
        amo_id=None,
        role=account_models.AccountRole.SUPERUSER,
        is_amo_admin=False,
        is_superuser=True,
        is_system_account=False,
    )


def test_tenant_admin_is_forced_to_own_scope():
    admin = _tenant_admin()
    assert tenant_saas_router._tenant_scope(admin, None) == "amo-1"
    assert tenant_saas_router._tenant_scope(admin, "amo-1") == "amo-1"
    with pytest.raises(HTTPException) as error:
        tenant_saas_router._tenant_scope(admin, "amo-2")
    assert error.value.status_code == 403


def test_superuser_can_choose_platform_or_tenant_scope():
    root = _superuser()
    assert tenant_saas_router._tenant_scope(root, None) is None
    assert tenant_saas_router._tenant_scope(root, "amo-2") == "amo-2"


def test_deployment_readiness_never_returns_secret_values(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_SECRETS_KEY", "do-not-return-this-value")
    rows = tenant_saas_router._deployment_readiness()
    row = next(item for item in rows if item["key"] == "PLATFORM_SECRETS_KEY")
    assert row["configured"] is True
    assert row["managed_in_frontend"] is False
    assert "do-not-return-this-value" not in json.dumps(rows)


def test_stripe_webhook_uses_matching_tenant_secret(monkeypatch: pytest.MonkeyPatch):
    tenant_credential = SimpleNamespace(
        id="stripe-tenant",
        tenant_id="amo-1",
        encrypted_secret="tenant-encrypted",
    )
    platform_credential = SimpleNamespace(
        id="stripe-platform",
        tenant_id=None,
        encrypted_secret="platform-encrypted",
    )
    monkeypatch.setattr(
        saas_webhooks,
        "_credential_candidates",
        lambda db, payload: [tenant_credential, platform_credential],
    )
    monkeypatch.setattr(
        saas_webhooks.saas_secrets,
        "decrypt_secret",
        lambda value: {
            "webhook_secret": "tenant-secret" if value == "tenant-encrypted" else "platform-secret"
        },
    )
    checked: list[str] = []

    def verify(raw_payload, signature, secret):
        checked.append(secret)
        return secret == "tenant-secret"

    monkeypatch.setattr(saas_webhooks.saas_providers, "verify_stripe_signature", verify)
    event = SimpleNamespace(id="stored-event")
    monkeypatch.setattr(
        saas_webhooks.account_models,
        "WebhookEvent",
        lambda **kwargs: event,
    )
    captured: dict[str, object] = {}

    def enqueue(db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="job-1")

    monkeypatch.setattr(saas_webhooks.saas_queue, "enqueue_job", enqueue)
    query = MagicMock()
    query.filter.return_value.first.return_value = None
    db = MagicMock()
    db.query.return_value = query
    raw = json.dumps({
        "id": "evt_tenant",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "amo-1",
                "metadata": {"tenant_id": "amo-1", "module_code": "quality"},
            }
        },
    }).encode()

    result = saas_webhooks.record_stripe_webhook(db, raw_payload=raw, signature="valid")

    assert result.id == "job-1"
    assert checked == ["tenant-secret"]
    assert captured["tenant_id"] == "amo-1"
    assert captured["payload"] == {
        "webhook_event_id": "stored-event",
        "verified_credential_id": "stripe-tenant",
        "verified_tenant_id": "amo-1",
    }


def test_platform_package_installs_scoped_stripe_verifier():
    assert saas_services.record_stripe_webhook is saas_webhooks.record_stripe_webhook


def test_gateway_waits_for_qos_acknowledgement(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REALTIME_PUBLISH_ACK_TIMEOUT_SEC", "2")
    info = MagicMock()
    info.rc = 0
    info.is_published.return_value = True
    client = MagicMock()
    client.publish.return_value = info
    gateway = RealtimeGateway()
    gateway.enabled = True
    gateway._connected = True
    gateway._client = client
    envelope = RealtimeEnvelope(
        v=1,
        id="event-1",
        ts=1,
        amoId="amo-1",
        userId="user-1",
        kind=RealtimeKind.CHAT_MESSAGE,
        payload={"message_id": "message-1"},
    )

    gateway.publish(topic="amo/amo-1/user/user-1/inbox", envelope=envelope, qos=1)

    info.wait_for_publish.assert_called_once_with(timeout=2.0)
    assert info.is_published.called


def test_gateway_rejects_missing_qos_acknowledgement(monkeypatch: pytest.MonkeyPatch):
    info = MagicMock()
    info.rc = 0
    info.is_published.return_value = False
    client = MagicMock()
    client.publish.return_value = info
    gateway = RealtimeGateway()
    gateway.enabled = True
    gateway._connected = True
    gateway._client = client
    envelope = RealtimeEnvelope(
        v=1,
        id="event-2",
        ts=1,
        amoId="amo-1",
        userId="user-1",
        kind=RealtimeKind.CHAT_MESSAGE,
        payload={},
    )

    with pytest.raises(TimeoutError, match="acknowledgement"):
        gateway.publish(topic="amo/amo-1/user/user-1/inbox", envelope=envelope, qos=1)
