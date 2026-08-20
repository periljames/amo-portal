from __future__ import annotations

import pytest

from amodb.apps.platform import managed_ai_provider_policy as policy
from amodb.apps.platform import saas_providers, saas_services


def test_openai_provider_registry_does_not_offer_model_override() -> None:
    definition = saas_providers.PROVIDERS["openai"]
    assert "model" not in definition.config_fields
    catalog = next(row for row in saas_providers.provider_catalog() if row["provider"] == "openai")
    assert "model" not in catalog["config_fields"]


def test_tenant_provider_list_hides_managed_ai(monkeypatch) -> None:
    monkeypatch.setattr(
        policy,
        "_ORIGINAL_LIST",
        lambda db, *, tenant_id=None: [
            {"provider": "stripe", "category": "BILLING"},
            {"provider": "openai", "category": "AI"},
            {"provider": "azure_openai", "category": "AI"},
        ],
    )
    rows = saas_services.list_provider_credentials(object(), tenant_id="tenant-a")
    assert [row["provider"] for row in rows] == ["stripe"]


def test_managed_ai_credential_resolution_uses_platform_scope(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def original(db, *, provider, tenant_id=None, allow_platform_fallback=True):
        calls.append(
            {
                "provider": provider,
                "tenant_id": tenant_id,
                "allow_platform_fallback": allow_platform_fallback,
            }
        )
        return "credential"

    monkeypatch.setattr(policy, "_ORIGINAL_GET", original)
    assert saas_services.get_provider_credential(
        object(),
        provider="openai",
        tenant_id="tenant-a",
        allow_platform_fallback=True,
    ) == "credential"
    assert calls == [
        {
            "provider": "openai",
            "tenant_id": None,
            "allow_platform_fallback": False,
        }
    ]


def test_tenant_cannot_create_managed_ai_provider_override(monkeypatch) -> None:
    called = False

    def original(*args, **kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(policy, "_ORIGINAL_UPSERT", original)
    with pytest.raises(ValueError, match="platform scoped"):
        saas_services.upsert_provider_credential(
            object(),
            provider="openai",
            payload={"secret": {"api_key": "not-used"}},
            actor_user_id="user-1",
            tenant_id="tenant-a",
        )
    assert called is False


def test_tenant_cannot_probe_platform_ai_credential(monkeypatch) -> None:
    called = False

    def original(*args, **kwargs):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(policy, "_ORIGINAL_HEALTH", original)
    with pytest.raises(ValueError, match="platform scoped"):
        saas_services.enqueue_provider_health(
            object(),
            provider="openai",
            tenant_id="tenant-a",
            actor_user_id="user-1",
        )
    assert called is False
