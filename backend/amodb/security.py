# backend/amodb/security.py

"""
Security helpers for AMOdb.

Responsibilities:
- Password hashing and verification
- JWT access token creation and decoding
- FastAPI dependencies for current user / admin checks
- Role-based access helpers for router dependencies

This module is intentionally focused and aligned with the new accounts app:
`amodb.apps.accounts.models.User` and its AccountRole enum.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional, Callable, Union, Set

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .database import get_db  # write DB for auth flows
from amodb.apps.accounts import models as account_models
from amodb.apps.accounts.models import AccountRole

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

# In production, ALWAYS override these via environment variables.
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_IN_PRODUCTION")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

try:
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    )
except ValueError:
    ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Used by FastAPI’s OAuth2 docs / OpenAPI
# This is the logical endpoint that issues tokens.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ---------------------------------------------------------------------------
# PASSWORD HASHING
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if the plain password matches the hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password for storing in the database."""
    return pwd_context.hash(password)


# ---------------------------------------------------------------------------
# JWT TOKENS
# ---------------------------------------------------------------------------


def create_access_token(
    *,
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT.

    The `data` dict should already include the subject, e.g.:
        {"sub": user.id, "amo_id": user.amo_id}
    """
    to_encode = data.copy()

    expire = datetime.utcnow() + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


# ---------------------------------------------------------------------------
# USER LOOKUP HELPERS
# ---------------------------------------------------------------------------


def get_user_by_id(
    db: Session,
    user_id: Union[str, int],
) -> Optional[account_models.User]:
    """
    Minimal helper to load a user by ID.

    Services inside the accounts app may use richer helpers with joinedload;
    this is intentionally simple to avoid circular imports.
    """
    # Normalise id type to int if your PK is integer; adjust if using UUID strings.
    try:
        normalised_id = int(user_id)
    except (TypeError, ValueError):
        normalised_id = user_id

    return (
        db.query(account_models.User)
        .filter(account_models.User.id == normalised_id)
        .first()
    )


# ---------------------------------------------------------------------------
# FASTAPI DEPENDENCIES
# ---------------------------------------------------------------------------


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> account_models.User:
    """
    Decode the JWT access token and return the corresponding User.

    The token is expected to contain a `sub` claim with the user_id.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id: Optional[Union[str, int]] = payload.get("sub")
        if user_id is None:
            raise _credentials_exception()
    except JWTError:
        raise _credentials_exception()

    user = get_user_by_id(db, user_id)
    if user is None:
        raise _credentials_exception()

    return user


def get_current_active_user(
    current_user: account_models.User = Depends(get_current_user),
) -> account_models.User:
    """
    Ensure the current user is active.

    Locked / deactivated users are blocked here rather than deeper in the app.
    """
    if not getattr(current_user, "is_active", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account",
        )
    return current_user


def require_admin(
    current_user: account_models.User = Depends(get_current_active_user),
) -> account_models.User:
    """
    Dependency that enforces an admin-level role.

    Allowed:
    - SUPERUSER
    - AMO_ADMIN
    - QUALITY_MANAGER
    - SAFETY_MANAGER
    """
    if getattr(current_user, "is_superuser", False) or getattr(
        current_user, "is_amo_admin", False
    ):
        return current_user

    if current_user.role in {
        AccountRole.QUALITY_MANAGER,
        AccountRole.SAFETY_MANAGER,
    }:
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient privileges",
    )


# ---------------------------------------------------------------------------
# ROLE-BASED ACCESS HELPER
# ---------------------------------------------------------------------------


def require_roles(
    *allowed_roles: Union[AccountRole, str],
) -> Callable[[account_models.User], account_models.User]:
    """
    Dependency factory to enforce that the current user has one of the given roles.

    Usage (with Enum):
        @router.post(...)
        def endpoint(
            current_user: User = Depends(
                require_roles(AccountRole.SUPERUSER, AccountRole.AMO_ADMIN)
            )
        ):
            ...

    Usage (with strings, useful in routers to avoid importing AccountRole):
        @router.post(...)
        def endpoint(
            current_user: User = Depends(
                require_roles("SUPERUSER", "AMO_ADMIN", "PLANNING_ENGINEER")
            )
        ):
            ...

    Behaviour:
    - SUPERUSER always passes, even if not explicitly listed in `allowed_roles`.
    - Otherwise, the user's `role` must be in the allowed set.
    """
    normalised_roles: Set[AccountRole] = set()
    for r in allowed_roles:
        if isinstance(r, AccountRole):
            normalised_roles.add(r)
        else:
            try:
                normalised_roles.add(AccountRole(r))
            except ValueError:
                raise ValueError(f"Unknown role {r!r} passed to require_roles()")

    def dependency(
        current_user: account_models.User = Depends(get_current_active_user),
    ) -> account_models.User:
        # Global override: SUPERUSER can do anything
        if getattr(current_user, "is_superuser", False):
            return current_user

        if current_user.role not in normalised_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this operation",
            )
        return current_user

    return dependency
