from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from amodb.database import Base
from amodb.apps.accounts import models as account_models
from amodb.apps.notifications import models as notification_models
from amodb.apps.notifications import providers as notification_providers
from amodb.apps.notifications import service as notification_service
from amodb.apps.realtime import models as realtime_models


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def _seed_internal_user(session_factory):
    db = session_factory()
    amo = account_models.AMO(
        amo_code="AMO-REVIEW",
        name="Review AMO",
        login_slug="review",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(amo)
    db.flush()
    user = account_models.User(
        amo_id=amo.id,
        email="internal@example.com",
        staff_code="REVIEW-1",
        first_name="Internal",
        last_name="Recipient",
        full_name="Internal Recipient",
        hashed_password="hash",
        role=account_models.AccountRole.QUALITY_MANAGER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return db, amo, user


def test_internal_email_lookup_enforces_user_opt_out_without_user_id(
    session_factory,
    monkeypatch,
):
    db, amo, user = _seed_internal_user(session_factory)
    db.add(
        realtime_models.NotificationTenantPreference(
            amo_id=amo.id,
            routine_email_enabled=True,
        )
    )
    db.add(
        realtime_models.NotificationPreference(
            amo_id=amo.id,
            user_id=user.id,
            email_enabled=False,
        )
    )
    db.commit()

    provider_called = False

    class FakeProvider(notification_providers.EmailProvider):
        config = {}

        def send(self, **kwargs):
            nonlocal provider_called
            provider_called = True
            return {"provider": "resend", "message_id": "should-not-send"}

    monkeypatch.setattr(
        notification_providers,
        "get_email_provider",
        lambda **_: (FakeProvider(), True),
    )

    log = notification_service.send_email(
        "workforce.leave.approved",
        user.email,
        "Leave approved",
        {"request_id": "leave-1"},
        correlation_id="leave:1:approved",
        email_class="ROUTINE",
        amo_id=amo.id,
        db=db,
    )

    assert log.status == notification_models.EmailStatus.SKIPPED_BY_PREFERENCE
    assert provider_called is False
    db.close()


def test_password_reset_delivery_log_commits_in_isolated_session(
    session_factory,
    monkeypatch,
):
    outer_db, amo, user = _seed_internal_user(session_factory)

    class FakeProvider(notification_providers.EmailProvider):
        config = {}

        def send(self, **kwargs):
            return {
                "provider": "resend",
                "message_id": "email_password_reset_1",
                "recipient": kwargs["recipient"],
                "original_recipient": kwargs["recipient"],
            }

    monkeypatch.setattr(notification_service, "WriteSessionLocal", session_factory)
    monkeypatch.setattr(
        notification_providers,
        "get_email_provider",
        lambda **_: (FakeProvider(), True),
    )

    log = notification_service.send_email(
        "password-reset",
        user.email,
        "Reset your AMO Portal password",
        {"action_url": "https://portal/reset?token=secret"},
        correlation_id="password-reset:user-1:1",
        email_class="ESSENTIAL",
        recipient_user_id=user.id,
        audit_context={"purpose": "password-reset", "user_id": user.id},
        amo_id=amo.id,
        db=outer_db,
    )

    verifier = session_factory()
    persisted = (
        verifier.query(notification_models.EmailLog)
        .filter(notification_models.EmailLog.id == log.id)
        .one()
    )
    assert persisted.provider_message_id == "email_password_reset_1"
    assert persisted.delivery_status == "ACCEPTED"
    assert persisted.context_json["purpose"] == "password-reset"
    assert "action_url" not in persisted.context_json
    verifier.close()
    outer_db.close()
