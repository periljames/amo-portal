from __future__ import annotations

import json
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import saas_admin_policy, saas_services, saas_webhooks
from amodb.apps.realtime.gateway import RealtimeGateway
from amodb.apps.realtime.schemas import RealtimeEnvelope, RealtimeKind


tenant_saas_router = import_module("amodb.apps.platform.tenant_saas_router")


class _QueryRows:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class _SequentialDB:
    def __init__(self, *responses):
        self.responses = iter(responses)

    def query(self, *args, **kwargs):
        return _QueryRows(next(self.responses))


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


def _credential(
    credential_id: str,
    *,
    tenant_id: str | None,
    status: str = "HEALTHY",
    encrypted_secret: str | None = "encrypted",
):
    return SimpleNamespace(
        id=credential_id,
        tenant_id=tenant_id,
        status=status,
        encrypted_secret=encrypted_secret,
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


def test_enabled_tenant_override_requires_its_own_secret(monkeypatch: pytest.MonkeyPatch):
    platform = _credential("platform", tenant_id=None)

    def get_credential(db, *, provider, tenant_id, allow_platform_fallback):
        return platform if tenant_id is None else None

    monkeypatch.setattr(saas_admin_policy.saas_services, "get_provider_credential", get_credential)

    with pytest.raises(ValueError, match="Tenant-specific secret values"):
        saas_admin_policy.validate_tenant_provider_override(
            MagicMock(),
            provider="stripe",
            tenant_id="amo-1",
            payload={"enabled": True, "config": {"success_url": "https://portal.test/success"}},
        )

    saas_admin_policy.validate_tenant_provider_override(
        MagicMock(),
        provider="stripe",
        tenant_id="amo-1",
        payload={"enabled": True, "secret": {"webhook_secret": "tenant-secret"}},
    )


def test_disabling_inherited_provider_does_not_require_copying_secret(monkeypatch: pytest.MonkeyPatch):
    platform = _credential("platform", tenant_id=None)
    monkeypatch.setattr(
        saas_admin_policy.saas_services,
        "get_provider_credential",
        lambda db, *, provider, tenant_id, allow_platform_fallback: platform if tenant_id is None else None,
    )

    saas_admin_policy.validate_tenant_provider_override(
        MagicMock(),
        provider="stripe",
        tenant_id="amo-1",
        payload={"enabled": False, "reason": "Disable card billing for this tenant"},
    )


def test_enabled_tenant_provider_cannot_clear_existing_secret(monkeypatch: pytest.MonkeyPatch):
    tenant = _credential("tenant", tenant_id="amo-1")
    monkeypatch.setattr(
        saas_admin_policy.saas_services,
        "get_provider_credential",
        lambda db, *, provider, tenant_id, allow_platform_fallback: tenant if tenant_id else None,
    )

    with pytest.raises(ValueError, match="cannot clear"):
        saas_admin_policy.validate_tenant_provider_override(
            MagicMock(),
            provider="stripe",
            tenant_id="amo-1",
            payload={"enabled": True, "clear_secret": True, "secret": {}},
        )


def test_scoped_stripe_credential_excludes_platform_fallback():
    tenant = _credential("stripe-tenant", tenant_id="amo-1")
    platform = _credential("stripe-platform", tenant_id=None)
    payload = {
        "data": {
            "object": {
                "client_reference_id": "amo-1",
                "metadata": {"tenant_id": "amo-1"},
            }
        }
    }

    candidates = saas_webhooks._credential_candidates(
        _SequentialDB([tenant], [platform]),
        payload=payload,
    )

    assert candidates == [tenant]


def test_disabled_scoped_stripe_credential_blocks_platform_fallback():
    disabled = _credential("stripe-tenant", tenant_id="amo-1", status="DISABLED")
    payload = {
        "data": {
            "object": {
                "client_reference_id": "amo-1",
                "metadata": {"tenant_id": "amo-1"},
            }
        }
    }

    assert saas_webhooks._credential_candidates(_SequentialDB([disabled]), payload=payload) == []


def test_platform_stripe_secret_is_fallback_only_without_scoped_row():
    platform = _credential("stripe-platform", tenant_id=None)
    payload = {
        "data": {
            "object": {
                "client_reference_id": "amo-1",
                "metadata": {"tenant_id": "amo-1"},
            }
        }
    }

    candidates = saas_webhooks._credential_candidates(
        _SequentialDB([], [platform]),
        payload=payload,
    )

    assert candidates == [platform]


def test_stripe_webhook_uses_matching_tenant_secret(monkeypatch: pytest.MonkeyPatch):
    tenant_credential = _credential("stripe-tenant", tenant_id="amo-1", encrypted_secret="tenant-encrypted")
    monkeypatch.setattr(
        saas_webhooks,
        "_credential_candidates",
        lambda db, payload: [tenant_credential],
    )
    monkeypatch.setattr(
        saas_webhooks.saas_secrets,
        "decrypt_secret",
        lambda value: {"webhook_secret": "tenant-secret"},
    )
    checked: list[str] = []

    def verify(raw_payload, signature, secret):
        checked.append(secret)
        return secret == "tenant-secret"

    monkeypatch.setattr(saas_webhooks.saas_providers, "verify_stripe_signature", verify)
    captured: dict[str, object] = {}

    def enqueue(db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="job-1")

    monkeypatch.setattr(saas_webhooks.saas_queue, "enqueue_job", enqueue)
    query = MagicMock()
    query.filter.return_value.first.return_value = None
    db = MagicMock()
    db.query.return_value = query

    def add(row):
        if isinstance(row, account_models.WebhookEvent):
            row.id = "stored-event"

    db.add.side_effect = add
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


def test_platform_package_installs_scoped_stripe_verifier_and_override_policy():
    assert saas_services.record_stripe_webhook is saas_webhooks.record_stripe_webhook
    assert saas_admin_policy._INSTALLED is True
    assert saas_services.upsert_provider_credential.__name__ == "guarded_upsert_provider_credential"


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
