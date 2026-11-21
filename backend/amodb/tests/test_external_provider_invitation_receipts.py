"""External provider invitation receipts: no false delivery claims or token leakage."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from amodb.apps.notifications import models as mail_models
from amodb.apps.notifications.providers import _fallback_content
from amodb.apps.procurement import external_auth_router as external


@pytest.mark.parametrize(
    "kind,template",
    [
        ("invitation", "external-provider-invitation"),
        ("reverification", "external-provider-reverification"),
        ("password recovery", "external-provider-password-recovery"),
    ],
)
def test_external_mail_uses_dedicated_template_and_safe_grant_correlation(monkeypatch, kind, template):
    calls = []
    monkeypatch.setattr(external.core, "context", lambda *args, **kwargs: None)
    monkeypatch.setenv("PORTAL_FRONTEND_BASE_URL", "https://portal.example.test")
    db = MagicMock()
    db.get.return_value = SimpleNamespace(login_slug="safarilink", amo_code="SL")
    def send(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            id="email-log-1", recipient="representative@example.test", status=mail_models.EmailStatus.SENT,
            delivery_status="ACCEPTED", provider_message_id="email-resend-1",
            context_json={"_delivery": {"mode": "SANDBOX", "effective_recipient": "test@example.test"}},
        )
    monkeypatch.setattr(external.notifications, "send_email", send)
    receipt = external._send(
        db, "tenant-a", "representative@example.test", "one-time-secret",
        kind, grant_id="grant-a",
    )
    sent = calls[0]
    assert sent["template_key"] == template
    assert sent["email_class"] == "ESSENTIAL"
    assert sent["amo_id"] == "tenant-a"
    assert sent["recipient"] == "representative@example.test"
    assert sent["context"]["action_url"] == "https://portal.example.test/vendor/" + {"invitation":"invite","reverification":"verify","password recovery":"reset"}[kind] + "?amo=safarilink"
    assert "10 minutes" in sent["context"]["message"]
    assert "one-time-secret" in sent["context"]["message"]
    assert "one-time-secret" not in str(sent["audit_context"])
    assert "one-time-secret" not in sent["correlation_id"]
    assert sent["correlation_id"].startswith("extmail:grant-a:")
    assert len(sent["correlation_id"]) <= 64
    assert receipt == {
        "email_status": "SENT", "email_delivery_status": "ACCEPTED",
        "email_log_id": "email-log-1", "provider_message_id": "email-resend-1",
        "sending_mode": "SANDBOX", "provider_accepted": True,
        "recipient": "representative@example.test", "effective_recipient": "test@example.test",
    }


def test_invalid_public_frontend_url_never_enters_mail(monkeypatch):
    monkeypatch.setenv("PORTAL_FRONTEND_BASE_URL", "http://localhost:3000")
    db = MagicMock()
    assert external._vendor_action_url(db, "tenant-a") is None
    db.get.assert_not_called()


def test_external_template_is_useful_and_escapes_untrusted_html():
    body, plain = _fallback_content(
        "external-provider-invitation", "AMO Portal invitation",
        {"message": "Your code is <unsafe-token>", "action_url": "https://portal.example.test/vendor/login"},
    )
    assert "Your code is &lt;unsafe-token&gt;" in body
    assert "<unsafe-token>" not in body
    assert "https://portal.example.test/vendor/login" in plain
    assert "Never share" in plain
    assert "password-reset" not in body


def test_external_invitation_template_rejects_blank_code():
    with pytest.raises(ValueError):
        _fallback_content("external-provider-invitation", "Invitation", {"message": ""})


def test_delivery_history_scopes_to_grant_and_redacts_token(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(external, "_authorized_quality", lambda db, amo_code, user: "tenant-a")
    def find_grant(sql, db, **kwargs):
        assert kwargs == {"amo": "tenant-a", "grant": "grant-a"}
        return {
            "id": "grant-a", "status": "PENDING",
            "email": "representative@example.test", "verified_at": None,
        }
    monkeypatch.setattr(external.core, "one", find_grant)
    recorded_at = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
    email = SimpleNamespace(
        id="log-a", amo_id="tenant-a",
        correlation_id="extmail:grant-a:I:aaa", created_at=recorded_at,
        recipient="representative@example.test",
        template_key="external-provider-invitation",
        status=mail_models.EmailStatus.SENT,
        delivery_status="DELIVERED",
        provider_message_id="provider-a",
        context_json={"_delivery": {"mode": "PRODUCTION", "effective_recipient": "representative@example.test"}},
    )
    event = SimpleNamespace(
        email_log_id="log-a", event_type="email.delivered", occurred_at=recorded_at,
        payload_json={"token": "must-not-leak"},
    )
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.side_effect = [
        [email], [event],
    ]
    result = external.invitation_delivery_history(
        "safarilink", "grant-a", limit=10, db=db, user=SimpleNamespace(id="user-a"),
    )
    assert result["grant_id"] == "grant-a"
    assert result["verified"] is False
    assert result["attempts"][0]["email_delivery_status"] == "DELIVERED"
    assert result["attempts"][0]["events"] == [{"event": "email.delivered", "at": recorded_at.isoformat()}]
    assert "must-not-leak" not in str(result)
    assert "recipient-server delivery" in result["note"]


def test_mail_history_fails_closed_for_unknown_grant(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(external, "_authorized_quality", lambda db, code, user: "tenant-a")
    monkeypatch.setattr(external.core, "one", lambda *args, **kwargs: None)
    with pytest.raises(HTTPException) as failure:
        external.invitation_delivery_history("safarilink", "foreign-grant", limit=10, db=db, user=SimpleNamespace(id="user-a"))
    assert failure.value.status_code == 404
    db.query.assert_not_called()


def test_accepted_recent_invitation_is_not_rotated_for_resend(monkeypatch):
    monkeypatch.setattr(external, "_authorized_quality", lambda db, code, user: "tenant-a")
    monkeypatch.setattr(external.core, "one", lambda sql, db, **kwargs: (
        {"id": "grant-a", "status": "PENDING", "identity_id": "identity-a", "email": "recipient@example.test"}
        if "SELECT g.*,i.email" in sql else None
    ))
    monkeypatch.setattr(external.core, "run", lambda *args, **kwargs: pytest.fail("Recent invitation must not rotate token"))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id="recent-accepted")
    with pytest.raises(HTTPException) as failure:
        external.resend_invitation("safarilink", "grant-a", db=db, user=SimpleNamespace(id="user-a"))
    assert failure.value.status_code == 409
    db.commit.assert_not_called()
