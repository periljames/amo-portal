from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from amodb.apps.quality.public_invite_security import (
    public_invite_security,
    resolve_public_invite_token,
)


def _request(*, path_token: str, authorization: str | None = None, method: str = "GET", suffix: str = "") -> Request:
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("latin-1")))
    path = f"/quality/cars/invite/{path_token}{suffix}"
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "client": ("203.0.113.10", 44321),
        "server": ("portal.example", 443),
        "path_params": {"invite_token": path_token},
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_current_route_requires_a_bearer_capability():
    dependency = public_invite_security(_request(path_token="current"), Response())
    with pytest.raises(HTTPException) as error:
        await dependency.__anext__()
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_current_route_scopes_bearer_and_applies_ip_and_token_limits():
    bearer = "synthetic-public-capability"
    response = Response()
    dependency = public_invite_security(
        _request(path_token="current", authorization=f"Bearer {bearer}"), response
    )
    with patch("amodb.apps.quality.public_invite_security.enforce") as enforce:
        await dependency.__anext__()
        try:
            assert resolve_public_invite_token("current") == bearer
            assert response.headers["Cache-Control"] == "private, no-store, max-age=0"
            assert response.headers["Referrer-Policy"] == "no-referrer"
            assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
            assert enforce.call_count == 2
            assert enforce.call_args_list[0].args == ("203.0.113.10", "car-invite-ip", 300)
            assert enforce.call_args_list[1].args == (bearer, "car-invite-capability", 120)
        finally:
            await dependency.aclose()


@pytest.mark.asyncio
async def test_legacy_path_token_remains_supported_during_url_migration():
    legacy = "a" * 32
    dependency = public_invite_security(_request(path_token=legacy), Response())
    with patch("amodb.apps.quality.public_invite_security.enforce"):
        await dependency.__anext__()
        try:
            assert resolve_public_invite_token(legacy) == legacy
        finally:
            await dependency.aclose()


def test_current_sentinel_without_request_context_is_not_a_credential():
    with pytest.raises(HTTPException) as error:
        resolve_public_invite_token("current")
    assert error.value.status_code == 404

@pytest.mark.parametrize("authorization", ["Basic employee-session", "Bearer ", f"Bearer {'x' * 65}"])
@pytest.mark.asyncio
async def test_current_route_rejects_non_bearer_empty_and_oversized_credentials(authorization):
    dependency = public_invite_security(
        _request(path_token="current", authorization=authorization), Response()
    )
    with pytest.raises(HTTPException) as error:
        await dependency.__anext__()
    assert error.value.status_code == 404


@pytest.mark.parametrize(
    ("method", "suffix", "expected_limit"),
    [
        ("GET", "", 120),
        ("POST", "/attachments", 10),
        ("POST", "/recall", 5),
        ("PATCH", "", 30),
    ],
)
@pytest.mark.asyncio
async def test_public_invite_rate_limit_varies_by_operation(method, suffix, expected_limit):
    response = Response()
    dependency = public_invite_security(
        _request(
            path_token="current",
            authorization="Bearer synthetic-public-capability",
            method=method,
            suffix=suffix,
        ),
        response,
    )
    with patch("amodb.apps.quality.public_invite_security.enforce") as enforce:
        await dependency.__anext__()
        try:
            assert enforce.call_count == 2
            assert enforce.call_args_list[1].args[2] == expected_limit
        finally:
            await dependency.aclose()
