from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from amodb.database import get_db

from . import broker_auth

router = APIRouter(prefix="/realtime/broker", tags=["realtime-broker-internal"])


@router.post("/authenticate", include_in_schema=False)
def broker_authenticate(
    payload: dict[str, Any],
    x_realtime_broker_secret: str | None = Header(default=None, alias="X-Realtime-Broker-Secret"),
    db: Session = Depends(get_db),
):
    broker_auth.require_broker_webhook_secret(x_realtime_broker_secret)
    return broker_auth.authenticate_client(
        db,
        username=str(payload.get("username") or ""),
        password=str(payload.get("password") or ""),
        client_id=str(payload.get("clientid") or payload.get("client_id") or ""),
    )


@router.post("/authorize", include_in_schema=False)
def broker_authorize(
    payload: dict[str, Any],
    x_realtime_broker_secret: str | None = Header(default=None, alias="X-Realtime-Broker-Secret"),
    db: Session = Depends(get_db),
):
    broker_auth.require_broker_webhook_secret(x_realtime_broker_secret)
    return broker_auth.authorize_topic(
        db,
        username=str(payload.get("username") or ""),
        client_id=str(payload.get("clientid") or payload.get("client_id") or ""),
        action=str(payload.get("action") or ""),
        topic=str(payload.get("topic") or ""),
    )
