from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, cast

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models
from .portal_preferences_models import UserPortalPreference


router = APIRouter(prefix="/portal-preferences", tags=["auth"])

TextScale = Literal["standard", "large", "extra-large"]
PortalDensity = Literal["comfortable", "compact"]
PortalMotion = Literal["system", "full", "reduced"]
PortalColorScheme = Literal["system", "light", "dark"]
PortalAccent = Literal["tenant", "blue", "teal", "green", "amber", "violet"]


class PortalPreferencesPatch(BaseModel):
    text_scale: TextScale | None = None
    density: PortalDensity | None = None
    motion: PortalMotion | None = None
    color_scheme: PortalColorScheme | None = None
    accent: PortalAccent | None = None


class PortalPreferencesRead(BaseModel):
    user_id: str
    amo_id: str | None
    text_scale: TextScale = "standard"
    density: PortalDensity = "comfortable"
    motion: PortalMotion = "system"
    color_scheme: PortalColorScheme = "system"
    accent: PortalAccent = "tenant"
    version: int = 1
    updated_at: datetime | None = None


_DEFAULTS = {
    "text_scale": "standard",
    "density": "comfortable",
    "motion": "system",
    "color_scheme": "system",
    "accent": "tenant",
}


def _disable_http_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"


def _read_preferences(db: Session, user_id: str) -> UserPortalPreference | None:
    return (
        db.query(UserPortalPreference)
        .filter(UserPortalPreference.user_id == user_id)
        .one_or_none()
    )


def _response_for_user(
    user: models.User,
    preference: UserPortalPreference | None = None,
) -> PortalPreferencesRead:
    values = {
        key: getattr(preference, key, default) if preference is not None else default
        for key, default in _DEFAULTS.items()
    }
    return PortalPreferencesRead(
        user_id=str(user.id),
        amo_id=str(user.amo_id) if user.amo_id else None,
        text_scale=cast(TextScale, str(values["text_scale"])),
        density=cast(PortalDensity, str(values["density"])),
        motion=cast(PortalMotion, str(values["motion"])),
        color_scheme=cast(PortalColorScheme, str(values["color_scheme"])),
        accent=cast(PortalAccent, str(values["accent"])),
        version=int(preference.version if preference is not None else 1),
        updated_at=preference.updated_at if preference is not None else None,
    )


@router.get("/", response_model=PortalPreferencesRead)
def get_portal_preferences(
    response: Response,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> PortalPreferencesRead:
    _disable_http_cache(response)
    return _response_for_user(
        current_user,
        _read_preferences(db, str(current_user.id)),
    )


@router.patch("/", response_model=PortalPreferencesRead)
def update_portal_preferences(
    payload: PortalPreferencesPatch,
    response: Response,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> PortalPreferencesRead:
    _disable_http_cache(response)
    user_id = str(current_user.id)
    preference = _read_preferences(db, user_id)
    patch = payload.model_dump(exclude_none=True)
    now = datetime.now(timezone.utc)

    if preference is None:
        preference = UserPortalPreference(
            user_id=user_id,
            amo_id=str(current_user.amo_id) if current_user.amo_id else None,
            **patch,
        )
        db.add(preference)
    else:
        preference.amo_id = str(current_user.amo_id) if current_user.amo_id else None
        for key, value in patch.items():
            setattr(preference, key, value)
        preference.version = int(preference.version or 0) + 1
        preference.updated_at = now

    db.commit()
    db.refresh(preference)
    return _response_for_user(current_user, preference)
