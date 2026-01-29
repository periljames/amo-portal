# backend/amodb/apps/accounts/router_onboarding.py

from __future__ import annotations

from fastapi import APIRouter, Depends

from amodb.security import get_current_active_user
from . import models, schemas

router = APIRouter(prefix="/accounts/onboarding", tags=["accounts"])


@router.get(
    "/status",
    response_model=schemas.OnboardingStatusRead,
    summary="Get onboarding completion status for the current user",
)
def get_onboarding_status(
    current_user: models.User = Depends(get_current_active_user),
) -> schemas.OnboardingStatusRead:
    missing: list[str] = []
    if current_user.must_change_password:
        missing.append("password_change")
    return schemas.OnboardingStatusRead(is_complete=not missing, missing=missing)
