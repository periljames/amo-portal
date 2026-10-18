from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from amodb.apps.notifications import providers as notification_providers
from amodb.apps.platform import resend_adapter, resend_email_policy, saas_admin_policy, saas_services
from amodb.jobs import saas_worker_safe


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


def test_tenant_resend_identity_rejects_secrets_and_unassigned_domains():
    config = {
        "from_email": "notifications@notify.venspera.com",
        "tenant_default_sender_domain": "notify.venspera.com",
        "verified_sender_domains": "flysafarilink.com",
        "tenant_sender_domain_assignments_json": '{"tenant-A": ["flysafarilink.com"]}',
    }
    shared = {"platform_config": config, "tenant_id": "tenant-A", "tenant_slug": "safarilink"}
    with pytest.raises(ValueError, match="cannot contain API keys"):
        resend_email_policy._normalise_tenant_resend_payload(
            {"secret": {"api_key": "re_test_key"}, "config": {}}, **shared,
        )
    with pytest.raises(ValueError, match="not been assigned"):
        resend_email_policy._normalise_tenant_resend_payload(
            {"config": {"from_email": "quality@unverified.example"}}, **shared,
        )
    with pytest.raises(ValueError, match="reserved for this tenant"):
        resend_email_policy._normalise_tenant_resend_payload(
            {"config": {"from_email": "quality.other-tenant@notify.venspera.com"}}, **shared,
        )
    with pytest.raises(ValueError, match="not been assigned"):
        resend_email_policy._normalise_tenant_resend_payload(
            {"config": {"from_email": "quality@flysafarilink.com"}},
            platform_config=config, tenant_id="tenant-B", tenant_slug="another",
        )


def test_tenant_resend_identity_accepts_verified_custom_domain_and_reply_to_list():
    prepared = resend_email_policy._normalise_tenant_resend_payload(
        {
            "enabled": True,
            "config": {
                "from_name": "Safarilink Quality",
                "from_email": "quality@flysafarilink.com",
                "reply_to": "qm@flysafarilink.com; qo@flysafarilink.com",
            },
        },
        platform_config={
            "from_email": "notifications@notify.venspera.com",
            "tenant_default_sender_domain": "notify.venspera.com",
            "verified_sender_domains": "flysafarilink.com",
            "tenant_sender_domain_assignments_json": '{"tenant-A": ["flysafarilink.com"]}',
        },
        tenant_id="tenant-A",
        tenant_slug="safarilink",
    )
    assert prepared["config"]["from_email"] == "quality@flysafarilink.com"
    assert prepared["config"]["reply_to"] == "qm@flysafarilink.com, qo@flysafarilink.com"


def test_platform_rejects_duplicate_domain_assignments():
    with pytest.raises(ValueError, match="cannot be assigned to multiple tenants"):
        resend_email_policy._tenant_domain_assignments(
            '{"tenant-A": ["flysafarilink.com"], "tenant-B": ["flysafarilink.com"]}'
        )



def test_quality_sender_scope_does_not_override_security_notifications():
    assert notification_providers._uses_qms_sender("qms_audit_notice_memo")
    assert notification_providers._uses_qms_sender("finding-issued")
    assert notification_providers._uses_qms_sender("qms_mail_identity_test")
    assert not notification_providers._uses_qms_sender("password-reset")
    assert not notification_providers._uses_qms_sender("email-verification")
    assert not notification_providers._uses_qms_sender("account-welcome")
    assert not notification_providers._uses_qms_sender("training-expiry-warning")


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


def test_non_sending_authentication_does_not_grant_delivery_health():
    result = {"credential_status": "AUTHENTICATED"}

    assert resend_email_policy.status_after_authentication("CONFIGURED", result) == "AUTHENTICATED"
    assert resend_email_policy.status_after_authentication("UNHEALTHY", result) == "AUTHENTICATED"
    assert resend_email_policy.status_after_authentication("HEALTHY", result) == "HEALTHY"


def test_resend_authentication_job_never_requests_generic_health_mutation(monkeypatch: pytest.MonkeyPatch):
    row = SimpleNamespace(id="resend-credential", status="CONFIGURED", tenant_id=None)
    captured: dict = {}
    monkeypatch.setattr(
        saas_services,
        "get_provider_credential",
        lambda db, *, provider, tenant_id, allow_platform_fallback: row,
    )

    def fake_enqueue(db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="job-1")

    monkeypatch.setattr(resend_email_policy.saas_queue, "enqueue_job", fake_enqueue)

    result = saas_services.enqueue_provider_health(
        MagicMock(),
        provider="resend",
        tenant_id=None,
        actor_user_id="superuser-1",
    )

    assert result.id == "job-1"
    assert captured["payload"]["provider"] == "resend"
    assert captured["payload"]["mutate_credential_status"] is False


def test_safe_worker_routes_resend_health_to_resend_authentication_handler(monkeypatch: pytest.MonkeyPatch):
    expected = {"credential_status": "AUTHENTICATED"}
    handler = MagicMock(return_value=expected)
    monkeypatch.setattr(resend_email_policy, "process_resend_authentication_job", handler)
    db = MagicMock()
    job = SimpleNamespace(
        job_type="PROVIDER_HEALTH_CHECK",
        payload_json={"provider": "resend", "credential_id": "credential-1"},
    )

    assert saas_worker_safe._process_job(db, job) == expected
    handler.assert_called_once_with(db, job)


def test_resend_adapter_serializes_binary_attachments_for_sdk(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}

    def fake_send(params, options):
        captured["params"] = params
        captured["options"] = options
        return {"id": "email_notice_1"}

    monkeypatch.setattr(resend_adapter.resend.Emails, "send", fake_send)
    result = resend_adapter.send_email(
        api_key="re_test_key",
        api_url="https://api.resend.com",
        from_value="Quality <quality@example.com>",
        to_email="auditee@example.com",
        subject="Audit notice",
        text="Please see the attached audit notice.",
        cc=["auditor@example.com"],
        reply_to=["quality@example.com", "auditor@example.com"],
        idempotency_key="audit-notice:1",
        attachments=[{"filename": "notice.pdf", "content": b"%PDF", "content_type": "application/pdf"}],
    )

    assert result["message_id"] == "email_notice_1"
    assert captured["params"]["attachments"] == [
        {"filename": "notice.pdf", "content": [37, 80, 68, 70], "content_type": "application/pdf"}
    ]
    assert captured["options"] == {"idempotency_key": "audit-notice:1"}
    assert captured["params"]["to"] == ["auditee@example.com"]
    assert captured["params"]["cc"] == ["auditor@example.com"]
    assert captured["params"]["reply_to"] == ["quality@example.com", "auditor@example.com"]


def test_semicolon_sandbox_list_is_separate_validated_mailboxes():
    assert resend_adapter.email_recipients('one@example.com; "Test, Auditor" <two@example.com>') == [
        "one@example.com", '"Test, Auditor" <two@example.com>',
    ]
    assert resend_adapter.email_recipients("one@example.com; one@example.com") == ["one@example.com"]
    with pytest.raises(ValueError):
        resend_adapter.email_recipients("one@example.com; not-an-email")
    with pytest.raises(ValueError):
        resend_adapter.email_recipients("one@example.com\r\nBcc: other@example.com")
