from __future__ import annotations

import html
import json
import os
import re
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session


class EmailDeliveryBlocked(RuntimeError):
    """Email is intentionally blocked by portal delivery controls."""


class EmailProvider:
    def send(
        self,
        *,
        template_key: str,
        recipient: str,
        subject: str,
        context: dict[str, Any],
        correlation_id: str | None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class NoopProvider(EmailProvider):
    def send(
        self,
        *,
        template_key: str,
        recipient: str,
        subject: str,
        context: dict[str, Any],
        correlation_id: str | None,
    ) -> dict[str, Any]:
        return {"provider": "none", "skipped": True}


def _environment() -> str:
    return (os.getenv("APP_ENV") or os.getenv("ENV") or "development").strip().lower()


def _template_map(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(item).strip() for key, item in value.items() if str(item).strip()}
    raw = str(value or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("template_map_json must contain a valid JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValueError("template_map_json must contain a JSON object")
    return {str(key): str(item).strip() for key, item in parsed.items() if str(item).strip()}


def _template_variables(context: dict[str, Any]) -> dict[str, str | int]:
    variables: dict[str, str | int] = {}
    for key, value in (context or {}).items():
        clean_key = re.sub(r"[^A-Za-z0-9_]", "_", str(key))[:50]
        if not clean_key or clean_key.startswith("_") or value is None:
            continue
        if isinstance(value, bool):
            variables[clean_key] = "true" if value else "false"
        elif isinstance(value, int) and abs(value) <= 2**53 - 1:
            variables[clean_key] = value
        elif isinstance(value, (str, float)):
            variables[clean_key] = str(value)[:2000]
    return variables


def _fallback_content(template_key: str, subject: str, context: dict[str, Any]) -> tuple[str, str]:
    rows: list[str] = []
    text_rows: list[str] = []
    for key, value in (context or {}).items():
        if str(key).startswith("_") or value in (None, "", [], {}):
            continue
        label = str(key).replace("_", " ").strip().title()
        display = str(value)
        rows.append(
            f"<tr><th style='text-align:left;padding:6px 12px 6px 0'>{html.escape(label)}</th>"
            f"<td style='padding:6px 0'>{html.escape(display)}</td></tr>"
        )
        text_rows.append(f"{label}: {display}")
    action_url = str((context or {}).get("action_url") or "").strip()
    action = (
        f"<p><a href='{html.escape(action_url, quote=True)}' "
        "style='display:inline-block;padding:10px 16px;background:#1f4b99;color:#fff;text-decoration:none;border-radius:4px'>"
        "Open in AMO Portal</a></p>"
        if action_url.startswith(("https://", "http://"))
        else ""
    )
    html_body = (
        "<!doctype html><html><body style='font-family:Arial,sans-serif;color:#172033'>"
        f"<h2>{html.escape(subject)}</h2>"
        f"<p>Portal notification: <strong>{html.escape(template_key)}</strong></p>"
        f"<table>{''.join(rows)}</table>{action}"
        "<p style='font-size:12px;color:#667085'>This automated message was sent by AMO Portal.</p>"
        "</body></html>"
    )
    text_body = "\n".join([subject, f"Portal notification: {template_key}", *text_rows, action_url]).strip()
    return html_body, text_body


class ResendProvider(EmailProvider):
    def __init__(
        self,
        *,
        secret: dict[str, Any],
        config: dict[str, Any],
        credential_status: str,
        tenant_id: str | None = None,
    ):
        self.secret = dict(secret or {})
        self.config = dict(config or {})
        self.credential_status = str(credential_status or "").strip().upper()
        self.tenant_id = str(tenant_id or "platform")

    def send(
        self,
        *,
        template_key: str,
        recipient: str,
        subject: str,
        context: dict[str, Any],
        correlation_id: str | None,
    ) -> dict[str, Any]:
        from amodb.apps.platform.resend_adapter import send_email

        mode = str(self.config.get("sending_mode") or "DISABLED").strip().upper()
        if mode == "DISABLED":
            raise EmailDeliveryBlocked("Outbound email is disabled in the Resend configuration")
        if self.credential_status != "HEALTHY":
            raise EmailDeliveryBlocked(
                "Automatic Resend delivery is blocked until the current API key passes a health check or explicit test email"
            )
        if mode == "PRODUCTION" and _environment() not in {"production", "prod"}:
            raise EmailDeliveryBlocked("Production email is blocked outside a production deployment")

        effective_recipient = recipient.strip()
        if mode == "SANDBOX":
            effective_recipient = str(self.config.get("sandbox_recipient") or "").strip()
            if not effective_recipient:
                raise EmailDeliveryBlocked("Sandbox mode requires sandbox_recipient")

        api_key = str(self.secret.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("Resend api_key is not configured")
        from_email = str(self.config.get("from_email") or "onboarding@resend.dev").strip()
        from_name = str(self.config.get("from_name") or "AMO Portal").strip()
        from_value = f"{from_name} <{from_email}>" if from_name else from_email
        mapping = _template_map(self.config.get("template_map_json"))
        template_id = mapping.get(template_key)
        variables = _template_variables(context)
        html_body: str | None = None
        text_body: str | None = None
        if not template_id:
            html_body, text_body = _fallback_content(template_key, subject, context)

        result = send_email(
            api_key=api_key,
            api_url=str(self.config.get("api_base_url") or "https://api.resend.com"),
            from_value=from_value,
            to_email=effective_recipient,
            subject=subject,
            html=html_body,
            text=text_body,
            reply_to=str(self.config.get("reply_to") or "").strip() or None,
            template_id=template_id,
            template_variables=variables if template_id else None,
            idempotency_key=correlation_id or f"{template_key}:{effective_recipient}",
            tags=[
                {"name": "source", "value": "amo_portal"},
                {"name": "tenant_id", "value": re.sub(r"[^A-Za-z0-9_-]", "_", self.tenant_id)[:256]},
                {"name": "template", "value": re.sub(r"[^A-Za-z0-9_-]", "_", template_key)[:256]},
                {"name": "email_class", "value": str(context.get("_email_class") or "ROUTINE")[:256]},
            ],
        )
        return {
            **result,
            "mode": mode,
            "recipient": effective_recipient,
            "original_recipient": recipient,
            "template_id": template_id,
        }


def get_email_provider(*, db: Session, amo_id: str | None) -> tuple[EmailProvider, bool]:
    """Resolve the current encrypted Resend credential for every send.

    No credential is cached. A rotated key is therefore used immediately by the
    next notification, while already-running requests keep only their local copy.
    """

    from amodb.apps.platform import saas_services

    # Inspect through the session connection. Inspecting the Engine can borrow
    # and roll back the same DBAPI connection used by an in-memory SQLite
    # transaction, discarding the queued email log before it is updated.
    if not inspect(db.connection()).has_table("saas_provider_credentials"):
        return NoopProvider(), False

    row = saas_services.get_provider_credential(
        db,
        provider="resend",
        tenant_id=amo_id,
        allow_platform_fallback=True,
    )
    if row is None or str(row.status or "").strip().upper() == "DISABLED":
        return NoopProvider(), False
    return (
        ResendProvider(
            secret=saas_services.provider_secrets(row),
            config=row.config_json or {},
            credential_status=str(row.status or ""),
            tenant_id=amo_id,
        ),
        True,
    )
