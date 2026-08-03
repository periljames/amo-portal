from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from . import models


PROFILE_ROUTE_MARKER = "/accounts/admin/admin-profile/"


def require_active_admin_profile(
    request: Request,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> models.User:
    """Protect every tenant administration API with an active elevated session.

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

    try:
        session = db.execute(
            text(
                """
                SELECT id
                FROM admin_profile_sessions
                WHERE amo_id = :amo_id
                  AND user_id = :user_id
                  AND revoked_at IS NULL
                  AND expires_at > :now
                ORDER BY activated_at DESC
                LIMIT 1
                """
            ),
            {
                "amo_id": str(amo_id),
                "user_id": str(current_user.id),
                "now": datetime.now(timezone.utc),
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
    return current_user
