from __future__ import annotations

import os
import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import models, schemas
from .services import effective_amo_id

MIN_PRESENCE_WRITE_INTERVAL_SECONDS = max(
    5,
    int(os.getenv("PRESENCE_MIN_WRITE_INTERVAL_SECONDS", "12")),
)
PRESENCE_HEARTBEAT_GRACE_SECONDS = max(
    MIN_PRESENCE_WRITE_INTERVAL_SECONDS * 2,
    int(os.getenv("PRESENCE_HEARTBEAT_GRACE_SECONDS", "90")),
)
PRESENCE_SESSION_RETENTION_HOURS = max(
    1,
    int(os.getenv("PRESENCE_SESSION_RETENTION_HOURS", "24")),
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _session_id(user: account_models.User, client_instance_id: str | None = None) -> str:
    auth_session = str(
        getattr(user, "auth_session_id", None)
        or getattr(user, "_auth_session_id", None)
        or ""
    ).strip()
    if not auth_session:
        auth_session = f"legacy:{str(user.id)}"
    client = str(client_instance_id or "default").strip()
    # Never trust or store a browser-provided identifier verbatim. The digest
    # binds the tab/device lease to the authenticated server session.
    return hashlib.sha256(f"{auth_session}:{client}".encode("utf-8")).hexdigest()


def _dialect_name(db: Session) -> str:
    dialect = getattr(getattr(db, "bind", None), "dialect", None)
    return str(getattr(dialect, "name", ""))


def _upsert_session(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    session_id: str,
    state: models.PresenceKind,
    now: datetime,
) -> None:
    values = {
        "amo_id": amo_id,
        "user_id": user_id,
        "session_id": session_id,
        "state": state,
        "last_seen_at": now,
        "updated_at": now,
    }
    if _dialect_name(db) == "postgresql":
        statement = pg_insert(models.PresenceSession).values(**values)
        statement = statement.on_conflict_do_update(
            constraint="uq_presence_sessions_amo_user_session",
            set_={
                "state": statement.excluded.state,
                "last_seen_at": statement.excluded.last_seen_at,
                "updated_at": statement.excluded.updated_at,
            },
        )
        db.execute(statement)
        return

    row = db.execute(
        select(models.PresenceSession).where(
            models.PresenceSession.amo_id == amo_id,
            models.PresenceSession.user_id == user_id,
            models.PresenceSession.session_id == session_id,
        )
    ).scalar_one_or_none()
    if row is None:
        db.add(models.PresenceSession(**values))
    else:
        row.state = state
        row.last_seen_at = now
        row.updated_at = now


def _aggregate_state(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    now: datetime,
) -> tuple[models.PresenceKind, datetime]:
    cutoff = now - timedelta(seconds=PRESENCE_HEARTBEAT_GRACE_SECONDS)
    rows = db.execute(
        select(models.PresenceSession.state, models.PresenceSession.last_seen_at)
        .where(
            models.PresenceSession.amo_id == amo_id,
            models.PresenceSession.user_id == user_id,
            models.PresenceSession.last_seen_at >= cutoff,
        )
        .order_by(models.PresenceSession.last_seen_at.desc())
    ).all()
    if not rows:
        return models.PresenceKind.OFFLINE, now
    latest = max((_aware(row.last_seen_at) or now for row in rows), default=now)
    if any(row.state == models.PresenceKind.ONLINE for row in rows):
        return models.PresenceKind.ONLINE, latest
    return models.PresenceKind.AWAY, latest


def _upsert_projection(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    state: models.PresenceKind,
    last_seen_at: datetime,
    session_id: str,
    now: datetime,
) -> None:
    values = {
        "amo_id": amo_id,
        "user_id": user_id,
        "state": state,
        "last_seen_at": last_seen_at,
        "session_id": session_id,
        "updated_at": now,
    }
    if _dialect_name(db) == "postgresql":
        statement = pg_insert(models.PresenceState).values(**values)
        statement = statement.on_conflict_do_update(
            constraint="uq_presence_state_amo_user",
            set_={
                "state": statement.excluded.state,
                "last_seen_at": statement.excluded.last_seen_at,
                "session_id": statement.excluded.session_id,
                "updated_at": statement.excluded.updated_at,
            },
        )
        db.execute(statement)
        return

    row = db.execute(
        select(models.PresenceState).where(
            models.PresenceState.amo_id == amo_id,
            models.PresenceState.user_id == user_id,
        )
    ).scalar_one_or_none()
    if row is None:
        db.add(models.PresenceState(**values))
    else:
        row.state = state
        row.last_seen_at = last_seen_at
        row.session_id = session_id
        row.updated_at = now


def update_presence_state(
    db: Session,
    *,
    user: account_models.User,
    payload: schemas.PresenceStateUpdateRequest,
) -> schemas.PresenceStateRead:
    """Renew this auth session's lease and update the user-level projection."""
    amo_id = effective_amo_id(user)
    user_id = str(user.id)
    now = _utcnow()
    session_id = _session_id(user, payload.client_instance_id)
    target_state = models.PresenceKind(payload.state)
    if not amo_id:
        return schemas.PresenceStateRead(
            user_id=user_id,
            amo_id="platform",
            state=target_state.value,
            last_seen_at=now,
            updated_at=now,
            reason=payload.reason,
            session_id=session_id,
        )

    current = db.execute(
        select(models.PresenceSession.state, models.PresenceSession.last_seen_at).where(
            models.PresenceSession.amo_id == amo_id,
            models.PresenceSession.user_id == user_id,
            models.PresenceSession.session_id == session_id,
        )
    ).first()
    last_seen = _aware(current.last_seen_at) if current else None
    elapsed = (now - last_seen).total_seconds() if last_seen else None
    should_write = not (
        current
        and current.state == target_state
        and elapsed is not None
        and elapsed < MIN_PRESENCE_WRITE_INTERVAL_SECONDS
    )

    if should_write:
        _upsert_session(
            db,
            amo_id=amo_id,
            user_id=user_id,
            session_id=session_id,
            state=target_state,
            now=now,
        )
        db.flush()
        aggregate_state, aggregate_seen = _aggregate_state(
            db,
            amo_id=amo_id,
            user_id=user_id,
            now=now,
        )
        _upsert_projection(
            db,
            amo_id=amo_id,
            user_id=user_id,
            state=aggregate_state,
            last_seen_at=aggregate_seen,
            session_id=session_id,
            now=now,
        )
        db.execute(
            delete(models.PresenceSession).where(
                models.PresenceSession.amo_id == amo_id,
                models.PresenceSession.user_id == user_id,
                models.PresenceSession.last_seen_at
                < now - timedelta(hours=PRESENCE_SESSION_RETENTION_HOURS),
            )
        )
        db.commit()
    else:
        aggregate_state, aggregate_seen = _aggregate_state(
            db,
            amo_id=amo_id,
            user_id=user_id,
            now=now,
        )

    return schemas.PresenceStateRead(
        user_id=user_id,
        amo_id=amo_id,
        state=aggregate_state.value,
        last_seen_at=aggregate_seen,
        updated_at=now,
        reason=payload.reason,
        session_id=session_id,
    )
