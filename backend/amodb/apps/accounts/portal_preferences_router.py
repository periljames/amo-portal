from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models


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


def _read_preferences(db: Session, user_id: str) -> dict[str, object] | None:
    row = db.execute(
        text(
            """
            SELECT user_id, amo_id, text_scale, density, motion, color_scheme,
                   accent, version, updated_at
            FROM user_portal_preferences
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    ).mappings().first()
    return dict(row) if row else None


def _response_for_user(user: models.User, row: dict[str, object] | None = None) -> PortalPreferencesRead:
    values = {**_DEFAULTS, **(row or {})}
    return PortalPreferencesRead(
        user_id=str(user.id),
        amo_id=str(user.amo_id) if user.amo_id else None,
        text_scale=cast(TextScale, str(values["text_scale"])),
        density=cast(PortalDensity, str(values["density"])),
        motion=cast(PortalMotion, str(values["motion"])),
        color_scheme=cast(PortalColorScheme, str(values["color_scheme"])),
        accent=cast(PortalAccent, str(values["accent"])),
        version=int(values.get("version") or 1),
        updated_at=cast(datetime | None, values.get("updated_at")),
    )


@router.get("/", response_model=PortalPreferencesRead)
def get_portal_preferences(
    response: Response,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> PortalPreferencesRead:
    _disable_http_cache(response)
    return _response_for_user(current_user, _read_preferences(db, str(current_user.id)))


@router.patch("/", response_model=PortalPreferencesRead)
def update_portal_preferences(
    payload: PortalPreferencesPatch,
    response: Response,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> PortalPreferencesRead:
    _disable_http_cache(response)
    user_id = str(current_user.id)
    existing = _read_preferences(db, user_id)
    merged = {**_DEFAULTS, **(existing or {}), **payload.model_dump(exclude_none=True)}
    now = datetime.now(timezone.utc)

    if existing:
        db.execute(
            text(
                """
                UPDATE user_portal_preferences
                SET amo_id = :amo_id,
                    text_scale = :text_scale,
                    density = :density,
                    motion = :motion,
                    color_scheme = :color_scheme,
                    accent = :accent,
                    version = version + 1,
                    updated_at = :updated_at
                WHERE user_id = :user_id
                """
            ),
            {
                "user_id": user_id,
                "amo_id": str(current_user.amo_id) if current_user.amo_id else None,
                "updated_at": now,
                **{key: merged[key] for key in _DEFAULTS},
            },
        )
    else:
        db.execute(
            text(
                """
                INSERT INTO user_portal_preferences (
                    id, user_id, amo_id, text_scale, density, motion,
                    color_scheme, accent, version, created_at, updated_at
                ) VALUES (
                    :id, :user_id, :amo_id, :text_scale, :density, :motion,
                    :color_scheme, :accent, 1, :created_at, :updated_at
                )
                """
            ),
            {
                "id": str(uuid4()),
                "user_id": user_id,
                "amo_id": str(current_user.amo_id) if current_user.amo_id else None,
                "created_at": now,
                "updated_at": now,
                **{key: merged[key] for key in _DEFAULTS},
            },
        )

    db.commit()
    return _response_for_user(current_user, _read_preferences(db, user_id))
