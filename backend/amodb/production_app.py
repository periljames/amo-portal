"""Production ASGI application with cross-replica admission and runtime guards."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import main as core
from .runtime_concurrency import install_runtime_concurrency

logger = logging.getLogger(__name__)

_PROTECTED_AUTH_PATHS = {
    "/auth/login": "login",
    "/auth/password-reset/request": "password-reset-request",
    "/auth/password-reset/confirm": "password-reset-confirm",
}

_SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now_ms - window_ms)
local count = redis.call('ZCARD', key)
if count >= limit then
  redis.call('PEXPIRE', key, window_ms)
  return count + 1
end
redis.call('ZADD', key, now_ms, member)
redis.call('PEXPIRE', key, window_ms)
return count + 1
"""


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)) or str(default))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    return max(minimum, min(maximum, value))


class RedisAuthRateLimiter:
    """Global sliding-window limiter for credential-sensitive public routes.

    Keys contain only SHA-256 digests of normalized login/reset subjects. Raw
    email addresses, staff codes, reset tokens and request bodies are never sent
    to Redis.
    """

    def __init__(self) -> None:
        self.required = _env_bool("AUTH_RATE_LIMIT_SHARED_REQUIRED", False)
        self.url = (os.getenv("AUTH_RATE_LIMIT_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
        self.window_seconds = _bounded_int("AUTH_RATE_LIMIT_WINDOW_SEC", 60, 10, 3600)
        self.max_attempts = _bounded_int("AUTH_RATE_LIMIT_MAX_ATTEMPTS", 10, 2, 1000)
        self.prefix = (os.getenv("AUTH_RATE_LIMIT_KEY_PREFIX") or "amo:auth-rate-limit:v1").strip(":")
        self.client: Redis | None = None

        if self.required and not self.url:
            raise RuntimeError(
                "AUTH_RATE_LIMIT_SHARED_REQUIRED=true but AUTH_RATE_LIMIT_REDIS_URL/REDIS_URL is not configured"
            )
        if self.url:
            self.client = Redis.from_url(
                self.url,
                encoding=None,
                decode_responses=False,
                socket_connect_timeout=2.0,
                socket_timeout=2.0,
                health_check_interval=30,
            )

    async def verify_startup(self) -> None:
        if not self.client:
            return
        try:
            await self.client.ping()
        except RedisError as exc:
            if self.required:
                raise RuntimeError("Shared authentication rate limiter is unavailable") from exc
            logger.warning("Shared authentication rate limiter unavailable; local route guard remains active")

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()

    async def check(self, endpoint: str, subject: str) -> tuple[bool, int]:
        if not self.client:
            return True, 0
        subject_digest = hashlib.sha256(subject.encode("utf-8", errors="ignore")).hexdigest()
        key = f"{self.prefix}:{endpoint}:{subject_digest}"
        now_ms = int(time.time() * 1000)
        member = f"{now_ms}:{secrets.token_hex(8)}"
        try:
            count = int(
                await self.client.eval(
                    _SLIDING_WINDOW_SCRIPT,
                    1,
                    key,
                    now_ms,
                    self.window_seconds * 1000,
                    self.max_attempts,
                    member,
                )
            )
        except RedisError:
            if self.required:
                raise
            logger.warning("Shared auth limiter check failed; falling back to route-local limiter", exc_info=True)
            return True, 0
        return count <= self.max_attempts, count


class DistributedAuthRateLimitMiddleware:
    def __init__(self, app: ASGIApp, *, limiter: RedisAuthRateLimiter) -> None:
        self.app = app
        self.limiter = limiter
        self.max_body_bytes = _bounded_int("AUTH_RATE_LIMIT_BODY_MAX_BYTES", 65536, 4096, 1048576)

    @staticmethod
    def _subject(endpoint: str, body: bytes, scope: Scope) -> str:
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        amo = str(payload.get("amo_slug") or "").strip().lower()
        if endpoint == "login":
            identity = str(
                payload.get("identifier")
                or payload.get("email")
                or payload.get("staff_code")
                or ""
            ).strip().lower()
            if identity:
                return f"{amo}|{identity}"
        elif endpoint == "password-reset-request":
            identity = str(payload.get("email") or "").strip().lower()
            if identity:
                return f"{amo}|{identity}"
        elif endpoint == "password-reset-confirm":
            token = str(payload.get("token") or "").strip()
            if token:
                return f"reset-token|{token}"

        client = scope.get("client")
        return f"client|{client[0] if client else 'unknown'}"

    async def _read_request(self, receive: Receive) -> tuple[bytes, list[Message]]:
        body = bytearray()
        messages: list[Message] = []
        while True:
            message = await receive()
            messages.append(message)
            if message.get("type") != "http.request":
                break
            chunk = message.get("body", b"")
            if chunk:
                body.extend(chunk)
                if len(body) > self.max_body_bytes:
                    break
            if not message.get("more_body", False):
                break
        return bytes(body), messages

    @staticmethod
    async def _respond(send: Send, status: int, detail: str, *, retry_after: int | None = None) -> None:
        payload = json.dumps(
            {
                "detail": detail,
                "error_code": "AUTH_RATE_LIMITED" if status == 429 else "AUTH_RATE_LIMIT_UNAVAILABLE",
                "retryable": True,
                "request_accepted": False,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"cache-control", b"no-store"),
            (b"content-length", str(len(payload)).encode("ascii")),
        ]
        if retry_after is not None:
            headers.append((b"retry-after", str(retry_after).encode("ascii")))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": payload})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or str(scope.get("method") or "").upper() != "POST":
            await self.app(scope, receive, send)
            return
        endpoint = _PROTECTED_AUTH_PATHS.get(str(scope.get("path") or ""))
        if not endpoint:
            await self.app(scope, receive, send)
            return

        body, captured = await self._read_request(receive)
        if len(body) > self.max_body_bytes:
            await self._respond(send, 413, "Authentication request body is too large.")
            return

        subject = self._subject(endpoint, body, scope)
        try:
            allowed, _count = await self.limiter.check(endpoint, subject)
        except RedisError:
            await self._respond(
                send,
                503,
                "Authentication protection is temporarily unavailable. Retry shortly.",
                retry_after=2,
            )
            return
        if not allowed:
            await self._respond(
                send,
                429,
                "Too many authentication attempts. Please try again shortly.",
                retry_after=self.limiter.window_seconds,
            )
            return

        index = 0

        async def replay_receive() -> Message:
            nonlocal index
            if index < len(captured):
                message = captured[index]
                index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)


runtime_maintenance = install_runtime_concurrency(core)
auth_rate_limiter = RedisAuthRateLimiter()
app = core.app
app.add_middleware(DistributedAuthRateLimitMiddleware, limiter=auth_rate_limiter)


async def _verify_production_dependencies() -> None:
    await auth_rate_limiter.verify_startup()


async def _close_production_dependencies() -> None:
    await auth_rate_limiter.close()


app.add_event_handler("startup", _verify_production_dependencies)
app.add_event_handler("shutdown", _close_production_dependencies)
