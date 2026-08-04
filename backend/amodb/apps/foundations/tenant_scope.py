from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models

AMO_CONTEXT_HEADER = "X-AMO-Context-Id"


def _normalise_amo_id(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > 64:
        return None
    return candidate


def resolve_foundation_amo_id(
    db: Session,
    user: account_models.User,
    requested_amo_id: object = None,
    *,
    require_explicit_superuser: bool = False,
) -> str:
    """Resolve one immutable tenant target for the current HTTP request.

    A superuser write must carry an explicit AMO header. This prevents another
    browser session from changing the persisted support context between a
    preflight read and the mutation. Non-superusers remain bound to their own
    AMO and cannot use the header to cross tenant boundaries.
    """
    requested = _normalise_amo_id(requested_amo_id)
    is_superuser = bool(getattr(user, "is_superuser", False))

    if not is_superuser:
        own_amo_id = _normalise_amo_id(getattr(user, "amo_id", None))
        if not own_amo_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The current account is not assigned to an AMO.",
            )
        if requested and requested != own_amo_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The requested AMO does not match the current account.",
            )
        return own_amo_id

    if require_explicit_superuser and not requested:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{AMO_CONTEXT_HEADER} is required for superuser foundation changes.",
        )

    target_amo_id = requested or _normalise_amo_id(
        getattr(user, "effective_amo_id", None) or getattr(user, "active_amo_id", None)
    )
    if not target_amo_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select an active AMO support context before accessing foundation records.",
        )

    try:
        active_amo = (
            db.query(account_models.AMO.id)
            .filter(
                account_models.AMO.id == target_amo_id,
                account_models.AMO.is_active.is_(True),
            )
            .first()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AMO context could not be verified.",
        ) from exc

    if not active_amo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested AMO is unavailable or inactive.",
        )
    return target_amo_id


def get_bound_foundation_amo_id(
    x_amo_context_id: Optional[str] = Header(default=None, alias=AMO_CONTEXT_HEADER),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> str:
    return resolve_foundation_amo_id(db, current_user, x_amo_context_id)


def get_bound_foundation_write_amo_id(
    x_amo_context_id: Optional[str] = Header(default=None, alias=AMO_CONTEXT_HEADER),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> str:
    return resolve_foundation_amo_id(
        db,
        current_user,
        x_amo_context_id,
        require_explicit_superuser=True,
    )
