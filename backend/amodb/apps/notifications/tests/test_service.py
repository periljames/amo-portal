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


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            account_models.AMO.__table__,
            account_models.User.__table__,
            notification_models.EmailLog.__table__,
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
        lambda: (notification_providers.NoopProvider(), False),
    )

    log = notification_service.send_email(
        "task_reminder",
        "notify@example.com",
        "Reminder",
        {"task_id": "1"},
        correlation_id="task:1:reminder",
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
        def send(self, **kwargs):
            return None

    monkeypatch.setattr(
        notification_providers,
        "get_email_provider",
        lambda: (FakeProvider(), True),
    )

    log = notification_service.send_email(
        "task_reminder",
        "notify@example.com",
        "Reminder",
        {"task_id": "1"},
        correlation_id="task:1:reminder",
        amo_id=amo.id,
        db=db_session,
    )
    db_session.commit()

    assert log.status == notification_models.EmailStatus.SENT
    assert log.sent_at is not None
    assert log.error is None


def test_send_email_provider_failure_best_effort(db_session, monkeypatch):
    amo = _create_amo(db_session)
    _create_user(db_session, amo.id)

    class FailingProvider(notification_providers.EmailProvider):
        def send(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        notification_providers,
        "get_email_provider",
        lambda: (FailingProvider(), True),
    )

    log = notification_service.send_email(
        "task_reminder",
        "notify@example.com",
        "Reminder",
        {"task_id": "1"},
        correlation_id="task:1:reminder",
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
        def send(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        notification_providers,
        "get_email_provider",
        lambda: (FailingProvider(), True),
    )

    with pytest.raises(RuntimeError):
        notification_service.send_email(
            "task_escalation",
            "notify@example.com",
            "Escalation",
            {"task_id": "1"},
            correlation_id="task:1:escalation",
            amo_id=amo.id,
            critical=True,
            db=db_session,
        )
