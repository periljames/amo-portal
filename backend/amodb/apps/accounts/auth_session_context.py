from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, status

from amodb.security import (
    bind_current_auth_session_id,
    get_current_active_user,
    reset_current_auth_session_id,
)
from . import models


async def bind_auth_session_to_token_refresh(
    current_user: models.User = Depends(get_current_active_user),
) -> AsyncIterator[None]:
    """Keep a refreshed JWT in the exact authentication session that requested it.

    FastAPI executes this async dependency in the request context before the
    synchronous refresh endpoint enters the worker thread. Context variables are
    copied into that worker, so create_access_token reuses this session id rather
    than creating a second browser/device identity during normal refresh.
    """
    auth_session_id = str(
        getattr(current_user, "auth_session_id", None)
        or getattr(current_user, "_auth_session_id", None)
        or ""
    ).strip()
    if not auth_session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication session identity is unavailable. Sign in again.",
        )

    token = bind_current_auth_session_id(auth_session_id)
    try:
        yield
    finally:
        reset_current_auth_session_id(token)
