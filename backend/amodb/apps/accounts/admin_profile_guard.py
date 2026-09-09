from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from . import models, role_registry
from .tenant_authority import is_standing_admin, is_tenant_admin, tenant_member
from .tenant_authority import active_admin_profile_session


PROFILE_ROUTE_MARKER = "/accounts/admin/admin-profile/"


def _normalise_role(user: models.User) -> str:
    value = getattr(getattr(user, "role", None), "value", getattr(user, "role", ""))
    return role_registry.canonical_role_key(value) or str(value or "").upper()


def require_active_admin_profile_or_roles(*allowed_roles: str) -> Callable[..., models.User]:
    """Allow a prescribed tenant role or a currently elevated administrator.

    This keeps operational authority independent from tenant administration while
    ensuring administrators use cross-cutting configuration endpoints only from
    an active, governed administrator session.
    """
    canonical_allowed = {
        role_registry.canonical_role_key(value) or str(value or "").upper()
        for value in allowed_roles
    }

    def dependency(
        request: Request,
        current_user: models.User = Depends(get_current_active_user),
        db: Session = Depends(get_db),
    ) -> models.User:
        if _normalise_role(current_user) in canonical_allowed:
            return current_user
        return require_active_admin_profile(request=request, current_user=current_user, db=db)

    return dependency


def _is_current_implicit_admin(user: models.User) -> bool:
    return is_standing_admin(user)


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
    # Request-only authority must never be persisted or serialized as a standing appointment.
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
    if not tenant_member(current_user):
        raise HTTPException(status_code=403, detail="A tenant identity is required for administration.")
    if is_tenant_admin(current_user):
        return current_user
    _auth_session_id(current_user)
    from types import SimpleNamespace
    if not active_admin_profile_session(db, current_user, SimpleNamespace(id=current_user.amo_id)):
        raise HTTPException(status_code=403, detail="Activate Admin profile before using tenant administration APIs.")
    _mark_request_as_admin_profile(current_user)
    return current_user
