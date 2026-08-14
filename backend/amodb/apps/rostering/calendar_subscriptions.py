from __future__ import annotations

import hashlib
import secrets
from typing import Optional

from sqlalchemy.orm import Session

from ..platform.saas_secrets import decrypt_secret, encrypt_secret
from . import common
from .roster_control_models import RosterCalendarSubscription


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _encrypt_token(raw_token: str) -> str:
    encrypted, _fingerprint = encrypt_secret({"token": raw_token})
    if not encrypted:
        raise RuntimeError("Calendar subscription token encryption failed")
    return encrypted


def raw_token(row: RosterCalendarSubscription) -> str:
    payload = decrypt_secret(row.token_encrypted)
    token = str(payload.get("token") or "")
    if not token or _token_hash(token) != row.token_hash:
        raise RuntimeError("Stored calendar subscription token failed integrity validation")
    return token


def subscription_status(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
) -> Optional[RosterCalendarSubscription]:
    return db.query(RosterCalendarSubscription).filter(
        RosterCalendarSubscription.amo_id == amo_id,
        RosterCalendarSubscription.user_id == user_id,
    ).first()


def issue_calendar_subscription(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    actor_user_id: str,
) -> tuple[RosterCalendarSubscription, str]:
    raw = secrets.token_urlsafe(32)
    hashed = _token_hash(raw)
    encrypted = _encrypt_token(raw)
    row = subscription_status(db, amo_id=amo_id, user_id=user_id)
    now = common.utcnow()
    action = "create"
    if row:
        action = "rotate" if row.revoked_at is None else "reactivate"
        row.token_hash = hashed
        row.token_encrypted = encrypted
        row.rotated_at = now
        row.revoked_at = None
    else:
        row = RosterCalendarSubscription(
            amo_id=amo_id,
            user_id=user_id,
            token_hash=hashed,
            token_encrypted=encrypted,
            created_by_user_id=actor_user_id,
        )
        db.add(row)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterCalendarSubscription",
        entity_id=row.id,
        action=action,
        after={"user_id": user_id, "active": True},
        critical=True,
    )
    return row, raw


def get_or_issue_active_subscription(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    actor_user_id: str,
) -> tuple[RosterCalendarSubscription, str]:
    row = subscription_status(db, amo_id=amo_id, user_id=user_id)
    if row and row.revoked_at is None:
        return row, raw_token(row)
    return issue_calendar_subscription(
        db,
        amo_id=amo_id,
        user_id=user_id,
        actor_user_id=actor_user_id,
    )


def revoke_calendar_subscription(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    actor_user_id: str,
) -> Optional[RosterCalendarSubscription]:
    row = subscription_status(db, amo_id=amo_id, user_id=user_id)
    if not row:
        return None
    if row.revoked_at is None:
        row.revoked_at = common.utcnow()
        db.add(row)
        db.flush()
        common.audit(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            entity_type="RosterCalendarSubscription",
            entity_id=row.id,
            action="revoke",
            after={"user_id": user_id, "active": False},
            critical=True,
        )
    return row


def resolve_calendar_subscription(
    db: Session,
    *,
    raw_token: str,
) -> Optional[RosterCalendarSubscription]:
    row = db.query(RosterCalendarSubscription).filter(
        RosterCalendarSubscription.token_hash == _token_hash(raw_token),
        RosterCalendarSubscription.revoked_at.is_(None),
    ).first()
    if row:
        # A matching hash is sufficient for feed lookup. The encrypted copy is
        # used only to re-display the owner's stable subscription URL.
        row.last_used_at = common.utcnow()
        db.add(row)
        db.flush()
    return row
