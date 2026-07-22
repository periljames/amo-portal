from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import models, realtime_auth

GATEWAY_SHARED_SUBSCRIPTION = "$share/amo-portal-gateway/amo/+/user/+/outbox"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _secret(name: str) -> str:
    return (os.getenv(name) or "").strip()


def realtime_enabled() -> bool:
    raw = _secret("REALTIME_ENABLED")
    return raw.lower() in {"1", "true", "yes", "on"} if raw else True


def validate_production_config() -> None:
    if not realtime_enabled() or _secret("APP_ENV").lower() not in {"production", "prod"}:
        return
    public_url = _secret("MQTT_BROKER_WS_URL")
    internal_url = _secret("MQTT_BROKER_INTERNAL_URL")
    webhook_secret = _secret("REALTIME_BROKER_WEBHOOK_SECRET")
    gateway_username = _secret("REALTIME_GATEWAY_USERNAME")
    gateway_password = _secret("REALTIME_GATEWAY_PASSWORD")
    errors: list[str] = []
    if not public_url.startswith("wss://"):
        errors.append("MQTT_BROKER_WS_URL must use wss:// in production")
    if not internal_url:
        errors.append("MQTT_BROKER_INTERNAL_URL is required when realtime is enabled")
    if len(webhook_secret) < 32:
        errors.append("REALTIME_BROKER_WEBHOOK_SECRET must contain at least 32 characters")
    if not gateway_username:
        errors.append("REALTIME_GATEWAY_USERNAME is required")
    if len(gateway_password) < 24:
        errors.append("REALTIME_GATEWAY_PASSWORD must contain at least 24 characters")
    if errors:
        raise RuntimeError("Invalid production realtime configuration: " + "; ".join(errors))


def require_broker_webhook_secret(provided: str | None) -> None:
    expected = _secret("REALTIME_BROKER_WEBHOOK_SECRET")
    if len(expected) < 32 or not provided or not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="Broker callback authentication failed")


def _client_session_id(client_id: str) -> str:
    prefix = "rt-"
    if not client_id.startswith(prefix) or len(client_id) <= len(prefix):
        raise HTTPException(status_code=401, detail="Realtime client identifier is invalid")
    return client_id[len(prefix):]


def _active_client_token(
    db: Session,
    *,
    client_id: str,
    username: str,
    now: datetime | None = None,
) -> models.RealtimeConnectToken:
    now = now or utcnow()
    session_id = _client_session_id(client_id)
    row = (
        db.query(models.RealtimeConnectToken)
        .filter(
            models.RealtimeConnectToken.session_id == session_id,
            models.RealtimeConnectToken.user_id == username,
            models.RealtimeConnectToken.expires_at > now,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=401, detail="Realtime client session is invalid or expired")
    return row


def authenticate_client(
    db: Session,
    *,
    username: str,
    password: str,
    client_id: str,
) -> dict[str, Any]:
    gateway_username = _secret("REALTIME_GATEWAY_USERNAME")
    gateway_password = _secret("REALTIME_GATEWAY_PASSWORD")
    if username == gateway_username and gateway_username:
        if not gateway_password or not hmac.compare_digest(gateway_password, password):
            raise HTTPException(status_code=401, detail="Gateway broker credentials are invalid")
        return {"result": "allow", "is_superuser": False, "client_type": "gateway"}

    token = _active_client_token(db, client_id=client_id, username=username)
    realtime_auth.validate_connect_token(
        db,
        raw_token=password,
        amo_id=str(token.amo_id),
        user_id=str(token.user_id),
    )
    return {
        "result": "allow",
        "is_superuser": False,
        "client_type": "user",
        "amo_id": str(token.amo_id),
        "user_id": str(token.user_id),
    }


def authorize_topic(
    db: Session,
    *,
    username: str,
    client_id: str,
    action: str,
    topic: str,
) -> dict[str, str]:
    normalized_action = action.strip().lower()
    gateway_username = _secret("REALTIME_GATEWAY_USERNAME")
    if username == gateway_username and gateway_username:
        allowed = (
            normalized_action in {"subscribe", "sub"}
            and topic == GATEWAY_SHARED_SUBSCRIPTION
        ) or (
            normalized_action in {"publish", "pub"}
            and topic.startswith("amo/")
            and topic.count("/") == 4
            and (topic.endswith("/inbox") or topic.endswith("/ack"))
        )
        return {"result": "allow" if allowed else "deny"}

    token = _active_client_token(db, client_id=client_id, username=username)
    base = f"amo/{token.amo_id}/user/{token.user_id}"
    if normalized_action in {"publish", "pub"}:
        allowed = topic == f"{base}/outbox"
    elif normalized_action in {"subscribe", "sub"}:
        allowed = topic in {f"{base}/inbox", f"{base}/ack"}
    else:
        allowed = False
    return {"result": "allow" if allowed else "deny"}
