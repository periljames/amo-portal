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
        attachments: list[dict[str, Any]] | None = None,
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
        attachments: list[dict[str, Any]] | None = None,
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
    if template_key == "qms_audit_notice_memo":
        recipient = str(context.get("recipient_name") or "Audit recipient").strip()
        role = str(context.get("recipient_role") or "AUDIT_RECIPIENT").replace("_", " ").strip().title()
        audit_ref = str(context.get("audit_ref") or "Controlled audit").strip()
        audit_title = str(context.get("audit_title") or "Audit").strip()
        audit_area = str(context.get("audit_area") or "Defined department / process").strip()
        planned_start = str(context.get("planned_start") or "To be confirmed").strip()
        planned_end = str(context.get("planned_end") or planned_start).strip()
        document_name = str(context.get("notice_document") or "Controlled audit notice.pdf").strip()
        action_url = str(context.get("action_url") or "").strip()
        responsibility = (
            "You are listed as the auditee representative and coordination contact for this department/process audit. "
            "Accountability for the process and records remains with the relevant process owners and responsible managers."
            if role.upper() in {"AUDITEE", "EXTERNAL AUDITEE"}
            else "You are receiving this controlled notice as a member of the audit team."
        )
        details = (
            ("Audit reference", audit_ref),
            ("Audit", audit_title),
            ("Department / process", audit_area),
            ("Planned window", f"{planned_start} to {planned_end}"),
            ("Attached controlled document", document_name),
        )
        rows = "".join(
            f"<tr><th style='text-align:left;padding:6px 12px 6px 0'>{html.escape(label)}</th>"
            f"<td style='padding:6px 0'>{html.escape(value)}</td></tr>"
            for label, value in details
        )
        action = (
            f"<p><a href='{html.escape(action_url, quote=True)}' "
            "style='display:inline-block;padding:10px 16px;background:#1f4b99;color:#fff;text-decoration:none;border-radius:4px'>"
            "Open controlled audit record</a></p>"
            if action_url.startswith(("https://", "http://"))
            else ""
        )
        html_body = (
            "<!doctype html><html><body style='font-family:Arial,sans-serif;color:#172033'>"
            f"<h2>{html.escape(subject)}</h2><p>Dear {html.escape(recipient)},</p>"
            f"<p>{html.escape(responsibility)}</p><table>{rows}</table>{action}"
            "<p>The attached PDF is the issued, electronically signed audit notice. Its QR code opens the controlled "
            "digital record after sign-in.</p>"
            "<p style='font-size:12px;color:#667085'>This controlled notification was sent by AMO Portal.</p>"
            "</body></html>"
        )
        text_body = "\n\n".join([
            subject,
            f"Dear {recipient},",
            responsibility,
            "\n".join(f"{label}: {value}" for label, value in details),
            "The attached PDF is the issued, electronically signed audit notice.",
            action_url,
        ]).strip()
        return html_body, text_body

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
        attachments: list[dict[str, Any]] | None = None,
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

        from amodb.apps.platform.resend_adapter import email_recipients

        effective_recipient = recipient.strip()
        intended_cc = context.get("_cc")
        intended_reply_to = context.get("_reply_to")

        def recipient_rows(value: Any) -> list[str]:
            if value is None:
                return []
            if isinstance(value, (list, tuple, set)):
                combined: list[str] = []
                seen: set[str] = set()
                for item in value:
                    for mailbox in email_recipients(str(item)):
                        key = mailbox.casefold()
                        if key not in seen:
                            seen.add(key)
                            combined.append(mailbox)
                return combined
            return email_recipients(str(value)) if str(value).strip() else []

        configured_reply_to = recipient_rows(self.config.get("reply_to"))
        requested_cc = recipient_rows(intended_cc)
        requested_reply_to = recipient_rows(intended_reply_to)
        if mode == "SANDBOX":
            effective_recipient = str(self.config.get("sandbox_recipient") or "").strip()
            if not effective_recipient:
                raise EmailDeliveryBlocked("Sandbox mode requires sandbox_recipient")
            effective_cc: list[str] = []
            effective_reply_to = recipient_rows(effective_recipient)
        else:
            effective_cc = requested_cc
            effective_reply_to = []
            seen_reply: set[str] = set()
            for mailbox in [*configured_reply_to, *requested_reply_to, *effective_cc]:
                key = mailbox.casefold()
                if key not in seen_reply:
                    seen_reply.add(key)
                    effective_reply_to.append(mailbox)

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
            cc=effective_cc or None,
            reply_to=effective_reply_to or None,
            template_id=template_id,
            template_variables=variables if template_id else None,
            idempotency_key=correlation_id or f"{template_key}:{effective_recipient}",
            tags=[
                {"name": "source", "value": "amo_portal"},
                {"name": "tenant_id", "value": re.sub(r"[^A-Za-z0-9_-]", "_", self.tenant_id)[:256]},
                {"name": "template", "value": re.sub(r"[^A-Za-z0-9_-]", "_", template_key)[:256]},
                {"name": "email_class", "value": str(context.get("_email_class") or "ROUTINE")[:256]},
            ],
            attachments=attachments,
        )
        effective_to = recipient_rows(effective_recipient)
        return {
            **result,
            "mode": mode,
            "recipient": effective_recipient,
            "original_recipient": recipient,
            "cc": effective_cc,
            "reply_to": effective_reply_to,
            "effective_recipients": [*effective_to, *effective_cc],
            "template_id": template_id,
        }


def get_email_provider(*, db: Session, amo_id: str | None) -> tuple[EmailProvider, bool]:
    """Use one platform Resend credential with tenant-scoped sender identity."""

    from amodb.apps.accounts import models as account_models
    from amodb.apps.platform import saas_services

    # Credentials remain platform-owned. Tenant rows can hold only sender
    # identity settings and are deliberately never used as a secret source.
    if not inspect(db.connection()).has_table("saas_provider_credentials"):
        return NoopProvider(), False

    platform_row = saas_services.get_provider_credential(
        db,
        provider="resend",
        tenant_id=None,
        allow_platform_fallback=False,
    )
    if platform_row is None or str(platform_row.status or "").strip().upper() == "DISABLED":
        return NoopProvider(), False

    config = dict(platform_row.config_json or {})
    tenant_config: dict[str, Any] = {}
    tenant = None
    if amo_id:
        tenant_row = saas_services.get_provider_credential(
            db,
            provider="resend",
            tenant_id=amo_id,
            allow_platform_fallback=False,
        )
        if tenant_row is not None and str(tenant_row.status or "").strip().upper() != "DISABLED":
            tenant_config = {
                key: value
                for key, value in dict(tenant_row.config_json or {}).items()
                if key in {"from_email", "from_name", "reply_to"}
            }
            config.update(tenant_config)
        tenant = db.get(account_models.AMO, amo_id)

    if tenant is not None:
        if not str(tenant_config.get("from_name") or "").strip():
            config["from_name"] = str(tenant.name or "AMO Portal").strip()
        if not str(tenant_config.get("from_email") or "").strip():
            default_domain = str(config.get("tenant_default_sender_domain") or "").strip().lower()
            if not default_domain:
                platform_sender = str((platform_row.config_json or {}).get("from_email") or "").strip()
                default_domain = platform_sender.rsplit("@", 1)[-1].lower() if "@" in platform_sender else ""
            slug = re.sub(r"[^a-z0-9]+", ".", str(tenant.login_slug or tenant.amo_code or "tenant").lower()).strip(".")
            if default_domain and slug:
                config["from_email"] = f"quality.{slug}@{default_domain}"
        if not str(tenant_config.get("reply_to") or "").strip():
            quality_users = (
                db.query(account_models.User)
                .filter(
                    account_models.User.amo_id == amo_id,
                    account_models.User.is_active.is_(True),
                    account_models.User.is_system_account.is_(False),
                    account_models.User.role.in_(
                        (
                            account_models.AccountRole.QUALITY_MANAGER,
                            account_models.AccountRole.QUALITY_OFFICER,
                        )
                    ),
                )
                .order_by(account_models.User.role.asc(), account_models.User.email.asc())
                .all()
            )
            replies = [str(user.email or "").strip() for user in quality_users if str(user.email or "").strip()]
            if replies:
                config["reply_to"] = ", ".join(dict.fromkeys(replies))

    return (
        ResendProvider(
            secret=saas_services.provider_secrets(platform_row),
            config=config,
            credential_status=str(platform_row.status or ""),
            tenant_id=amo_id,
        ),
        True,
    )
