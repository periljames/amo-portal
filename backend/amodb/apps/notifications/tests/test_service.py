from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from amodb.database import Base
from amodb.apps.accounts import models as account_models
from amodb.apps.notifications import models as notification_models
from amodb.apps.notifications import service as notification_service
from amodb.apps.notifications import providers as notification_providers

from amodb.apps.realtime import models as realtime_models

@pytest.fixture()
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            account_models.AMO.__table__,
            account_models.User.__table__,
            realtime_models.NotificationPreference.__table__,
            realtime_models.NotificationTenantPreference.__table__,
            notification_models.EmailLog.__table__,
            notification_models.EmailDeliveryEvent.__table__,
        ],
    )
    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def _create_amo(db) -> account_models.AMO:
    amo = account_models.AMO(
        amo_code="AMO-NOTIFY",
        name="Notify AMO",
        login_slug="notify",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(amo)
    db.commit()
    return amo


def _create_user(db, amo_id: str) -> account_models.User:
    user = account_models.User(
        amo_id=amo_id,
        email="notify@example.com",
        staff_code="NOTIFY-1",
        first_name="Notify",
        last_name="User",
        full_name="Notify User",
        hashed_password="hash",
        role=account_models.AccountRole.AMO_ADMIN,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def test_send_email_no_provider_marks_skipped(db_session, monkeypatch):
    amo = _create_amo(db_session)
    _create_user(db_session, amo.id)

    monkeypatch.setattr(
        notification_providers,
        "get_email_provider",
        lambda **_: (notification_providers.NoopProvider(), False),
    )

    log = notification_service.send_email(
        "task_reminder",
        "notify@example.com",
        "Reminder",
        {"task_id": "1"},
        correlation_id="task:1:reminder",
        email_class="ESSENTIAL",
        amo_id=amo.id,
        db=db_session,
    )
    db_session.commit()

    assert log.status == notification_models.EmailStatus.SKIPPED_NO_PROVIDER
    assert log.error
    assert log.sent_at is None


def test_send_email_provider_success(db_session, monkeypatch):
    amo = _create_amo(db_session)
    _create_user(db_session, amo.id)

    class FakeProvider(notification_providers.EmailProvider):
        config = {"per_minute_limit": 10, "daily_limit": 500}

        def send(self, **kwargs):
            return {
                "provider": "resend",
                "message_id": "email_123",
                "mode": "SANDBOX",
                "recipient": kwargs["recipient"],
                "original_recipient": kwargs["recipient"],
                "template_id": None,
            }

    monkeypatch.setattr(
        notification_providers,
        "get_email_provider",
        lambda **_: (FakeProvider(), True),
    )

    log = notification_service.send_email(
        "task_reminder",
        "notify@example.com",
        "Reminder",
        {"task_id": "1"},
        correlation_id="task:1:reminder",
        email_class="ESSENTIAL",
        amo_id=amo.id,
        db=db_session,
    )
    db_session.commit()

    assert log.status == notification_models.EmailStatus.SENT
    assert log.sent_at is not None
    assert log.error is None
    assert log.context_json["_delivery"]["provider"] == "resend"
    assert log.context_json["_delivery"]["message_id"] == "email_123"


def test_send_email_passes_attachment_without_persisting_content(db_session, monkeypatch):
    amo = _create_amo(db_session)
    _create_user(db_session, amo.id)
    captured: dict = {}

    class FakeProvider(notification_providers.EmailProvider):
        config = {"per_minute_limit": 10, "daily_limit": 500}

        def send(self, **kwargs):
            captured.update(kwargs)
            return {
                "provider": "resend",
                "message_id": "email_with_notice",
                "mode": "SANDBOX",
                "recipient": kwargs["recipient"],
                "original_recipient": kwargs["recipient"],
                "template_id": None,
            }

    monkeypatch.setattr(notification_providers, "get_email_provider", lambda **_: (FakeProvider(), True))
    payload = b"%PDF-1.7\ncontrolled notice"
    log = notification_service.send_email(
        "qms_audit_notice_memo",
        "notify@example.com",
        "Audit notice",
        {"audit_ref": "QAR-26-001"},
        correlation_id="audit-notice:test",
        email_class="CRITICAL",
        amo_id=amo.id,
        db=db_session,
        attachments=[{"filename": "notice.pdf", "content": payload, "content_type": "application/pdf"}],
    )

    assert log.status == notification_models.EmailStatus.SENT
    assert captured["attachments"] == [
        {"filename": "notice.pdf", "content": payload, "content_type": "application/pdf"}
    ]
    assert log.context_json["_attachments"] == [
        {"filename": "notice.pdf", "content_type": "application/pdf", "size_bytes": len(payload)}
    ]
    assert payload not in str(log.context_json).encode()


def test_send_email_reuses_successful_correlation_id(db_session, monkeypatch):
    amo = _create_amo(db_session)
    _create_user(db_session, amo.id)
    calls = 0

    class FakeProvider(notification_providers.EmailProvider):
        config = {}

        def send(self, **kwargs):
            nonlocal calls
            calls += 1
            return {
                "provider": "resend",
                "message_id": "email_once",
                "mode": "SANDBOX",
                "recipient": kwargs["recipient"],
                "original_recipient": kwargs["recipient"],
                "template_id": None,
            }

    monkeypatch.setattr(notification_providers, "get_email_provider", lambda **_: (FakeProvider(), True))
    first = notification_service.send_email(
        "task_reminder",
        "notify@example.com",
        "Reminder",
        {},
        correlation_id="same-correlation",
        email_class="ESSENTIAL",
        amo_id=amo.id,
        db=db_session,
    )
    db_session.commit()
    second = notification_service.send_email(
        "task_reminder",
        "notify@example.com",
        "Reminder",
        {},
        correlation_id="same-correlation",
        email_class="ESSENTIAL",
        amo_id=amo.id,
        db=db_session,
    )

    assert first.id == second.id
    assert calls == 1


def test_send_email_provider_failure_best_effort(db_session, monkeypatch):
    amo = _create_amo(db_session)
    _create_user(db_session, amo.id)

    class FailingProvider(notification_providers.EmailProvider):
        config = {}

        def send(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        notification_providers,
        "get_email_provider",
        lambda **_: (FailingProvider(), True),
    )

    log = notification_service.send_email(
        "task_reminder",
        "notify@example.com",
        "Reminder",
        {"task_id": "1"},
        correlation_id="task:1:reminder",
        email_class="ESSENTIAL",
        amo_id=amo.id,
        db=db_session,
    )
    db_session.commit()

    assert log.status == notification_models.EmailStatus.FAILED
    assert log.error


def test_send_email_provider_failure_critical_raises(db_session, monkeypatch):
    amo = _create_amo(db_session)
    _create_user(db_session, amo.id)

    class FailingProvider(notification_providers.EmailProvider):
        config = {}

        def send(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        notification_providers,
        "get_email_provider",
        lambda **_: (FailingProvider(), True),
    )

    with pytest.raises(RuntimeError):
        notification_service.send_email(
            "task_escalation",
            "notify@example.com",
            "Escalation",
            {"task_id": "1"},
            correlation_id="task:1:escalation",
            email_class="CRITICAL",
            amo_id=amo.id,
            critical=True,
            db=db_session,
        )


def test_routine_email_requires_tenant_and_user_opt_in(db_session, monkeypatch):
    amo = _create_amo(db_session)
    user = _create_user(db_session, amo.id)
    monkeypatch.setattr(
        notification_providers,
        "get_email_provider",
        lambda **_: (notification_providers.NoopProvider(), True),
    )

    first = notification_service.send_email(
        "routine-update",
        user.email,
        "Routine update",
        {},
        correlation_id="routine:first",
        email_class="ROUTINE",
        recipient_user_id=user.id,
        amo_id=amo.id,
        db=db_session,
    )
    assert first.status == notification_models.EmailStatus.SKIPPED_BY_PREFERENCE

    db_session.add(
        realtime_models.NotificationTenantPreference(
            amo_id=amo.id,
            routine_email_enabled=True,
        )
    )
    db_session.add(
        realtime_models.NotificationPreference(
            amo_id=amo.id,
            user_id=user.id,
            email_enabled=True,
        )
    )
    db_session.commit()

    second = notification_service.send_email(
        "routine-update",
        user.email,
        "Routine update",
        {},
        correlation_id="routine:second",
        email_class="ROUTINE",
        recipient_user_id=user.id,
        amo_id=amo.id,
        db=db_session,
    )
    assert second.status != notification_models.EmailStatus.SKIPPED_BY_PREFERENCE


def test_critical_email_cannot_be_disabled(db_session, monkeypatch):
    amo = _create_amo(db_session)
    user = _create_user(db_session, amo.id)
    db_session.add(
        realtime_models.NotificationTenantPreference(
            amo_id=amo.id,
            routine_email_enabled=False,
            receipt_email_enabled=False,
            marketing_email_enabled=False,
        )
    )
    db_session.add(
        realtime_models.NotificationPreference(
            amo_id=amo.id,
            user_id=user.id,
            email_enabled=False,
            receipt_email_enabled=False,
            marketing_email_enabled=False,
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        notification_providers,
        "get_email_provider",
        lambda **_: (notification_providers.NoopProvider(), False),
    )

    log = notification_service.send_email(
        "corrective-action-overdue",
        user.email,
        "Corrective action overdue",
        {},
        correlation_id="critical:one",
        email_class="CRITICAL",
        recipient_user_id=user.id,
        amo_id=amo.id,
        db=db_session,
    )
    assert log.status == notification_models.EmailStatus.SKIPPED_NO_PROVIDER
