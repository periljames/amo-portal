from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from . import saas_providers, saas_secrets, saas_services


_INSTALLED = False
_ORIGINAL_UPSERT: Callable[..., dict[str, Any]] | None = None


def _submitted_secret(payload: dict[str, Any]) -> dict[str, Any]:
    secret = payload.get("secret")
    if secret is None:
        return {}
    if not isinstance(secret, dict):
        raise ValueError("secret must be an object")
    return {key: value for key, value in secret.items() if str(value or "").strip()}


def prepare_provider_payload(
    db: Session,
    *,
    provider: str,
    payload: dict[str, Any],
    tenant_id: str | None,
) -> dict[str, Any]:
    """Validate scope inheritance and preserve write-only encrypted secrets.

    Provider forms never read plaintext secrets back into the browser. A partial
    rotation must therefore merge submitted fields with the exact scoped secret
    on the server; replacing the encrypted mapping with only the visible fields
    would silently delete credentials. First-time enabled configurations must
    provide every secret field declared by the provider definition.
    """

    normalized = str(provider or "").strip().lower()
    definition = saas_providers.PROVIDERS.get(normalized)
    if definition is None:
        raise ValueError("Unknown integration provider")

    prepared = dict(payload)
    enabled = bool(prepared.get("enabled", True))
    submitted = _submitted_secret(prepared)
    exact_row = saas_services.get_provider_credential(
        db,
        provider=normalized,
        tenant_id=tenant_id,
        allow_platform_fallback=False,
    )
    platform_row = None
    if tenant_id:
        platform_row = saas_services.get_provider_credential(
            db,
            provider=normalized,
            tenant_id=None,
            allow_platform_fallback=False,
        )

    existing_secret = (
        saas_secrets.decrypt_secret(exact_row.encrypted_secret)
        if exact_row and exact_row.encrypted_secret
        else {}
    )
    if submitted:
        merged_secret = {**existing_secret, **submitted}
        prepared["secret"] = merged_secret
    else:
        merged_secret = existing_secret

    clearing_secret = bool(prepared.get("clear_secret")) and not submitted
    if not enabled:
        return prepared

    if clearing_secret and existing_secret:
        raise ValueError(
            "An enabled provider cannot clear its stored secret. Disable the provider or supply replacement credentials."
        )

    inherited_platform_secret = bool(platform_row and platform_row.encrypted_secret)
    if tenant_id and exact_row is None and inherited_platform_secret and not submitted:
        raise ValueError(
            "Tenant-specific secret values are required before overriding an inherited platform credential."
        )

    missing = [
        field
        for field in definition.secret_fields
        if not str(merged_secret.get(field) or "").strip()
    ]
    if missing:
        raise ValueError(
            "Enabled provider configuration is missing required secret field(s): "
            + ", ".join(missing)
        )

    return prepared


def validate_tenant_provider_override(
    db: Session,
    *,
    provider: str,
    payload: dict[str, Any],
    tenant_id: str | None,
) -> None:
    prepare_provider_payload(
        db,
        provider=provider,
        payload=payload,
        tenant_id=tenant_id,
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
        prepared = prepare_provider_payload(
            db,
            provider=provider,
            payload=payload,
            tenant_id=tenant_id,
        )
        assert _ORIGINAL_UPSERT is not None
        return _ORIGINAL_UPSERT(
            db,
            provider=provider,
            payload=prepared,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
        )

    saas_services.upsert_provider_credential = guarded_upsert_provider_credential
    _INSTALLED = True
