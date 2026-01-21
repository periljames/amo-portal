from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from amodb.database import Base
from amodb.apps.accounts import models as account_models
from amodb.apps.reliability import models as reliability_models
from amodb.apps.reliability.router import (
    create_notification_rule,
    list_my_notifications,
    list_notification_rules,
    mark_notification_read,
)
from amodb.apps.reliability import schemas as reliability_schemas


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            account_models.AMO.__table__,
            account_models.Department.__table__,
            account_models.User.__table__,
            reliability_models.ReliabilityNotification.__table__,
            reliability_models.ReliabilityNotificationRule.__table__,
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


def _create_amo(db, *, code: str, name: str, slug: str) -> account_models.AMO:
    amo = account_models.AMO(
        amo_code=code,
        name=name,
        login_slug=slug,
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


def test_notifications_use_effective_amo_id(db_session):
    primary_amo = _create_amo(db_session, code="AMO-PRIMARY", name="Primary AMO", slug="primary")
    effective_amo = _create_amo(db_session, code="AMO-EFFECT", name="Effective AMO", slug="effective")
    user = _create_user(db_session, primary_amo.id)
    setattr(user, "effective_amo_id", effective_amo.id)

    rule_payload = reliability_schemas.ReliabilityNotificationRuleCreate(
        severity=reliability_models.ReliabilitySeverityEnum.HIGH,
    )
    rule = create_notification_rule(
        rule_payload,
        current_user=user,
        db=db_session,
    )
    assert rule.amo_id == effective_amo.id

    rules = list_notification_rules(current_user=user, db=db_session)
    assert len(rules) == 1
    assert rules[0].amo_id == effective_amo.id

    notification = reliability_models.ReliabilityNotification(
        amo_id=effective_amo.id,
        user_id=user.id,
        title="Alert",
        message="Threshold exceeded",
        severity=reliability_models.ReliabilitySeverityEnum.HIGH,
        dedupe_key="alert-1",
        created_at=datetime.utcnow(),
    )
    db_session.add(notification)
    db_session.commit()
    db_session.refresh(notification)

    notifications = list_my_notifications(current_user=user, db=db_session)
    assert len(notifications) == 1
    assert notifications[0].amo_id == effective_amo.id

    read_payload = reliability_schemas.ReliabilityNotificationMarkRead(read=True)
    updated = mark_notification_read(
        notification.id,
        read_payload,
        current_user=user,
        db=db_session,
    )
    assert updated.read_at is not None
