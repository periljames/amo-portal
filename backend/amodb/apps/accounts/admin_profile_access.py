from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import models


def _normalise_role(user: models.User) -> str:
    value = getattr(getattr(user, "role", None), "value", getattr(user, "role", ""))
    return str(value or "").upper()


def _is_current_implicit_admin(user: models.User) -> bool:
    if getattr(user, "is_superuser", False):
        return False
    return bool(
        getattr(user, "is_amo_admin", False)
        or _normalise_role(user) == "AMO_ADMIN"
    )


def active_admin_profile_session(db: Session, user: models.User, amo: models.AMO) -> bool:
    """Return whether this exact authenticated tenant session is elevated.

    Existing AMO administrators use grantless rows only while they remain
    standing administrators. Approved grantees use rows linked to a currently
    active grant. Concurrent logins for the same account never share elevation.
    """
    auth_session_id = str(
        getattr(user, "auth_session_id", None)
        or getattr(user, "_auth_session_id", None)
        or ""
    ).strip()
    if not auth_session_id:
        return False

    try:
        return db.execute(
            text(
                """
                SELECT 1
                FROM admin_profile_sessions s
                LEFT JOIN admin_access_grants g ON g.id = s.grant_id
                WHERE s.amo_id = :amo_id
                  AND s.user_id = :user_id
                  AND s.auth_session_id = :auth_session_id
                  AND s.revoked_at IS NULL
                  AND s.expires_at > :now
                  AND (
                    (
                      :implicit_admin = TRUE
                      AND s.grant_id IS NULL
                    )
                    OR (
                      s.grant_id IS NOT NULL
                      AND g.amo_id = s.amo_id
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
                "auth_session_id": auth_session_id,
                "implicit_admin": _is_current_implicit_admin(user),
                "now": datetime.now(timezone.utc),
            },
        ).first() is not None
    except SQLAlchemyError:
        return False
