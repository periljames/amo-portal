from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from amodb.apps.notifications import providers as notification_providers
from amodb.apps.platform import resend_email_policy, saas_admin_policy, saas_services


def test_initial_resend_setup_requires_api_key_but_not_webhook_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        saas_admin_policy.saas_services,
        "get_provider_credential",
        lambda db, *, provider, tenant_id, allow_platform_fallback: None,
    )

    prepared = saas_admin_policy.prepare_provider_payload(
        MagicMock(),
        provider="resend",
        tenant_id=None,
        payload={"enabled": True, "secret": {"api_key": "re_test_key"}},
    )

    assert prepared["secret"] == {"api_key": "re_test_key"}


def test_initial_resend_setup_rejects_missing_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        saas_admin_policy.saas_services,
        "get_provider_credential",
        lambda db, *, provider, tenant_id, allow_platform_fallback: None,
    )

    with pytest.raises(ValueError, match="api_key"):
        saas_admin_policy.prepare_provider_payload(
            MagicMock(),
            provider="resend",
            tenant_id=None,
            payload={"enabled": True, "secret": {"webhook_signing_secret": "whsec_test"}},
        )


def test_resend_tenant_override_is_blocked():
    with pytest.raises(ValueError, match="platform-wide credential"):
        saas_services.upsert_provider_credential(
            MagicMock(),
            provider="resend",
            payload={"enabled": True, "secret": {"api_key": "re_test_key"}},
            actor_user_id="tenant-admin",
            tenant_id="amo-1",
        )


def test_production_mode_requires_production_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "staging")
    with pytest.raises(ValueError, match="outside a production deployment"):
        resend_email_policy._normalise_resend_payload(
            {
                "config": {
                    "sending_mode": "PRODUCTION",
                    "from_email": "notifications@example.com",
                },
                "production_confirmation": resend_email_policy.PRODUCTION_CONFIRMATION,
            }
        )


def test_automatic_delivery_requires_healthy_credential():
    provider = notification_providers.ResendProvider(
        secret={"api_key": "re_test_key"},
        config={
            "sending_mode": "SANDBOX",
            "sandbox_recipient": "sandbox@example.com",
        },
        credential_status="CONFIGURED",
    )

    with pytest.raises(notification_providers.EmailDeliveryBlocked, match="health check"):
        provider.send(
            template_key="finding-issued",
            recipient="recipient@example.com",
            subject="Finding issued",
            context={},
            correlation_id="finding:1",
        )
