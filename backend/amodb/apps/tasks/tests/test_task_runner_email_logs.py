from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from amodb.database import Base
from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.apps.notifications import models as notification_models
from amodb.apps.tasks import models as task_models
from amodb.apps.tasks import services as task_services


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            account_models.AMO.__table__,
            account_models.User.__table__,
            account_models.AuthorisationType.__table__,
            account_models.UserAuthorisation.__table__,
            account_models.AccountSecurityEvent.__table__,
            audit_models.AuditEvent.__table__,
            notification_models.EmailLog.__table__,
            task_models.Task.__table__,
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
        amo_code="AMO-TASK",
        name="Task AMO",
        login_slug="tasks",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(amo)
    db.commit()
    return amo


def _create_user(db, amo_id: str, *, email: str, role: account_models.AccountRole) -> account_models.User:
    user = account_models.User(
        amo_id=amo_id,
        email=email,
        staff_code=email.split("@")[0].upper(),
        first_name="Task",
        last_name="User",
        full_name="Task User",
        hashed_password="hash",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def test_task_runner_creates_email_logs(db_session):
    amo = _create_amo(db_session)
    owner = _create_user(db_session, amo.id, email="owner@example.com", role=account_models.AccountRole.TECHNICIAN)
    supervisor = _create_user(
        db_session,
        amo.id,
        email="supervisor@example.com",
        role=account_models.AccountRole.QUALITY_MANAGER,
    )

    now = datetime.utcnow()

    reminder_task = task_models.Task(
        amo_id=amo.id,
        title="Reminder task",
        description="Needs attention",
        status=task_models.TaskStatus.OPEN,
        owner_user_id=owner.id,
        supervisor_user_id=supervisor.id,
        due_at=now + timedelta(hours=2),
        priority=2,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )
    overdue_task = task_models.Task(
        amo_id=amo.id,
        title="Escalation task",
        description="Overdue",
        status=task_models.TaskStatus.OPEN,
        owner_user_id=owner.id,
        supervisor_user_id=supervisor.id,
        due_at=now - timedelta(hours=25),
        priority=2,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )
    db_session.add(reminder_task)
    db_session.add(overdue_task)
    db_session.commit()

    summary = task_services.run_task_runner(db_session, now=now)
    db_session.commit()

    logs = db_session.query(notification_models.EmailLog).all()
    assert summary["reminders"] == 1
    assert summary["escalations"] == 1
    assert len(logs) == 2
    assert all(log.status == notification_models.EmailStatus.SKIPPED_NO_PROVIDER for log in logs)

    audit_events = db_session.query(audit_models.AuditEvent).all()
    assert any(event.action == "task_reminder" for event in audit_events)
    assert any(event.action == "ESCALATED" for event in audit_events)
