from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from amodb.database import get_db

from .audit_external_access_router import (
    AuditAccessExchange,
    _GUEST_COOKIE,
    _active_grant,
    _append_access_event,
    _public_read_model,
    _utcnow,
)
from .router import public_router


router = APIRouter(prefix="/quality", tags=["Quality / External Audit Session Guard"])


@router.post("/audit-access/exchange")
def exchange_audit_access_guarded(
    payload: AuditAccessExchange,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    grant = _active_grant(db, payload.token)
    participant = grant.participant
    identity = participant.external_identity if participant else None
    if identity is not None and identity.assurance_level == "PASSKEY":
        raise HTTPException(
            status_code=428,
            detail="Passkey verification is required before this external-auditor audit session can be activated.",
        )
    if identity is not None and identity.assurance_level != "EMAIL_LINK":
        raise HTTPException(
            status_code=403,
            detail="This external identity requires an assurance method that is not enabled on the current QMS access flow.",
        )

    now = _utcnow()
    grant.last_used_at = now
    if participant.accepted_at is None:
        participant.accepted_at = now
        participant.status = "ACTIVE"
    _append_access_event(db, grant, "EXCHANGED", "External audit invitation exchanged for an HTTP-only audit session.")
    db.commit()

    max_age = max(1, int((grant.expires_at - now).total_seconds()))
    app_env = os.getenv("APP_ENV", "").strip().lower()
    response.set_cookie(
        key=_GUEST_COOKIE,
        value=payload.token,
        max_age=max_age,
        httponly=True,
        secure=request.url.scheme == "https" or app_env in {"prod", "production"},
        samesite="strict",
        path="/",
    )
    return _public_read_model(db, grant)


@router.delete("/audit-access/session", status_code=status.HTTP_204_NO_CONTENT)
def end_audit_access_session_guarded(response: Response) -> Response:
    # Current EMAIL_LINK and PASSKEY sessions both use the root path. Delete the
    # historical narrower cookie too so clients upgraded from an older build
    # cannot retain a second same-name session cookie.
    response.delete_cookie(_GUEST_COOKIE, path="/", httponly=True, samesite="strict")
    response.delete_cookie(_GUEST_COOKIE, path="/quality/audit-access", httponly=True, samesite="strict")
    return response


def _is_shadowed_session_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return (
        path == "/quality/audit-access/exchange" and "POST" in methods
    ) or (
        path == "/quality/audit-access/session" and "DELETE" in methods
    )


# Remove older same-path compatibility handlers rather than relying only on
# FastAPI insertion order. This makes the cookie path and PASSKEY gate canonical
# for every caller and eliminates the stale logout route permanently at runtime.
public_router.routes[:] = [item for item in public_router.routes if not _is_shadowed_session_route(item)]
public_router.routes[0:0] = list(router.routes)
