from __future__ import annotations

import asyncio
import hmac
import json
import hashlib

import pytest
from starlette.requests import Request
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from amodb.database import Base
from amodb.apps.accounts import models as account_models
from amodb.apps.integrations import models as integration_models
from amodb.apps.integrations import router as integrations_router


def _signature(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _setup_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            account_models.AMO.__table__,
            account_models.IdempotencyKey.__table__,
            integration_models.IntegrationConfig.__table__,
            integration_models.IntegrationInboundEvent.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return SessionLocal


def _build_request(body: bytes):
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/integrations/webhook/ingest",
        "headers": [],
        "client": ("127.0.0.1", 1234),
    }
    return Request(scope, receive)


def test_inbound_ingest_signature_and_idempotency():
    SessionLocal = _setup_db()

    db = SessionLocal()
    amo = account_models.AMO(
        amo_code="AMO-INB",
        name="Inbound AMO",
        login_slug="inbound",
    )
    db.add(amo)
    db.commit()

    secret = "super-secret"
    config = integration_models.IntegrationConfig(
        amo_id=amo.id,
        integration_key="webhook",
        display_name="Webhook",
        signing_secret=secret,
        enabled=True,
        status=integration_models.IntegrationConfigStatus.ACTIVE,
    )
    db.add(config)
    db.commit()
    db.close()

    body = {"event_type": "asset.created", "payload": {"id": "A1"}}
    raw = json.dumps(body).encode("utf-8")
    sig = _signature(secret, raw)

    request = _build_request(raw)
    db = SessionLocal()
    event = asyncio.run(
        integrations_router.ingest_event(
            integration_key="webhook",
            payload=integrations_router.schemas.IntegrationInboundIngest(**body),
            request=request,
            db=db,
            idempotency_key="idem-123",
            signature=sig,
            amo_id=amo.id,
        )
    )
    assert event.signature_valid is True

    duplicate_request = _build_request(raw)
    duplicate = asyncio.run(
        integrations_router.ingest_event(
            integration_key="webhook",
            payload=integrations_router.schemas.IntegrationInboundIngest(**body),
            request=duplicate_request,
            db=db,
            idempotency_key="idem-123",
            signature=sig,
            amo_id=amo.id,
        )
    )
    assert duplicate.id == event.id

    bad_request = _build_request(raw)
    with pytest.raises(HTTPException):
        asyncio.run(
            integrations_router.ingest_event(
                integration_key="webhook",
                payload=integrations_router.schemas.IntegrationInboundIngest(**body),
                request=bad_request,
                db=db,
                idempotency_key="idem-456",
                signature="bad",
                amo_id=amo.id,
            )
        )
    db.close()
