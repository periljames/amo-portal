from __future__ import annotations

import asyncio
import json

from redis.exceptions import RedisError

from amodb.distributed_rate_limit import DistributedAuthRateLimitMiddleware


class FakeLimiter:
    window_seconds = 60

    def __init__(self, *, allowed: bool = True, unavailable: bool = False) -> None:
        self.allowed = allowed
        self.unavailable = unavailable
        self.calls: list[tuple[str, str]] = []

    async def check(self, endpoint: str, subject: str) -> tuple[bool, int]:
        self.calls.append((endpoint, subject))
        if self.unavailable:
            raise RedisError("down")
        return self.allowed, 1 if self.allowed else 11


def _scope(path: str = "/auth/login") -> dict:
    return {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [(b"content-type", b"application/json")],
        "client": ("10.10.10.10", 43210),
        "scheme": "https",
        "server": ("portal.test", 443),
        "http_version": "1.1",
        "query_string": b"",
    }


def test_subject_is_global_per_login_identity_without_storing_raw_key_material() -> None:
    subject = DistributedAuthRateLimitMiddleware.subject(
        "login",
        json.dumps({"amo_slug": " SafariLink ", "email": " Pilot@Example.COM "}).encode(),
        _scope(),
    )
    assert subject == "safarilink|pilot@example.com"


def test_allowed_auth_request_is_replayed_to_inner_app() -> None:
    received_body = bytearray()
    response_messages: list[dict] = []
    limiter = FakeLimiter(allowed=True)

    async def inner(scope, receive, send):
        message = await receive()
        received_body.extend(message.get("body", b""))
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = DistributedAuthRateLimitMiddleware(inner, limiter=limiter)  # type: ignore[arg-type]
    body = b'{"amo_slug":"safarilink","identifier":"pilot@example.com"}'
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        response_messages.append(message)

    asyncio.run(middleware(_scope(), receive, send))

    assert bytes(received_body) == body
    assert limiter.calls == [("login", "safarilink|pilot@example.com")]
    assert response_messages[0]["status"] == 204


def test_shared_limit_rejects_before_authentication_work() -> None:
    called = False
    response_messages: list[dict] = []
    limiter = FakeLimiter(allowed=False)

    async def inner(scope, receive, send):
        nonlocal called
        called = True

    middleware = DistributedAuthRateLimitMiddleware(inner, limiter=limiter)  # type: ignore[arg-type]
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered = True
        return {
            "type": "http.request",
            "body": b'{"amo_slug":"safarilink","staff_code":"SL001"}',
            "more_body": False,
        }

    async def send(message):
        response_messages.append(message)

    asyncio.run(middleware(_scope(), receive, send))

    assert called is False
    assert response_messages[0]["status"] == 429
    assert any(header[0] == b"retry-after" for header in response_messages[0]["headers"])
    payload = json.loads(response_messages[1]["body"])
    assert payload["error_code"] == "AUTH_RATE_LIMITED"
    assert payload["retryable"] is True


def test_required_shared_limiter_outage_fails_auth_closed() -> None:
    called = False
    response_messages: list[dict] = []
    limiter = FakeLimiter(unavailable=True)

    async def inner(scope, receive, send):
        nonlocal called
        called = True

    middleware = DistributedAuthRateLimitMiddleware(inner, limiter=limiter)  # type: ignore[arg-type]
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered = True
        return {"type": "http.request", "body": b'{"identifier":"pilot@example.com"}', "more_body": False}

    async def send(message):
        response_messages.append(message)

    asyncio.run(middleware(_scope(), receive, send))

    assert called is False
    assert response_messages[0]["status"] == 503
    payload = json.loads(response_messages[1]["body"])
    assert payload["error_code"] == "AUTH_RATE_LIMIT_UNAVAILABLE"
    assert payload["retryable"] is True


def test_oversized_auth_request_is_rejected_with_non_retryable_metadata() -> None:
    called = False
    response_messages: list[dict] = []
    limiter = FakeLimiter()

    async def inner(scope, receive, send):
        nonlocal called
        called = True

    middleware = DistributedAuthRateLimitMiddleware(inner, limiter=limiter)  # type: ignore[arg-type]
    middleware.max_body_bytes = 4096
    delivered = False
    body = b"x" * 4097

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        response_messages.append(message)

    asyncio.run(middleware(_scope(), receive, send))

    assert called is False
    assert limiter.calls == []
    assert response_messages[0]["status"] == 413
    payload = json.loads(response_messages[1]["body"])
    assert payload["error_code"] == "AUTH_REQUEST_TOO_LARGE"
    assert payload["retryable"] is False
