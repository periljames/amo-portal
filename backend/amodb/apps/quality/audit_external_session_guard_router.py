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
    response.delete_cookie(_GUEST_COOKIE, path="/", httponly=True, samesite="strict")
    return response


# These routes intentionally shadow the older exchange/delete endpoints. PASSKEY
# invitations must complete the dedicated WebAuthn flow before any cookie is set.
public_router.routes[0:0] = list(router.routes)
