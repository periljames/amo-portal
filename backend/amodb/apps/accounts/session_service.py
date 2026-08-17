from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session, joinedload

from . import models

SESSION_HOURS = max(2, int(os.getenv("PORTAL_AUTH_SESSION_HOURS", "12")))
ROTATION_GRACE_SECONDS = max(5, int(os.getenv("REFRESH_ROTATION_GRACE_SECONDS", "30")))
SESSION_RETENTION_DAYS = max(1, int(os.getenv("PORTAL_AUTH_SESSION_RETENTION_DAYS", "7")))


class RefreshRejected(Exception):
    pass


@dataclass(frozen=True)
class IssuedSession:
    session_id: str
    refresh_token: str
    expires_at: datetime


@dataclass(frozen=True)
class RotatedSession:
    session_id: str
    refresh_token: str
    expires_at: datetime
    user: models.User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _pepper() -> bytes:
    value = (
        os.getenv("REFRESH_TOKEN_PEPPER")
        or os.getenv("SECRET_KEY")
        or "CHANGE_ME_IN_PRODUCTION"
    )
    return value.encode("utf-8")


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _next_token(raw: str) -> str:
    digest = hmac.new(_pepper(), f"refresh-next:{raw}".encode("utf-8"), hashlib.sha384).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _user_agent_hash(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def create_session(
    db: Session,
    *,
    user: models.User,
    ip_address: str | None,
    user_agent: str | None,
) -> IssuedSession:
    now = _utcnow()
    expires_at = now + timedelta(hours=SESSION_HOURS)
    db.query(models.PortalAuthSession).filter(
        models.PortalAuthSession.user_id == str(user.id),
        models.PortalAuthSession.expires_at < now - timedelta(days=SESSION_RETENTION_DAYS),
    ).delete(synchronize_session=False)
    session_id = str(uuid4())
    family_id = str(uuid4())
    raw = secrets.token_urlsafe(48)
    db.add(
        models.PortalAuthSession(
            id=session_id,
            user_id=str(user.id),
            amo_id=None if bool(getattr(user, "is_superuser", False)) else user.amo_id,
            refresh_family_id=family_id,
            created_at=now,
            last_seen_at=now,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent_hash=_user_agent_hash(user_agent),
        )
    )
    db.add(
        models.RefreshSessionToken(
            session_id=session_id,
            family_id=family_id,
            token_hash=_hash_token(raw),
            status="ACTIVE",
            issued_at=now,
            expires_at=expires_at,
        )
    )
    db.commit()
    return IssuedSession(session_id=session_id, refresh_token=raw, expires_at=expires_at)


def rotate_session(db: Session, *, raw_token: str) -> RotatedSession:
    now = _utcnow()
    token_hash = _hash_token(raw_token)
    row = (
        db.query(models.RefreshSessionToken)
        .filter(models.RefreshSessionToken.token_hash == token_hash)
        .with_for_update()
        .first()
    )
    if row is None:
        raise RefreshRejected("Refresh session is not valid.")
    session = (
        db.query(models.PortalAuthSession)
        .filter(models.PortalAuthSession.id == row.session_id)
        .with_for_update()
        .first()
    )
    if session is None:
        raise RefreshRejected("Refresh session is not valid.")

    session_expiry = _aware(session.expires_at)
    token_expiry = _aware(row.expires_at)
    if session.revoked_at is not None or not session_expiry or session_expiry <= now:
        raise RefreshRejected("Refresh session has expired.")
    if row.revoked_at is not None or not token_expiry or token_expiry <= now:
        raise RefreshRejected("Refresh token has expired.")

    replacement_raw = _next_token(raw_token)
    replacement_hash = _hash_token(replacement_raw)
    if row.status == "ROTATED":
        rotated_at = _aware(row.rotated_at)
        replacement = (
            db.query(models.RefreshSessionToken)
            .filter(
                models.RefreshSessionToken.id == row.replaced_by_id,
                models.RefreshSessionToken.token_hash == replacement_hash,
                models.RefreshSessionToken.status == "ACTIVE",
            )
            .first()
        )
        if (
            replacement is not None
            and rotated_at is not None
            and (now - rotated_at).total_seconds() <= ROTATION_GRACE_SECONDS
        ):
            user = (
                db.query(models.User)
                .options(joinedload(models.User.amo), joinedload(models.User.department))
                .filter(models.User.id == session.user_id)
                .first()
            )
            if user is None or not user.is_active:
                raise RefreshRejected("Account is unavailable.")
            return RotatedSession(session.id, replacement_raw, session_expiry, user)

        session.revoked_at = now
        session.revoked_reason = "refresh_reuse"
        db.query(models.RefreshSessionToken).filter(
            models.RefreshSessionToken.session_id == session.id,
            models.RefreshSessionToken.revoked_at.is_(None),
        ).update(
            {"status": "REVOKED", "revoked_at": now},
            synchronize_session=False,
        )
        db.commit()
        raise RefreshRejected("Refresh-token reuse was detected; sign in again.")

    if row.status != "ACTIVE":
        raise RefreshRejected("Refresh session is not active.")

    replacement = models.RefreshSessionToken(
        session_id=session.id,
        family_id=row.family_id,
        parent_id=row.id,
        token_hash=replacement_hash,
        status="ACTIVE",
        issued_at=now,
        expires_at=session.expires_at,
    )
    db.add(replacement)
    db.flush()
    row.status = "ROTATED"
    row.last_used_at = now
    row.rotated_at = now
    row.replaced_by_id = replacement.id
    session.last_seen_at = now

    user = (
        db.query(models.User)
        .options(joinedload(models.User.amo), joinedload(models.User.department))
        .filter(models.User.id == session.user_id)
        .first()
    )
    if user is None or not user.is_active:
        session.revoked_at = now
        session.revoked_reason = "account_unavailable"
        db.commit()
        raise RefreshRejected("Account is unavailable.")
    db.commit()
    return RotatedSession(session.id, replacement_raw, session_expiry, user)


def revoke_session(
    db: Session,
    *,
    session_id: str,
    reason: str,
) -> datetime:
    now = _utcnow()
    row = db.get(models.PortalAuthSession, session_id)
    if row is not None and row.revoked_at is None:
        row.revoked_at = now
        row.revoked_reason = reason[:64]
        db.query(models.RefreshSessionToken).filter(
            models.RefreshSessionToken.session_id == session_id,
            models.RefreshSessionToken.revoked_at.is_(None),
        ).update(
            {"status": "REVOKED", "revoked_at": now},
            synchronize_session=False,
        )
    return now


def revoke_by_refresh_token(db: Session, *, raw_token: str, reason: str) -> None:
    row = db.query(models.RefreshSessionToken).filter(
        models.RefreshSessionToken.token_hash == _hash_token(raw_token)
    ).first()
    if row is not None:
        revoke_session(db, session_id=row.session_id, reason=reason)
