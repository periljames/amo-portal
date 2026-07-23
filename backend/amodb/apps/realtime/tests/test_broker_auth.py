from __future__ import annotations

from datetime import timedelta

import pytest

from amodb.apps.accounts import models as account_models
from amodb.apps.realtime import broker_auth, models, realtime_auth


def _seed(db_session):
    amo = account_models.AMO(amo_code="BROKER", name="Broker AMO", login_slug="broker")
    db_session.add(amo)
    db_session.flush()
    user = account_models.User(
        amo_id=amo.id,
        staff_code="BROKER-1",
        email="broker-user@example.com",
        first_name="Broker",
        last_name="User",
        full_name="Broker User",
        role=account_models.AccountRole.TECHNICIAN,
        hashed_password="x",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    raw_token = "broker-user-connect-token-long-enough"
    token = models.RealtimeConnectToken(
        amo_id=amo.id,
        user_id=user.id,
        token_hash=realtime_auth.token_digest(raw_token),
        session_id="session-broker-auth",
        expires_at=broker_auth.utcnow() + timedelta(minutes=5),
    )
    db_session.add(token)
    db_session.commit()
    return amo, user, token, raw_token


def _configure(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REALTIME_BROKER_WEBHOOK_SECRET", "broker-webhook-secret-with-more-than-32-characters")
    monkeypatch.setenv("REALTIME_GATEWAY_USERNAME", "amo-gateway")
    monkeypatch.setenv("REALTIME_GATEWAY_PASSWORD", "gateway-password-with-more-than-24-characters")


def test_user_broker_auth_and_acl_are_exact(db_session, monkeypatch: pytest.MonkeyPatch):
    _configure(monkeypatch)
    amo, user, token, raw_token = _seed(db_session)
    client_id = f"rt-{token.session_id}"

    result = broker_auth.authenticate_client(
        db_session,
        username=user.id,
        password=raw_token,
        client_id=client_id,
    )
    assert result["result"] == "allow"

    base = f"amo/{amo.id}/user/{user.id}"
    assert broker_auth.authorize_topic(
        db_session,
        username=user.id,
        client_id=client_id,
        action="publish",
        topic=f"{base}/outbox",
    ) == {"result": "allow"}
    assert broker_auth.authorize_topic(
        db_session,
        username=user.id,
        client_id=client_id,
        action="subscribe",
        topic=f"{base}/inbox",
    ) == {"result": "allow"}
    assert broker_auth.authorize_topic(
        db_session,
        username=user.id,
        client_id=client_id,
        action="subscribe",
        topic=f"amo/{amo.id}/user/another-user/inbox",
    ) == {"result": "deny"}
    assert broker_auth.authorize_topic(
        db_session,
        username=user.id,
        client_id=client_id,
        action="subscribe",
        topic="#",
    ) == {"result": "deny"}


def test_gateway_is_limited_to_shared_inbound_and_recipient_outbound(db_session, monkeypatch: pytest.MonkeyPatch):
    _configure(monkeypatch)
    assert broker_auth.authenticate_client(
        db_session,
        username="amo-gateway",
        password="gateway-password-with-more-than-24-characters",
        client_id="gateway-instance-1",
    )["result"] == "allow"
    assert broker_auth.authorize_topic(
        db_session,
        username="amo-gateway",
        client_id="gateway-instance-1",
        action="subscribe",
        topic=broker_auth.GATEWAY_SHARED_SUBSCRIPTION,
    ) == {"result": "allow"}
    assert broker_auth.authorize_topic(
        db_session,
        username="amo-gateway",
        client_id="gateway-instance-1",
        action="subscribe",
        topic="#",
    ) == {"result": "deny"}
    assert broker_auth.authorize_topic(
        db_session,
        username="amo-gateway",
        client_id="gateway-instance-1",
        action="publish",
        topic="amo/tenant/user/person/inbox",
    ) == {"result": "allow"}


def test_production_realtime_requires_tls_and_secrets(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("REALTIME_ENABLED", "true")
    monkeypatch.setenv("MQTT_BROKER_INTERNAL_URL", "mqtt://broker:1883")
    monkeypatch.setenv("MQTT_BROKER_WS_URL", "ws://broker.example.test/mqtt")
    monkeypatch.delenv("REALTIME_BROKER_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("REALTIME_GATEWAY_USERNAME", raising=False)
    monkeypatch.delenv("REALTIME_GATEWAY_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="wss://"):
        broker_auth.validate_production_config()
