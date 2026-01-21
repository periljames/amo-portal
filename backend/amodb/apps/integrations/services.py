from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from amodb.apps.accounts import services as account_services

from . import models
from .schemas import IntegrationConfigCreate


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_payload(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sign_payload(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _normalize_signature(signature: str) -> str:
    if "=" in signature:
        _, value = signature.split("=", 1)
        return value.strip()
    return signature.strip()


def _get_config_by_key(db: Session, *, amo_id: str, integration_key: str) -> Optional[models.IntegrationConfig]:
    return (
        db.query(models.IntegrationConfig)
        .filter(
            models.IntegrationConfig.amo_id == amo_id,
            models.IntegrationConfig.integration_key == integration_key,
        )
        .first()
    )


def _get_config_by_id(db: Session, *, integration_id: str) -> Optional[models.IntegrationConfig]:
    return (
        db.query(models.IntegrationConfig)
        .filter(models.IntegrationConfig.id == integration_id)
        .first()
    )


def _ensure_config_active(config: models.IntegrationConfig, *, amo_id: str) -> None:
    if config.amo_id != amo_id:
        raise ValueError("Integration config does not belong to the AMO.")
    if not config.enabled or config.status != models.IntegrationConfigStatus.ACTIVE:
        raise ValueError("Integration config is not active.")


def list_integration_configs(db: Session, *, amo_id: str) -> list[models.IntegrationConfig]:
    return (
        db.query(models.IntegrationConfig)
        .filter(models.IntegrationConfig.amo_id == amo_id)
        .order_by(models.IntegrationConfig.created_at.desc())
        .all()
    )


def create_integration_config(
    db: Session,
    *,
    amo_id: str,
    data: IntegrationConfigCreate,
    created_by_user_id: Optional[str],
    idempotency_key: Optional[str] = None,
) -> models.IntegrationConfig:
    payload = data.model_dump()

    if idempotency_key:
        account_services.register_idempotency_key(
            db,
            scope=f"integration_config:{amo_id}",
            key=idempotency_key,
            payload=payload,
            commit=False,
        )

    existing = (
        db.query(models.IntegrationConfig)
        .filter(
            models.IntegrationConfig.amo_id == amo_id,
            models.IntegrationConfig.integration_key == data.integration_key,
        )
        .first()
    )
    if existing:
        return existing

    config = models.IntegrationConfig(
        amo_id=amo_id,
        integration_key=data.integration_key,
        display_name=data.display_name,
        status=data.status,
        enabled=data.enabled,
        base_url=data.base_url,
        signing_secret=data.signing_secret,
        allowed_ips=data.allowed_ips,
        credentials_json=data.credentials_json,
        metadata_json=data.metadata_json,
        created_by_user_id=created_by_user_id,
        updated_by_user_id=created_by_user_id,
    )
    db.add(config)
    db.flush()
    return config


def enqueue_outbound_event(
    db: Session,
    *,
    amo_id: str,
    integration_id: str,
    event_type: str,
    payload_json: Dict[str, Any],
    idempotency_key: Optional[str] = None,
    created_by_user_id: Optional[str] = None,
    next_attempt_at: Optional[datetime] = None,
) -> models.IntegrationOutboundEvent:
    config = _get_config_by_id(db, integration_id=integration_id)
    if not config:
        raise ValueError("Integration config not found.")
    _ensure_config_active(config, amo_id=amo_id)

    if idempotency_key:
        existing = (
            db.query(models.IntegrationOutboundEvent)
            .filter(
                models.IntegrationOutboundEvent.amo_id == amo_id,
                models.IntegrationOutboundEvent.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing:
            return existing

        account_services.register_idempotency_key(
            db,
            scope=f"integration_outbox:{amo_id}",
            key=idempotency_key,
            payload={
                "amo_id": amo_id,
                "integration_id": integration_id,
                "event_type": event_type,
                "payload_json": payload_json,
            },
            commit=False,
        )

    event = models.IntegrationOutboundEvent(
        amo_id=amo_id,
        integration_id=integration_id,
        event_type=event_type,
        payload_json=payload_json,
        status=models.IntegrationOutboundStatus.PENDING,
        attempt_count=0,
        next_attempt_at=next_attempt_at or _utcnow(),
        idempotency_key=idempotency_key,
        created_by_user_id=created_by_user_id,
    )
    db.add(event)
    db.flush()
    return event


def ingest_inbound_event(
    db: Session,
    *,
    amo_id: str,
    integration_key: str,
    event_type: str,
    payload_json: Dict[str, Any],
    idempotency_key: str,
    signature: str,
    source_ip: Optional[str],
    raw_body: Optional[bytes] = None,
    created_by_user_id: Optional[str] = None,
) -> models.IntegrationInboundEvent:
    config = _get_config_by_key(db, amo_id=amo_id, integration_key=integration_key)
    if not config:
        raise ValueError("Integration config not found.")
    _ensure_config_active(config, amo_id=amo_id)

    if not idempotency_key:
        raise ValueError("Idempotency key is required.")

    normalized_signature = _normalize_signature(signature)
    payload_bytes = raw_body or json.dumps(payload_json, sort_keys=True).encode("utf-8")
    payload_hash = _hash_payload(payload_bytes)

    signature_valid = False
    error: Optional[str] = None
    if config.signing_secret:
        expected = _sign_payload(payload_bytes, config.signing_secret)
        signature_valid = hmac.compare_digest(normalized_signature, expected)
    else:
        error = "Missing signing secret for integration."

    existing = (
        db.query(models.IntegrationInboundEvent)
        .filter(
            models.IntegrationInboundEvent.amo_id == amo_id,
            models.IntegrationInboundEvent.integration_id == config.id,
            models.IntegrationInboundEvent.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing:
        return existing

    account_services.register_idempotency_key(
        db,
        scope=f"integration_inbound:{amo_id}:{config.id}",
        key=idempotency_key,
        payload={
            "event_type": event_type,
            "payload_hash": payload_hash,
        },
        commit=False,
    )

    if not signature_valid and not error:
        error = "Invalid signature."

    inbound = models.IntegrationInboundEvent(
        amo_id=amo_id,
        integration_id=config.id,
        event_type=event_type,
        payload_json=payload_json,
        received_at=_utcnow(),
        idempotency_key=idempotency_key,
        signature_valid=signature_valid,
        source_ip=source_ip,
        payload_hash=payload_hash,
        error=error,
        created_by_user_id=created_by_user_id,
    )
    db.add(inbound)
    db.flush()
    return inbound
