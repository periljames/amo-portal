from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import models, schemas
from .services import effective_amo_id

MIN_PRESENCE_WRITE_INTERVAL_SECONDS = max(
    5,
    int(os.getenv("PRESENCE_MIN_WRITE_INTERVAL_SECONDS", "12")),
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def update_presence_state(
    db: Session,
    *,
    user: account_models.User,
    payload: schemas.PresenceStateUpdateRequest,
) -> schemas.PresenceStateRead:
    """Persist meaningful presence changes without a database write every five seconds."""
    amo_id = effective_amo_id(user)
    now = _utcnow()
    target_state = (
        models.PresenceKind.ONLINE
        if payload.state == "online"
        else models.PresenceKind.AWAY
    )
    if not amo_id:
        return schemas.PresenceStateRead(
            user_id=str(user.id),
            amo_id="platform",
            state=target_state.value,
            last_seen_at=now,
            updated_at=now,
            reason=payload.reason,
        )

    row = (
        db.query(models.PresenceState)
        .filter(
            models.PresenceState.amo_id == amo_id,
            models.PresenceState.user_id == str(user.id),
        )
        .first()
    )
    if row is not None:
        last_seen = _aware(row.last_seen_at)
        elapsed = (now - last_seen).total_seconds() if last_seen else None
        if (
            row.state == target_state
            and elapsed is not None
            and elapsed < MIN_PRESENCE_WRITE_INTERVAL_SECONDS
        ):
            return schemas.PresenceStateRead(
                user_id=row.user_id,
                amo_id=row.amo_id,
                state=row.state.value,
                last_seen_at=row.last_seen_at,
                updated_at=row.updated_at,
                reason=payload.reason,
            )
    else:
        row = models.PresenceState(
            amo_id=amo_id,
            user_id=str(user.id),
            state=target_state,
            last_seen_at=now,
        )
        db.add(row)

    row.state = target_state
    row.last_seen_at = now
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return schemas.PresenceStateRead(
        user_id=row.user_id,
        amo_id=row.amo_id,
        state=row.state.value,
        last_seen_at=row.last_seen_at,
        updated_at=row.updated_at,
        reason=payload.reason,
    )
