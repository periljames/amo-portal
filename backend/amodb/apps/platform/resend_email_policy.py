from __future__ import annotations

import json
import os
import re
import time
import uuid
from email.utils import getaddresses
from typing import Any

from . import saas_models, saas_providers, saas_queue, saas_services
from .resend_adapter import check_api_key


LEGACY_EMAIL_PROVIDERS = frozenset({"smtp", "sendgrid", "ses", "mailgun", "postmark", "custom_http"})
PRODUCTION_CONFIRMATION = "ENABLE RESEND PRODUCTION"
RESEND_API_URL = "https://api.resend.com"
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
        "tenant_default_sender_domain",
        "verified_sender_domains",
        "tenant_sender_domain_assignments_json",
    ),
    "Transactional and automated portal email through Resend, with encrypted credentials, templates, delivery controls and signed webhooks.",
)

_INSTALLED = False


def _environment() -> str:
    return (os.getenv("APP_ENV") or os.getenv("ENV") or "development").strip().lower()


def status_after_authentication(current_status: str, result: dict[str, Any]) -> str:
    """A non-sending API probe cannot grant delivery-ready status."""

    current = str(current_status or "").strip().upper()
    if current == "HEALTHY":
        return "HEALTHY"
    candidate = str(result.get("credential_status") or "AUTHENTICATED").strip().upper()
    return candidate if candidate in {"AUTHENTICATED", "HEALTHY"} else "AUTHENTICATED"


def process_resend_authentication_job(db, job) -> dict[str, Any]:
    payload = dict(job.payload_json or {})
    credential_id = str(payload.get("credential_id") or "").strip()
    credential = db.get(saas_models.SaaSProviderCredential, credential_id)
    if credential is None or str(credential.provider or "").strip().lower() != "resend":
        raise ValueError("Resend credential was not found")
    current_status = str(credential.status or "").strip().upper()
    if current_status == "DISABLED":
        raise ValueError("Disabled Resend credentials cannot be authenticated")
    if current_status not in {"CONFIGURED", "AUTHENTICATED", "HEALTHY", "UNHEALTHY"}:
        raise ValueError("Resend is not configured for an authentication check")

    started = time.perf_counter()
    try:
        result = saas_providers.check_provider(
            "resend",
            secret=saas_services.provider_secrets(credential),
            config=credential.config_json or {},
        )
    except Exception as exc:
        credential.status = "UNHEALTHY"
        credential.last_checked_at = saas_services.utcnow()
        credential.last_latency_ms = max(0, int(round((time.perf_counter() - started) * 1000)))
        credential.last_health_detail = str(exc)[:2000]
        db.flush()
        raise

    credential.status = status_after_authentication(current_status, result)
    credential.last_checked_at = saas_services.utcnow()
    credential.last_latency_ms = int(
        result.get("latency_ms")
        or max(0, int(round((time.perf_counter() - started) * 1000)))
    )
    credential.last_health_detail = str(
        result.get("detail")
        or "Resend API authentication passed. Send one explicit test email to authorize automatic delivery."
    )[:2000]
    db.flush()
    return result


def _normalise_domains(value: Any) -> list[str]:
    raw = str(value or "").replace(";", ",")
    domains: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        domain = item.strip().lower().lstrip("@")
        if not domain:
            continue
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain) or "." not in domain:
            raise ValueError(f"Invalid sender domain: {domain}")
        if domain not in seen:
            seen.add(domain)
            domains.append(domain)
    return domains


def _tenant_domain_assignments(value: Any) -> dict[str, list[str]]:
    """Platform-approved custom domains, bound to exactly one tenant each."""
    raw = value if isinstance(value, dict) else json.loads(str(value or "{}"))
    if not isinstance(raw, dict):
        raise ValueError("tenant_sender_domain_assignments_json must be a JSON object")
    result: dict[str, list[str]] = {}
    owners: dict[str, str] = {}
    for tenant_id, domains in raw.items():
        key = str(tenant_id).strip()
        if not key or len(key) > 128 or not isinstance(domains, list):
            raise ValueError("Each tenant domain assignment requires a tenant ID and an array of domains")
        cleaned = _normalise_domains(",".join(str(item) for item in domains))
        for domain in cleaned:
            if domain in owners and owners[domain] != key:
                raise ValueError("A custom sending domain cannot be assigned to multiple tenants")
            owners[domain] = key
        result[key] = cleaned
    return result


def _email_domain(value: str) -> str:
    parsed = getaddresses([str(value or "")])
    addresses = [address.strip().lower() for _name, address in parsed if address.strip()]
    if len(addresses) != 1 or "@" not in addresses[0]:
        raise ValueError("from_email must contain one valid mailbox address")
    return addresses[0].rsplit("@", 1)[1]


def _normalise_tenant_resend_payload(
    payload: dict[str, Any],
    *,
    platform_config: dict[str, Any],
    tenant_id: str,
    tenant_slug: str,
) -> dict[str, Any]:
    result = dict(payload or {})
    if result.get("secret") or result.get("clear_secret"):
        raise ValueError("Tenant Resend settings cannot contain API keys or webhook secrets.")
    config = dict(result.get("config") or {})
    allowed_identity_fields = {"from_email", "from_name", "reply_to"}
    unexpected = set(config) - allowed_identity_fields
    if unexpected:
        raise ValueError(
            "Tenant Resend settings may change only from_email, from_name and reply_to: "
            + ", ".join(sorted(unexpected))
        )
    clear_fields = result.get("clear_config_fields") or []
    if not isinstance(clear_fields, list):
        raise ValueError("clear_config_fields must be a list")
    unexpected_clear = set(clear_fields) - allowed_identity_fields
    if unexpected_clear:
        raise ValueError(
            "Tenant Resend settings cannot clear platform transport fields: "
            + ", ".join(sorted(unexpected_clear))
        )

    from amodb.apps.platform.resend_adapter import email_recipients

    if "from_name" in config:
        config["from_name"] = str(config.get("from_name") or "").strip()[:255]
    if str(config.get("reply_to") or "").strip():
        config["reply_to"] = ", ".join(email_recipients(str(config["reply_to"])))

    if str(config.get("from_email") or "").strip():
        sender = email_recipients(str(config["from_email"]))
        if len(sender) != 1:
            raise ValueError("Tenant from_email must contain exactly one mailbox.")
        address = getaddresses(sender)[0][1].strip().lower()
        sender_domain = _email_domain(address)
        platform_sender = str(platform_config.get("from_email") or "").strip()
        allowed = set(_normalise_domains(platform_config.get("verified_sender_domains")))
        if platform_sender:
            allowed.add(_email_domain(platform_sender))
        default_domain = str(platform_config.get("tenant_default_sender_domain") or "").strip().lower()
        if default_domain:
            allowed.add(default_domain)
        shared_domain = str(platform_config.get("tenant_default_sender_domain") or "").strip().lower()
        if not shared_domain and platform_sender:
            shared_domain = _email_domain(platform_sender)
        slug = re.sub(r"[^a-z0-9]+", ".", str(tenant_slug).lower()).strip(".")
        shared_sender = f"quality.{slug}@{shared_domain}" if slug and shared_domain else ""
        assignments = _tenant_domain_assignments(platform_config.get("tenant_sender_domain_assignments_json"))
        if sender_domain == shared_domain:
            if address != shared_sender:
                raise ValueError("The shared Venspera sender address is reserved for this tenant's own identity.")
        elif sender_domain not in assignments.get(str(tenant_id), []):
            raise ValueError("This custom sender domain has not been assigned to your tenant by Venspera.")
        if sender_domain not in allowed:
            raise ValueError(
                f"Sender domain {sender_domain} is not approved for sending. "
                "Verify it in Resend and register it in verified_sender_domains."
            )
        config["from_email"] = address

    result["config"] = config
    result.pop("production_confirmation", None)
    return result


def _normalise_resend_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload or {})
    config = dict(result.get("config") or {})
    mode = str(config.get("sending_mode") or "DISABLED").strip().upper()
    if mode not in {"DISABLED", "SANDBOX", "PRODUCTION"}:
        raise ValueError("sending_mode must be DISABLED, SANDBOX or PRODUCTION")

    api_base_url = str(config.get("api_base_url") or RESEND_API_URL).strip().rstrip("/")
    if api_base_url != RESEND_API_URL:
        raise ValueError("Resend API calls are pinned to https://api.resend.com")
    config["api_base_url"] = RESEND_API_URL
    config["sending_mode"] = mode
    config["from_name"] = str(config.get("from_name") or "AMO Portal").strip()
    if str(config.get("from_email") or "").strip():
        _email_domain(str(config["from_email"]))
    platform_sender_domain = (
        _email_domain(str(config.get("from_email") or ""))
        if str(config.get("from_email") or "").strip()
        else ""
    )
    default_sender_domain = str(config.get("tenant_default_sender_domain") or platform_sender_domain).strip().lower()
    if default_sender_domain:
        _normalise_domains(default_sender_domain)
        config["tenant_default_sender_domain"] = default_sender_domain
    config["verified_sender_domains"] = ", ".join(_normalise_domains(config.get("verified_sender_domains")))
    assigned_domains = _tenant_domain_assignments(config.get("tenant_sender_domain_assignments_json"))
    permitted_domains = set(_normalise_domains(config.get("verified_sender_domains")))
    for tenant_domains in assigned_domains.values():
        if not set(tenant_domains).issubset(permitted_domains):
            raise ValueError("Tenant custom domains must also appear in verified_sender_domains.")
    config["tenant_sender_domain_assignments_json"] = json.dumps(assigned_domains, sort_keys=True)
    config["per_minute_limit"] = int(config.get("per_minute_limit") or 10)
    config["daily_limit"] = int(config.get("daily_limit") or 500)
    if not 1 <= config["per_minute_limit"] <= 60:
        raise ValueError("per_minute_limit must be between 1 and 60")
    if not 1 <= config["daily_limit"] <= 100000:
        raise ValueError("daily_limit must be between 1 and 100000")

    if mode == "SANDBOX" and not str(config.get("sandbox_recipient") or "").strip():
        raise ValueError("sandbox_recipient is required while sending_mode is SANDBOX")
    if mode == "SANDBOX":
        from .resend_adapter import email_recipients
        config["sandbox_recipient"] = ", ".join(email_recipients(str(config["sandbox_recipient"])))
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
    original_enqueue_health = saas_services.enqueue_provider_health

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
                api_url=str(config.get("api_base_url") or RESEND_API_URL),
            )
        return original_check(normalized, secret=secret, config=config)

    def list_provider_credentials(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            item
            for item in original_list(*args, **kwargs)
            if str(item.get("provider") or "").lower() not in LEGACY_EMAIL_PROVIDERS
        ]

    def guarded_upsert_provider_credential(
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
        if normalized == "resend" and tenant_id is not None:
            platform_row = saas_services.get_provider_credential(
                db,
                provider="resend",
                tenant_id=None,
                allow_platform_fallback=False,
            )
            if platform_row is None:
                raise ValueError("Platform Resend transport must be configured before tenant sender identity.")
            from amodb.apps.accounts import models as account_models
            tenant = db.get(account_models.AMO, tenant_id)
            if tenant is None:
                raise ValueError("Tenant not found")
            effective_payload = _normalise_tenant_resend_payload(
                payload,
                platform_config=dict(platform_row.config_json or {}),
                tenant_id=str(tenant_id),
                tenant_slug=str(tenant.login_slug or tenant.amo_code or ""),
            )
            return original_upsert(
                db,
                provider=normalized,
                payload=effective_payload,
                actor_user_id=actor_user_id,
                tenant_id=tenant_id,
            )
        secret_changed = normalized == "resend" and bool((payload or {}).get("secret"))
        effective_payload = _normalise_resend_payload(payload) if normalized == "resend" else payload
        response = original_upsert(
            db,
            provider=normalized,
            payload=effective_payload,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
        )
        if normalized == "resend":
            row = saas_services.get_provider_credential(
                db,
                provider="resend",
                tenant_id=None,
                allow_platform_fallback=False,
            )
            if row is not None:
                row.status = "CONFIGURED"
                row.last_checked_at = None
                row.last_latency_ms = None
                row.last_health_detail = (
                    "API key changed; authenticate the key and send one explicit test email."
                    if secret_changed
                    else "Configuration changed; authenticate the key and send one explicit test email."
                )
                db.commit()
                db.refresh(row)
                return saas_services.provider_payload(row)
        return response

    def enqueue_provider_health(
        db,
        *,
        provider: str,
        tenant_id: str | None,
        actor_user_id: str,
    ):
        normalized = str(provider or "").strip().lower()
        if normalized != "resend":
            return original_enqueue_health(
                db,
                provider=normalized,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
            )
        if tenant_id is not None:
            raise ValueError("Resend is a platform-wide credential and can only be checked by a platform superuser")
        row = saas_services.get_provider_credential(
            db,
            provider="resend",
            tenant_id=None,
            allow_platform_fallback=False,
        )
        if row is None:
            raise ValueError("Resend is not configured")
        current_status = str(row.status or "").strip().upper()
        if current_status == "DISABLED":
            raise ValueError("Disabled providers cannot be authenticated")
        if current_status not in {"CONFIGURED", "AUTHENTICATED", "HEALTHY", "UNHEALTHY"}:
            raise ValueError("Resend is not configured for an authentication check")
        return saas_queue.enqueue_job(
            db,
            job_type="PROVIDER_HEALTH_CHECK",
            queue_name="integrations",
            tenant_id=None,
            payload={
                "provider": "resend",
                "credential_id": row.id,
                "mutate_credential_status": False,
                "credential_scope": saas_services.provider_scope(row.tenant_id),
            },
            idempotency_key=f"health:{row.id}:{saas_services.utcnow().strftime('%Y%m%d%H%M')}",
            correlation_id=str(uuid.uuid4()),
            created_by=actor_user_id,
            max_attempts=3,
        )

    saas_providers.provider_catalog = provider_catalog
    saas_providers.check_provider = check_provider
    saas_services.list_provider_credentials = list_provider_credentials
    saas_services.upsert_provider_credential = guarded_upsert_provider_credential
    saas_services.enqueue_provider_health = enqueue_provider_health
