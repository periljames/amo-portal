from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.database import get_db

from .phase4_router import start_support_session
from .router import require_platform_superuser


def start_canonical_support_session(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    tenant_id = str(payload.get("tenant_id") or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=422, detail="tenant_id is required")
    access_level = str(payload.get("access_level") or payload.get("mode") or "READ_ONLY").strip().upper()
    normalized = {
        "access_level": access_level,
        "reason": payload.get("reason"),
        "minutes": payload.get("minutes") or 30,
        "requested_route": payload.get("requested_route"),
        "ticket_reference": payload.get("ticket_reference"),
    }
    return start_support_session(tenant_id=tenant_id, payload=normalized, db=db, user=user)


def install_canonical_support_session_route(platform_router: APIRouter) -> None:
    platform_router.routes[:] = [
        route_item
        for route_item in platform_router.routes
        if not (
            str(getattr(route_item, "path", "")) == "/support-sessions"
            and "POST" in set(getattr(route_item, "methods", None) or ())
        )
    ]
    platform_router.add_api_route(
        "/support-sessions",
        start_canonical_support_session,
        methods=["POST"],
        tags=["platform-phase4-operations"],
        name="start_canonical_platform_support_session",
    )


__all__ = ["install_canonical_support_session_route", "start_canonical_support_session"]
