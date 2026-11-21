"""Purpose-bound bearer access for public CAR invitation routes.

A public invitation is the respondent's credential. It is separate from employee
authentication and grants access only to the CAR resolved by the guest lookup.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import AsyncIterator

from fastapi import HTTPException, Request, Response

from amodb.apps.accounts.auth_rate_limit import enforce

_PUBLIC_CAR_INVITE_TOKEN: ContextVar[str | None] = ContextVar(
    "public_car_invite_token", default=None
)


def resolve_public_invite_token(path_token: str | None) -> str:
    """Resolve the tokenless current route from this request's bearer."""
    if path_token == "current":
        token = _PUBLIC_CAR_INVITE_TOKEN.get()
        if not token:
            raise HTTPException(status_code=404, detail="CAR invitation not found")
        return token
    token = (path_token or "").strip()
    if not token or len(token) > 64:
        raise HTTPException(status_code=404, detail="CAR invitation not found")
    return token


async def public_invite_security(
    request: Request, response: Response
) -> AsyncIterator[None]:
    """Apply no-store headers, request limits and request-scoped bearer handling."""
    response.headers.update({
        "Cache-Control": "private, no-store, max-age=0",
        "Pragma": "no-cache",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Robots-Tag": "noindex, nofollow",
    })

    path_token = request.path_params.get("invite_token")
    token = path_token
    if path_token == "current":
        authorization = request.headers.get("authorization", "")
        scheme, separator, credential = authorization.partition(" ")
        if scheme.lower() != "bearer" or not separator or not credential.strip():
            raise HTTPException(status_code=404, detail="CAR invitation not found")
        token = credential.strip()

    if token:
        if len(token) > 64:
            raise HTTPException(status_code=404, detail="CAR invitation not found")
        client_ip = request.client.host if request.client else "unknown"
        # enforce() hashes each subject before writing a Redis/in-memory key.
        enforce(client_ip, "car-invite-ip", 300, window_seconds=60)
        path = request.url.path.lower()
        if request.method.upper() == "GET":
            token_limit = 120
        elif "attachments" in path and request.method.upper() == "POST":
            token_limit = 10
        elif path.endswith("/recall"):
            token_limit = 5
        else:
            token_limit = 30
        enforce(token, "car-invite-capability", token_limit, window_seconds=60)

    context_token = _PUBLIC_CAR_INVITE_TOKEN.set(token) if token else None
    try:
        yield
    finally:
        if context_token is not None:
            _PUBLIC_CAR_INVITE_TOKEN.reset(context_token)
