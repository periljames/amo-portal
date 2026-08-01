from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.database import get_db

from . import models, services
from .router import require_platform_superuser


router = APIRouter(prefix="/phase4", tags=["platform-phase4-api-keys"])


def _parse_expiry(value: Any) -> datetime | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="expires_at must be a valid ISO datetime") from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise HTTPException(status_code=422, detail="expires_at must be a valid ISO datetime")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="expires_at must be in the future")
    return parsed


def create_scoped_api_key(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    name = str(payload.get("name") or "Platform API key").strip()
    scopes = payload.get("scopes") or []
    if not isinstance(scopes, list) or not scopes:
        raise HTTPException(status_code=422, detail="At least one API scope is required")
    normalized_scopes = sorted({str(scope).strip() for scope in scopes if str(scope).strip()})
    if not normalized_scopes:
        raise HTTPException(status_code=422, detail="At least one API scope is required")
    reason = str(payload.get("reason") or "Platform API key issued").strip()
    expires_at = _parse_expiry(payload.get("expires_at"))

    raw = "apk_" + secrets.token_urlsafe(32)
    row = models.PlatformAPIKey(
        name=name,
        key_prefix=raw[:12],
        key_hash=hashlib.sha256(raw.encode()).hexdigest(),
        scopes_json=normalized_scopes,
        created_by=str(user.id),
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    services.audit(
        db,
        actor_user_id=str(user.id),
        action="integration.api_key.created",
        entity_type="platform_api_key",
        entity_id=row.id,
        reason=reason,
        details={
            "prefix": row.key_prefix,
            "scopes": normalized_scopes,
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "name": row.name,
        "key_prefix": row.key_prefix,
        "status": row.status,
        "scopes_json": row.scopes_json,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "raw_key": raw,
    }


@router.post("/api-keys")
def create_phase4_api_key(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    return create_scoped_api_key(payload=payload, db=db, user=user)


def install_canonical_api_key_create_route(platform_router: APIRouter) -> None:
    """Replace the legacy create endpoint that discarded scopes and expiry."""

    platform_router.routes[:] = [
        route_item
        for route_item in platform_router.routes
        if not (
            str(getattr(route_item, "path", "")) == "/integrations/api-keys"
            and "POST" in set(getattr(route_item, "methods", None) or ())
        )
    ]
    platform_router.add_api_route(
        "/integrations/api-keys",
        create_scoped_api_key,
        methods=["POST"],
        tags=["platform-phase4-api-keys"],
        name="create_scoped_platform_api_key",
    )


__all__ = ["router", "create_scoped_api_key", "install_canonical_api_key_create_route"]
