from __future__ import annotations

from typing import Any

from amodb.apps.ai.config import get_ai_configuration

from .saas_providers import ProviderDefinition, PROVIDERS


_LABELS = {
    "api_key": "API key", "api_base_url": "API base URL", "default_model": "Default chat model",
    "lightweight_model": "Lightweight model", "embedding_model": "Embedding model", "project": "Project ID",
    "organization": "Organization ID", "webhook_secret": "Webhook signing secret", "consumer_key": "Consumer key",
    "consumer_secret": "Consumer secret", "callback_url": "Callback URL", "client_id": "Client ID",
    "client_secret": "Client secret", "from_email": "From email", "from_name": "From name",
    "use_tls": "Use TLS", "use_ssl": "Use SSL", "allow_self_signed": "Allow self-signed certificate",
    "api_version": "API version", "api_token": "API token", "base_url": "Base URL", "project_key": "Project key",
}
_BOOLEANS = {"certified", "use_tls", "use_ssl", "allow_self_signed"}
_URLS = {"api_base_url", "callback_url", "endpoint", "base_url", "success_url", "cancel_url"}


def _field(name: str, *, source: str, required: bool = False, advanced: bool = False,
           default: Any = None, options: list[dict[str, str]] | None = None) -> dict[str, Any]:
    control = (
        "select" if options else "toggle" if name in _BOOLEANS else "password" if source == "secret"
        else "url" if name in _URLS else "number" if name == "port" else "text"
    )
    return {
        "name": name, "label": _LABELS.get(name, name.replace("_", " ").title()),
        "source": source, "control": control, "required": required, "advanced": advanced,
        "default": default, "options": options or [],
    }


def provider_setup_schema(provider: str, definition: ProviderDefinition | None = None) -> dict[str, Any]:
    """Backend-owned, non-secret contract for rendering a guided provider form."""
    normalized = str(provider or "").strip().lower()
    definition = definition or PROVIDERS.get(normalized)
    if not definition:
        raise ValueError("Unknown provider")
    if normalized == "openai":
        ai = get_ai_configuration()
        chat = [{"value": model, "label": model} for model in ai.allowed_chat_models]
        embeddings = [{"value": model, "label": model} for model in ai.allowed_embedding_models]
        return {
            "mode": "guided",
            "summary": "Add the API key; approved model choices and safe defaults come from the backend.",
            "fields": [
                _field("api_key", source="secret", required=True),
                _field("default_model", source="config", required=True, default=ai.default_model, options=chat),
                _field("lightweight_model", source="config", required=True, default=ai.lightweight_model, options=chat),
                _field("embedding_model", source="config", required=True, default=ai.embedding_model, options=embeddings),
                _field("api_base_url", source="config", advanced=True, default=ai.openai_api_base_url),
                _field("project", source="config", advanced=True),
                _field("organization", source="config", advanced=True),
            ],
        }
    environment = (
        [{"value": "sandbox", "label": "Sandbox"}, {"value": "production", "label": "Production"}]
        if normalized == "mpesa_daraja" else None
    )
    required = {
        "stripe": {"secret_key"}, "mpesa_daraja": {"consumer_key", "consumer_secret", "passkey", "shortcode"},
        "smtp": {"host", "port", "from_email"}, "azure_openai": {"api_key", "endpoint", "deployment", "api_version"},
    }.get(normalized, set(definition.secret_fields[:1]))
    fields = [_field(name, source="secret", required=name in required) for name in definition.secret_fields]
    fields.extend(
        _field(name, source="config", required=name in required,
               options=environment if name == "environment" else None,
               default="sandbox" if name == "environment" else None)
        for name in definition.config_fields
    )
    return {
        "mode": "guided",
        "summary": "Credentials stay encrypted; connection settings are validated by the backend.",
        "fields": fields,
    }
