from __future__ import annotations

import time
from contextlib import contextmanager
from threading import RLock
from typing import Any, Iterator, Mapping

import resend
from svix.webhooks import Webhook

from amodb.observability import operation_span, record_provider_call


_SDK_LOCK = RLock()
_DEFAULT_API_URL = "https://api.resend.com"


def _clean_api_key(value: Any) -> str:
    key = str(value or "").strip()
    if not key.startswith("re_") or len(key) < 8:
        raise ValueError("Resend api_key must start with 're_'.")
    return key


def _clean_api_url(value: Any) -> str:
    url = str(value or _DEFAULT_API_URL).strip().rstrip("/")
    if url != _DEFAULT_API_URL:
        raise ValueError("Resend API calls are pinned to https://api.resend.com.")
    return url


@contextmanager
def configured_sdk(*, api_key: str, api_url: str | None = None) -> Iterator[None]:
    """Configure the module-level Resend SDK only for one locked operation.

    The official Python SDK stores its API key in module globals. The lock and
    restoration prevent concurrent tenant sends or key rotations from leaking a
    credential into another request.
    """

    key = _clean_api_key(api_key)
    url = _clean_api_url(api_url)
    with _SDK_LOCK:
        previous_key = resend.api_key
        previous_url = resend.api_url
        resend.api_key = key
        resend.api_url = url
        try:
            yield
        finally:
            resend.api_key = previous_key
            resend.api_url = previous_url


def send_email(
    *,
    api_key: str,
    api_url: str | None,
    from_value: str,
    to_email: str,
    subject: str,
    html: str | None = None,
    text: str | None = None,
    reply_to: str | None = None,
    template_id: str | None = None,
    template_variables: dict[str, str | int] | None = None,
    idempotency_key: str | None = None,
    tags: list[dict[str, str]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not from_value.strip() or not to_email.strip():
        raise ValueError("Resend sender and recipient are required.")
    params: dict[str, Any] = {
        "from": from_value.strip(),
        "to": to_email.strip(),
        "subject": subject.strip(),
    }
    if reply_to and reply_to.strip():
        params["reply_to"] = reply_to.strip()
    if template_id:
        params["template"] = {
            "id": template_id.strip(),
            "variables": template_variables or {},
        }
    else:
        if not html and not text:
            raise ValueError("A Resend template, HTML body, or text body is required.")
        if html:
            params["html"] = html
        if text:
            params["text"] = text
    if tags:
        params["tags"] = tags
    if attachments:
        params["attachments"] = [
            {
                "filename": str(item["filename"]),
                "content": list(bytes(item["content"])),
                "content_type": str(item.get("content_type") or "application/octet-stream"),
            }
            for item in attachments
        ]

    options: dict[str, Any] | None = None
    if idempotency_key:
        options = {"idempotency_key": idempotency_key[:256]}

    started = time.perf_counter()
    outcome = "ERROR"
    try:
        with operation_span("provider.resend.send", provider="RESEND", operation="SEND"):
            with configured_sdk(api_key=api_key, api_url=api_url):
                response = resend.Emails.send(params, options)
        message_id = str(response.get("id") or "").strip()
        if not message_id:
            raise RuntimeError("Resend accepted the request without returning an email id.")
        outcome = "SUCCESS"
        return {"provider": "resend", "message_id": message_id}
    finally:
        record_provider_call(
            provider="RESEND",
            operation="SEND",
            status=outcome,
            duration_seconds=time.perf_counter() - started,
        )


def check_api_key(*, api_key: str, api_url: str | None = None) -> dict[str, Any]:
    """Validate authentication without sending an email.

    Full-access keys can list domains. Sending-only keys may return a permission
    response; that still proves the key authenticated, while an explicit test
    email remains the authoritative end-to-end delivery check.
    """

    started = time.perf_counter()
    outcome = "ERROR"
    try:
        with operation_span("provider.resend.health", provider="RESEND", operation="HEALTH"):
            with configured_sdk(api_key=api_key, api_url=api_url):
                try:
                    response = resend.Domains.list()
                except Exception as exc:
                    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                    text = str(exc)
                    if str(code) == "403" or "permission" in text.lower() or "restricted" in text.lower():
                        outcome = "SUCCESS"
                        return {
                            "ok": True,
                            "provider": "resend",
                            "credential_status": "AUTHENTICATED",
                            "access": "sending_only_or_restricted",
                            "detail": "The key authenticated but cannot list domains. Run an explicit test email to confirm sending.",
                        }
                    raise RuntimeError(f"Resend API key health check failed: {text}") from exc
        domains = response.get("data") if isinstance(response, dict) else None
        outcome = "SUCCESS"
        return {
            "ok": True,
            "provider": "resend",
            "credential_status": "AUTHENTICATED",
            "access": "full",
            "domain_count": len(domains or []),
            "detail": "Resend authentication and domain API access passed. Run an explicit test email to confirm delivery.",
        }
    finally:
        record_provider_call(
            provider="RESEND",
            operation="HEALTH",
            status=outcome,
            duration_seconds=time.perf_counter() - started,
        )


def verify_webhook(*, payload: bytes, headers: Mapping[str, str], signing_secret: str) -> dict[str, Any]:
    secret = str(signing_secret or "").strip()
    if not secret:
        raise ValueError("Resend webhook signing secret is not configured.")
    try:
        raw_payload = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Resend webhook payload must be valid UTF-8 JSON.") from exc
    verified = Webhook(secret).verify(raw_payload, dict(headers))
    if not isinstance(verified, dict):
        raise ValueError("Resend webhook payload must be a JSON object.")
    return verified
