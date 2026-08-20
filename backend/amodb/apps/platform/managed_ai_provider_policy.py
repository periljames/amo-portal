from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from . import saas_providers, saas_services


MANAGED_AI_PROVIDERS = frozenset({"openai", "azure_openai"})

_INSTALLED = False
_ORIGINAL_GET: Callable[..., Any] | None = None
_ORIGINAL_LIST: Callable[..., list[dict[str, Any]]] | None = None
_ORIGINAL_UPSERT: Callable[..., dict[str, Any]] | None = None
_ORIGINAL_HEALTH: Callable[..., Any] | None = None


def is_managed_ai_provider(provider: str) -> bool:
    return str(provider or "").strip().lower() in MANAGED_AI_PROVIDERS


def _install_provider_catalog_boundary() -> None:
    """Remove model selection from generic provider configuration.

    Provider credentials describe how the portal authenticates to OpenAI. Model
    selection belongs exclusively to the governed AI catalogue and tenant policy,
    so the legacy generic ``model`` field must not appear as a second source of
    truth in the superadmin provider form.
    """
    definitions = []
    for definition in saas_providers._PROVIDER_DEFINITIONS:
        if definition.code != "openai":
            definitions.append(definition)
            continue
        definitions.append(
            saas_providers.ProviderDefinition(
                code=definition.code,
                display_name=definition.display_name,
                category=definition.category,
                secret_fields=definition.secret_fields,
                config_fields=tuple(
                    field for field in definition.config_fields if field != "model"
                ),
                description=(
                    "Platform-managed OpenAI credential for governed AI workflows. "
                    "Models are selected by the AI catalogue and tenant entitlement."
                ),
            )
        )
    saas_providers._PROVIDER_DEFINITIONS = tuple(definitions)
    saas_providers.PROVIDERS = {
        definition.code: definition for definition in saas_providers._PROVIDER_DEFINITIONS
    }


def install_managed_ai_provider_policy() -> None:
    """Keep portal-billed AI credentials platform-owned and tenant-safe.

    Managed AI is sold as a portal entitlement with per-tenant metering. Tenant
    provider overrides would create an implicit BYOK mode and could cause double
    billing. Until BYOK has its own explicit billing contract, AI credentials are
    therefore platform scoped, hidden from tenant provider lists, and unavailable
    through tenant-scoped health/update operations.
    """
    global _INSTALLED, _ORIGINAL_GET, _ORIGINAL_LIST, _ORIGINAL_UPSERT, _ORIGINAL_HEALTH
    if _INSTALLED:
        return

    _install_provider_catalog_boundary()
    _ORIGINAL_GET = saas_services.get_provider_credential
    _ORIGINAL_LIST = saas_services.list_provider_credentials
    _ORIGINAL_UPSERT = saas_services.upsert_provider_credential
    _ORIGINAL_HEALTH = saas_services.enqueue_provider_health

    def managed_get_provider_credential(
        db: Session,
        *,
        provider: str,
        tenant_id: str | None = None,
        allow_platform_fallback: bool = True,
    ):
        assert _ORIGINAL_GET is not None
        if tenant_id and is_managed_ai_provider(provider):
            return _ORIGINAL_GET(
                db,
                provider=provider,
                tenant_id=None,
                allow_platform_fallback=False,
            )
        return _ORIGINAL_GET(
            db,
            provider=provider,
            tenant_id=tenant_id,
            allow_platform_fallback=allow_platform_fallback,
        )

    def managed_list_provider_credentials(
        db: Session,
        *,
        tenant_id: str | None = None,
    ) -> list[dict[str, Any]]:
        assert _ORIGINAL_LIST is not None
        rows = _ORIGINAL_LIST(db, tenant_id=tenant_id)
        if not tenant_id:
            return rows
        return [
            row
            for row in rows
            if not is_managed_ai_provider(str(row.get("provider") or ""))
        ]

    def managed_upsert_provider_credential(
        db: Session,
        *,
        provider: str,
        payload: dict[str, Any],
        actor_user_id: str,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        assert _ORIGINAL_UPSERT is not None
        if tenant_id and is_managed_ai_provider(provider):
            raise ValueError(
                "Managed AI provider credentials are platform scoped. Configure tenant AI through its entitlement, model tier and budget instead."
            )
        return _ORIGINAL_UPSERT(
            db,
            provider=provider,
            payload=payload,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
        )

    def managed_enqueue_provider_health(
        db: Session,
        *,
        provider: str,
        tenant_id: str | None,
        actor_user_id: str,
    ):
        assert _ORIGINAL_HEALTH is not None
        if tenant_id and is_managed_ai_provider(provider):
            raise ValueError(
                "Managed AI provider health is platform scoped and cannot be probed through a tenant credential context."
            )
        return _ORIGINAL_HEALTH(
            db,
            provider=provider,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
        )

    saas_services.get_provider_credential = managed_get_provider_credential
    saas_services.list_provider_credentials = managed_list_provider_credentials
    saas_services.upsert_provider_credential = managed_upsert_provider_credential
    saas_services.enqueue_provider_health = managed_enqueue_provider_health
    _INSTALLED = True
