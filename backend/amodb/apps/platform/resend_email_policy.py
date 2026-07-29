from __future__ import annotations

import os
from typing import Any, Callable

from . import saas_providers, saas_services
from .resend_adapter import check_api_key


LEGACY_EMAIL_PROVIDERS = frozenset({"smtp", "sendgrid", "ses", "mailgun", "postmark", "custom_http"})
PRODUCTION_CONFIRMATION = "ENABLE RESEND PRODUCTION"
RESEND_DEFINITION = saas_providers.ProviderDefinition(
    "resend",
    "Resend",
    "EMAIL",
    ("api_key", "webhook_signing_secret"),
    (
        "api_base_url",
        "from_email",
        "from_name",
        "reply_to",
        "sending_mode",
        "sandbox_recipient",
        "health_check_recipient",
        "per_minute_limit",
        "daily_limit",
        "template_map_json",
    ),
    "Transactional and automated portal email through Resend, with encrypted credentials, templates, delivery controls and signed webhooks.",
)

_INSTALLED = False


def _environment() -> str:
    return (os.getenv("APP_ENV") or os.getenv("ENV") or "development").strip().lower()


def _normalise_resend_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload or {})
    config = dict(result.get("config") or {})
    mode = str(config.get("sending_mode") or "DISABLED").strip().upper()
    if mode not in {"DISABLED", "SANDBOX", "PRODUCTION"}:
        raise ValueError("sending_mode must be DISABLED, SANDBOX or PRODUCTION")

    config["sending_mode"] = mode
    config["api_base_url"] = str(config.get("api_base_url") or "https://api.resend.com").strip().rstrip("/")
    config["from_name"] = str(config.get("from_name") or "AMO Portal").strip()
    config["per_minute_limit"] = int(config.get("per_minute_limit") or 10)
    config["daily_limit"] = int(config.get("daily_limit") or 500)
    if not 1 <= config["per_minute_limit"] <= 60:
        raise ValueError("per_minute_limit must be between 1 and 60")
    if not 1 <= config["daily_limit"] <= 100000:
        raise ValueError("daily_limit must be between 1 and 100000")

    if mode == "SANDBOX" and not str(config.get("sandbox_recipient") or "").strip():
        raise ValueError("sandbox_recipient is required while sending_mode is SANDBOX")
    if mode == "PRODUCTION":
        if _environment() not in {"production", "prod"}:
            raise ValueError("Production email cannot be enabled outside a production deployment")
        if str(result.get("production_confirmation") or "").strip() != PRODUCTION_CONFIRMATION:
            raise ValueError(f"Type '{PRODUCTION_CONFIRMATION}' to enable production email")
        sender = str(config.get("from_email") or "").strip().lower()
        if not sender or sender.endswith("@resend.dev"):
            raise ValueError("Production mode requires a sender on a verified custom domain")

    if "secret" in result:
        secret = dict(result.get("secret") or {})
        api_key = str(secret.get("api_key") or "").strip()
        if api_key and (not api_key.startswith("re_") or len(api_key) < 8):
            raise ValueError("Resend api_key must start with 're_'")
        webhook_secret = str(secret.get("webhook_signing_secret") or "").strip()
        if webhook_secret and not webhook_secret.startswith("whsec_"):
            raise ValueError("Resend webhook_signing_secret must start with 'whsec_'")
        result["secret"] = secret

    result["config"] = config
    return result


def install_resend_email_provider() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    for code in LEGACY_EMAIL_PROVIDERS:
        saas_providers.PROVIDERS.pop(code, None)
    saas_providers.PROVIDERS["resend"] = RESEND_DEFINITION

    original_catalog = saas_providers.provider_catalog
    original_check = saas_providers.check_provider
    original_list = saas_services.list_provider_credentials
    original_upsert = saas_services.upsert_provider_credential

    def provider_catalog() -> list[dict[str, Any]]:
        items = [item for item in original_catalog() if item.get("provider") not in LEGACY_EMAIL_PROVIDERS]
        if not any(item.get("provider") == "resend" for item in items):
            items.append(
                {
                    "provider": RESEND_DEFINITION.code,
                    "display_name": RESEND_DEFINITION.display_name,
                    "category": RESEND_DEFINITION.category,
                    "secret_fields": list(RESEND_DEFINITION.secret_fields),
                    "config_fields": list(RESEND_DEFINITION.config_fields),
                    "description": RESEND_DEFINITION.description,
                }
            )
        return items

    def check_provider(provider: str, *, secret: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        normalized = str(provider or "").strip().lower()
        if normalized in LEGACY_EMAIL_PROVIDERS:
            raise ValueError("Legacy email providers are disabled; configure Resend instead")
        if normalized == "resend":
            return check_api_key(
                api_key=str(secret.get("api_key") or ""),
                api_url=str(config.get("api_base_url") or "https://api.resend.com"),
            )
        return original_check(normalized, secret=secret, config=config)

    def list_provider_credentials(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            item
            for item in original_list(*args, **kwargs)
            if str(item.get("provider") or "").lower() not in LEGACY_EMAIL_PROVIDERS
        ]

    def upsert_provider_credential(
        db,
        *,
        provider: str,
        payload: dict[str, Any],
        actor_user_id: str,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        normalized = str(provider or "").strip().lower()
        if normalized in LEGACY_EMAIL_PROVIDERS:
            raise ValueError("Legacy email providers are disabled; configure Resend instead")
        secret_changed = normalized == "resend" and bool((payload or {}).get("secret"))
        effective_payload = _normalise_resend_payload(payload) if normalized == "resend" else payload
        response = original_upsert(
            db,
            provider=normalized,
            payload=effective_payload,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
        )
        if normalized == "resend" and secret_changed:
            row = saas_services.get_provider_credential(
                db,
                provider="resend",
                tenant_id=tenant_id,
                allow_platform_fallback=False,
            )
            if row is not None:
                row.status = "CONFIGURED"
                row.last_checked_at = None
                row.last_latency_ms = None
                row.last_health_detail = "API key changed; run a new health check and test email."
                db.commit()
                db.refresh(row)
                return saas_services.provider_payload(row)
        return response

    saas_providers.provider_catalog = provider_catalog
    saas_providers.check_provider = check_provider
    saas_services.list_provider_credentials = list_provider_credentials
    saas_services.upsert_provider_credential = upsert_provider_credential
