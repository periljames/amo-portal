from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from . import models


def revoke_admin_profile_on_logout(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """Revoke every live elevated session before the logout transaction commits.

    The nested transaction keeps logout available on development databases where
    the Admin Profile migration has not yet been applied. A missing governance
    table rolls back only the savepoint; access-token revocation still commits.
    """
    now = datetime.now(timezone.utc)
    try:
        with db.begin_nested():
            db.execute(
                text(
                    """
                    UPDATE admin_profile_sessions
                    SET revoked_at = :now
                    WHERE user_id = :user_id
                      AND revoked_at IS NULL
                    """
                ),
                {"now": now, "user_id": str(current_user.id)},
            )
    except SQLAlchemyError:
        # Token revocation is still authoritative when the optional governance
        # schema is unavailable during development or disaster recovery.
        return

    amo_id = getattr(current_user, "amo_id", None)
    if not amo_id:
        return
    try:
        with db.begin_nested():
            db.execute(
                text(
                    """
                    INSERT INTO admin_access_events (
                        id, amo_id, actor_user_id, subject_user_id, grant_id,
                        session_id, event_type, detail, created_at
                    ) VALUES (
                        :event_id, :amo_id, :user_id, :user_id, NULL,
                        NULL, 'ADMIN_PROFILE_REVOKED_ON_LOGOUT',
                        'Authentication session ended', :now
                    )
                    """
                ),
                {
                    "event_id": str(uuid4()),
                    "amo_id": str(amo_id),
                    "user_id": str(current_user.id),
                    "now": now,
                },
            )
    except SQLAlchemyError:
        # Security revocation must not depend on optional audit-event storage.
        return
