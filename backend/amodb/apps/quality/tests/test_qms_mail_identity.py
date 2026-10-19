from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from amodb.apps.quality import qms_mail_identity_router as mail
from amodb.apps.quality.tenant_security import TenantContext


def _ctx(*, admin: bool = False) -> TenantContext:
    return TenantContext(
        amo_code="safarilink", amo_id="tenant-A", user_id="user-A",
        is_superuser=False, admin_authority=admin,
    )


def _user(role: str = "QUALITY_MANAGER"):
    return SimpleNamespace(
        id="user-A", amo_id="tenant-A", role=role, is_active=True,
        email="manager@flysafarilink.com", full_name="Quality Manager",
    )


def test_qms_mail_identity_default_uses_own_tenant_and_no_provider_secrets(monkeypatch):
    config = {
        "from_email": "notifications@notify.venspera.com",
        "tenant_default_sender_domain": "notify.venspera.com",
        "tenant_sender_domain_assignments_json": '{"tenant-A": ["flysafarilink.com"]}',
        "verified_sender_domains": "flysafarilink.com",
        "sending_mode": "SANDBOX",
    }
    monkeypatch.setattr(
        mail, "_platform_and_tenant",
        lambda db, amo_id: (SimpleNamespace(config_json=config, status="HEALTHY"), None),
    )
    monkeypatch.setattr(
        mail, "get_email_provider",
        lambda *, db, amo_id: (
            SimpleNamespace(config={"reply_to": "manager@flysafarilink.com"}), True
        ),
    )
    db = MagicMock()
    db.get.return_value = SimpleNamespace(
        name="Safarilink Aviation", login_slug="safarilink", amo_code="SAFARILINK",
    )
    identity = mail._identity_payload(db, _ctx(), _user())
    assert identity["from_email"] == "quality.safarilink@notify.venspera.com"
    assert identity["shared_sender"] == identity["from_email"]
    assert identity["custom_domains"] == ["flysafarilink.com"]
    assert identity["ready"] is True
    assert identity["can_manage"] is True
    assert "api_key" not in identity
    assert "webhook_signing_secret" not in identity


def test_qms_mail_identity_save_enforces_tenant_scope_and_clears_stale_sender(monkeypatch):
    saved = {}
    monkeypatch.setattr(
        mail, "_platform_and_tenant",
        lambda db, amo_id: (SimpleNamespace(config_json={}), None),
    )
    monkeypatch.setattr(
        mail.saas_services, "upsert_provider_credential",
        lambda db, **kwargs: saved.update(kwargs),
    )
    monkeypatch.setattr(mail, "_identity_payload", lambda db, ctx, user: {"saved": True})
    db = MagicMock()
    result = mail.update_qms_mail_identity(
        mail.MailIdentityUpdate(
            from_name="Safarilink Quality",
            from_email="",
            reply_to="",
            enabled=True,
            reason="Return to tenant defaults",
        ),
        ctx=_ctx(), user=_user(), db=db,
    )
    assert result == {"saved": True}
    assert saved["tenant_id"] == "tenant-A"
    assert saved["actor_user_id"] == "user-A"
    assert set(saved["payload"]["clear_config_fields"]) == {"from_email", "reply_to"}
    assert saved["payload"]["config"] == {"from_name": "Safarilink Quality"}


def test_qms_mail_identity_rejects_non_quality_management():
    with pytest.raises(HTTPException) as raised:
        mail.update_qms_mail_identity(
            mail.MailIdentityUpdate(
                from_name="Test", reason="Unauthorised request",
            ),
            ctx=_ctx(), user=_user("AUDITOR"), db=MagicMock(),
        )
    assert raised.value.status_code == 403


def test_qms_mail_test_sends_only_to_requester(monkeypatch):
    calls = {}
    def fake_send(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(
            id="email-log", status="SENT", delivery_status="ACCEPTED",
            provider_message_id="resend-accepted-message",
        )
    monkeypatch.setattr(mail.notification_service, "send_email", fake_send)
    db = MagicMock()
    outcome = mail.test_qms_mail_identity(ctx=_ctx(), user=_user(), db=db)
    assert calls["recipient"] == "manager@flysafarilink.com"
    assert calls["amo_id"] == "tenant-A"
    assert calls["recipient_user_id"] == "user-A"
    assert calls["cooldown_seconds"] == 60
    assert outcome["delivery_status"] == "ACCEPTED"
    assert "recipient-server delivery" in outcome["detail"]
    db.commit.assert_called_once()
