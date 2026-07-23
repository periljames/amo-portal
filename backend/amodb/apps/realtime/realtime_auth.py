from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import models


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def token_digest(raw_token: str) -> str:
    value = raw_token.strip()
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_connect_token(
    db: Session,
    *,
    raw_token: str | None,
    amo_id: str,
    user_id: str,
    now: datetime | None = None,
) -> models.RealtimeConnectToken:
    """Validate an MQTT envelope against the short-lived token issued by the API.

    Broker ACLs remain required in deployment, but backend authorization does not
    trust an MQTT topic or unsigned envelope identity on its own.
    """

    digest = token_digest(raw_token or "")
    if not digest:
        raise HTTPException(status_code=401, detail="Realtime envelope authentication is required")
    now = now or utcnow()
    candidates = (
        db.query(models.RealtimeConnectToken)
        .filter(
            models.RealtimeConnectToken.amo_id == str(amo_id),
            models.RealtimeConnectToken.user_id == str(user_id),
            models.RealtimeConnectToken.expires_at > now,
        )
        .order_by(models.RealtimeConnectToken.created_at.desc())
        .limit(8)
        .all()
    )
    token = next(
        (row for row in candidates if hmac.compare_digest(str(row.token_hash), digest)),
        None,
    )
    if token is None:
        raise HTTPException(status_code=401, detail="Realtime envelope token is invalid or expired")

    user = (
        db.query(account_models.User)
        .filter(
            account_models.User.id == str(user_id),
            account_models.User.amo_id == str(amo_id),
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .first()
    )
    if user is None:
        raise HTTPException(status_code=403, detail="Realtime user is no longer active in this AMO")
    return token


def prune_user_tokens(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    keep_latest: int = 3,
    now: datetime | None = None,
) -> int:
    """Remove expired and surplus connect tokens without invalidating active tabs."""

    now = now or utcnow()
    rows = (
        db.query(models.RealtimeConnectToken)
        .filter(
            models.RealtimeConnectToken.amo_id == str(amo_id),
            models.RealtimeConnectToken.user_id == str(user_id),
        )
        .order_by(models.RealtimeConnectToken.created_at.desc())
        .all()
    )
    retained = 0
    removed = 0
    for row in rows:
        should_remove = row.expires_at <= now or retained >= max(1, keep_latest)
        if should_remove:
            db.delete(row)
            removed += 1
        else:
            retained += 1
    if removed:
        db.commit()
    return removed
