from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import pytest

from amodb.apps.training import notification_dispatch


ROOT = Path(__file__).resolve().parents[5]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_retry_delay_is_exponential_and_bounded() -> None:
    assert notification_dispatch.retry_delay_seconds(1) == 60
    assert notification_dispatch.retry_delay_seconds(2) == 120
    assert notification_dispatch.retry_delay_seconds(3) == 240
    assert notification_dispatch.retry_delay_seconds(99) == 6 * 60 * 60


def test_tenant_channel_policy_is_opt_in_and_deduplicated() -> None:
    assert notification_dispatch._normalise_channels({}) == ()
    assert notification_dispatch._normalise_channels({"external_channels": ["email", "EMAIL", "whatsapp"]}) == (
        "EMAIL",
        "WHATSAPP",
    )
    assert notification_dispatch._normalise_channels({"email_enabled": True, "whatsapp_enabled": True}) == (
        "EMAIL",
        "WHATSAPP",
    )


def test_email_adapter_uses_provider_message_id_and_fake_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[EmailMessage] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            assert host == "smtp.example.test"
            assert port == 2525
            assert timeout == 15

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def starttls(self) -> None:
            return None

        def login(self, username: str, password: str) -> None:
            assert username == "training-bot"
            assert password == "secret"

        def send_message(self, message: EmailMessage) -> None:
            sent.append(message)

    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_FROM", "training@example.test")
    monkeypatch.setenv("SMTP_USER", "training-bot")
    monkeypatch.setenv("SMTP_PASS", "secret")
    monkeypatch.setattr(notification_dispatch.smtplib, "SMTP", FakeSMTP)

    provider_id = notification_dispatch._deliver_email(
        address="learner@example.test",
        subject="Training due",
        body="Open My Training.",
    )

    assert provider_id.startswith("<") and provider_id.endswith(">")
    assert len(sent) == 1
    assert sent[0]["To"] == "learner@example.test"
    assert sent[0]["Subject"] == "Training due"
    assert sent[0]["Message-ID"] == provider_id


def test_outbox_contract_reuses_training_workflow_runtime() -> None:
    source = _source("backend/amodb/apps/training/notification_dispatch.py")
    for contract in (
        'OUTBOX_WORKFLOW_TYPE = "NOTIFICATION_OUTBOX"',
        'workflow_type=OUTBOX_WORKFLOW_TYPE',
        'status="QUEUED"',
        'workflow.status = "SENDING"',
        'workflow.status = "SENT"',
        'workflow.status = "RETRY_SCHEDULED"',
        'workflow.status = "FAILED"',
        '"attempt_count"',
        '"provider_message_id"',
        '"last_error"',
        '"next_attempt_at"',
        '"NOTIFICATION_OUTBOX_TRANSITION"',
    ):
        assert contract in source


def test_scheduler_syncs_and_processes_durable_outbox() -> None:
    source = _source("backend/amodb/jobs/training_notification_automation.py")
    assert "sync_notifications_to_outbox" in source
    assert "process_outbox" in source
    assert 'summary[f"outbox_{key}"]' in source
    assert 'summary[f"delivery_{key}"]' in source
