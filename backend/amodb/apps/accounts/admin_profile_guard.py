from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from amodb.database import get_db
from amodb.security import get_current_active_user
from . import models


PROFILE_ROUTE_MARKER = "/accounts/admin/admin-profile/"


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


def _auth_session_id(user: models.User) -> str:
    value = str(
        getattr(user, "auth_session_id", None)
        or getattr(user, "_auth_session_id", None)
        or ""
    ).strip()
    if not value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication session identity is unavailable. Sign in again.",
        )
    return value


def _mark_request_as_admin_profile(user: models.User) -> None:
    """Expose elevation to legacy dependencies without persisting role changes.

    Existing administration handlers still depend on `require_admin` or
    `require_roles(..., AMO_ADMIN)`. FastAPI resolves this router dependency
    first and reuses the same current-user object for later dependencies.
    `set_committed_value` changes only the request-scoped ORM identity state and
    does not mark the mapped role fields dirty for database persistence.
    """
    try:
        set_committed_value(user, "is_amo_admin", True)
        set_committed_value(user, "role", models.AccountRole.AMO_ADMIN)
    except Exception:
        # Lightweight test doubles are not SQLAlchemy-mapped instances.
        setattr(user, "is_amo_admin", True)
        setattr(user, "role", models.AccountRole.AMO_ADMIN)
    setattr(user, "_admin_profile_elevated", True)


def require_active_admin_profile(
    request: Request,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> models.User:
    """Protect every tenant administration API with active governed elevation.

    The profile state/activation/deactivation and grant-governance endpoints are
    exempt because they are the controlled entry point into elevation. Platform
    superusers remain governed by the separate platform control plane.
    """
    if PROFILE_ROUTE_MARKER in request.url.path:
        return current_user
    if getattr(current_user, "is_superuser", False):
        return current_user

    amo_id = getattr(current_user, "effective_amo_id", None) or getattr(current_user, "amo_id", None)
    if not amo_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A tenant identity is required for administration.",
        )

    now = datetime.now(timezone.utc)
    auth_session_id = _auth_session_id(current_user)
    implicit_admin = _is_current_implicit_admin(current_user)
    try:
        session = db.execute(
            text(
                """
                SELECT s.id
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
                ORDER BY s.activated_at DESC
                LIMIT 1
                """
            ),
            {
                "amo_id": str(amo_id),
                "user_id": str(current_user.id),
                "auth_session_id": auth_session_id,
                "implicit_admin": implicit_admin,
                "now": now,
            },
        ).first()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Administrator profile service is not ready. Open the profile menu and activate Admin profile.",
        ) from exc

    if not session:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Activate Admin profile before using tenant administration APIs.",
        )

    _mark_request_as_admin_profile(current_user)
    return current_user
