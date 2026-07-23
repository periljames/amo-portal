from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from . import saas_services


_INSTALLED = False
_ORIGINAL_UPSERT: Callable[..., dict[str, Any]] | None = None


def _nonempty_secret(payload: dict[str, Any]) -> bool:
    secret = payload.get("secret")
    return isinstance(secret, dict) and any(str(value or "").strip() for value in secret.values())


def validate_tenant_provider_override(
    db: Session,
    *,
    provider: str,
    payload: dict[str, Any],
    tenant_id: str | None,
) -> None:
    """Prevent an enabled tenant override from silently dropping inherited secrets.

    A tenant-specific credential row takes precedence over the platform default.
    Creating or re-enabling that row without its own secret would therefore make
    the integration appear configured while removing the credential used by the
    inherited provider. Disabling an inherited provider is allowed and produces
    an explicit disabled tenant override.
    """

    if not tenant_id or not bool(payload.get("enabled", True)):
        return

    normalized = str(provider or "").strip().lower()
    tenant_row = saas_services.get_provider_credential(
        db,
        provider=normalized,
        tenant_id=tenant_id,
        allow_platform_fallback=False,
    )
    platform_row = saas_services.get_provider_credential(
        db,
        provider=normalized,
        tenant_id=None,
        allow_platform_fallback=False,
    )

    existing_tenant_secret = bool(tenant_row and tenant_row.encrypted_secret)
    inherited_platform_secret = bool(platform_row and platform_row.encrypted_secret)
    clearing_secret = bool(payload.get("clear_secret")) and not _nonempty_secret(payload)

    if clearing_secret and existing_tenant_secret:
        raise ValueError(
            "An enabled tenant provider cannot clear its stored secret. Disable the provider or supply replacement tenant credentials."
        )

    if inherited_platform_secret and not existing_tenant_secret and not _nonempty_secret(payload):
        raise ValueError(
            "Tenant-specific secret values are required before overriding an inherited platform credential."
        )


def install_tenant_provider_override_policy() -> None:
    global _INSTALLED, _ORIGINAL_UPSERT
    if _INSTALLED:
        return

    _ORIGINAL_UPSERT = saas_services.upsert_provider_credential

    def guarded_upsert_provider_credential(
        db: Session,
        *,
        provider: str,
        payload: dict[str, Any],
        actor_user_id: str,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        validate_tenant_provider_override(
            db,
            provider=provider,
            payload=payload,
            tenant_id=tenant_id,
        )
        assert _ORIGINAL_UPSERT is not None
        return _ORIGINAL_UPSERT(
            db,
            provider=provider,
            payload=payload,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
        )

    saas_services.upsert_provider_credential = guarded_upsert_provider_credential
    _INSTALLED = True
