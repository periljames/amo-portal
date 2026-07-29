from unittest.mock import MagicMock

from amodb.apps.accounts import router_public


def test_password_reset_email_uses_essential_resend_policy(monkeypatch):
    captured = {}

    def fake_send_email(*args, **kwargs):
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(
        router_public.notification_service,
        "send_email",
        fake_send_email,
    )

    router_public._maybe_send_email(
        MagicMock(),
        "user@example.com",
        "Reset your AMO Portal password",
        "Use this link to reset your password: https://portal/reset?token=secret",
        db=MagicMock(),
        amo_id="amo-1",
        user_id="user-1",
        action_url="https://portal/reset?token=secret",
    )

    assert captured["template_key"] == "password-reset"
    assert captured["email_class"] == "ESSENTIAL"
    assert captured["recipient_user_id"] == "user-1"
    assert "action_url" in captured["context"]
    assert "action_url" not in captured["audit_context"]
