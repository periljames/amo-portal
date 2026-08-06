"""Selection integrity endpoints shared by governed Workforce bulk actions."""
from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import governance_schemas, hr_selection_integrity, permissions, services

router = APIRouter(prefix="/workforce/hr", tags=["workforce-selection"])


class SelectionPreview(BaseModel):
    matched_count: int
    selection_token: str


@router.post("/people/governed/selection-preview", response_model=SelectionPreview)
def preview_governed_selection(
    selection: governance_schemas.GovernedPeopleSelection,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    permissions.require_permission(
        db, user=current_user, permission=permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS
    )
    try:
        user_ids, token = hr_selection_integrity.resolve_with_token(
            db, amo_id=services.effective_amo_id(current_user), selection=selection
        )
        if not user_ids:
            raise ValueError("The selected Workforce population is empty")
        return SelectionPreview(matched_count=len(user_ids), selection_token=token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": str(exc),
                "error_code": "WORKFORCE_SELECTION_PREVIEW_INVALID",
                "field_errors": {},
                "conflicts": [],
                "retryable": False,
            },
        ) from exc
