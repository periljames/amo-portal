from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import models


def active_admin_profile_session(db: Session, user: models.User, amo: models.AMO) -> bool:
    """Return whether this tenant user has a live governed Admin Profile session.

    Eligibility is represented by the session and its linked active grant, not by
    mutating the user's standing role. Existing AMO administrators use sessions
    without a grant; temporary and permanent grantees use a linked active grant.
    """
    try:
        return db.execute(
            text(
                """
                SELECT 1
                FROM admin_profile_sessions s
                LEFT JOIN admin_access_grants g ON g.id = s.grant_id
                WHERE s.amo_id = :amo_id
                  AND s.user_id = :user_id
                  AND s.revoked_at IS NULL
                  AND s.expires_at > :now
                  AND (
                    s.grant_id IS NULL
                    OR (
                      g.amo_id = s.amo_id
                      AND g.user_id = s.user_id
                      AND g.status = 'ACTIVE'
                      AND (g.valid_from IS NULL OR g.valid_from <= :now)
                      AND (g.valid_until IS NULL OR g.valid_until > :now)
                    )
                  )
                LIMIT 1
                """
            ),
            {
                "amo_id": str(amo.id),
                "user_id": str(user.id),
                "now": datetime.now(timezone.utc),
            },
        ).first() is not None
    except SQLAlchemyError:
        return False
