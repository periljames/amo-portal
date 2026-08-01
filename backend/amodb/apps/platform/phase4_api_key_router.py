from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.database import get_db

from . import models, services
from .router import require_platform_superuser


router = APIRouter(prefix="/phase4", tags=["platform-phase4-api-keys"])


@router.post("/api-keys")
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
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A reason is required")

    expires_at = payload.get("expires_at")
    if isinstance(expires_at, str) and expires_at.strip():
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="expires_at must be a valid ISO datetime") from exc
    elif not expires_at:
        expires_at = None

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
