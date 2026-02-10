from __future__ import annotations

from datetime import datetime, timedelta, timezone

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.apps.tasks import models as task_models
from amodb.apps.tasks import services as task_services


def _create_amo(db_session) -> account_models.AMO:
    amo = account_models.AMO(
        amo_code="AMO-TASK",
        name="Task AMO",
        login_slug="task",
    )
    db_session.add(amo)
    db_session.commit()
    return amo


def _create_user(db_session, amo_id: str) -> account_models.User:
    user = account_models.User(
        amo_id=amo_id,
        email="qa@example.com",
        staff_code="QA1",
        first_name="QA",
        last_name="User",
        full_name="QA User",
        hashed_password="hash",
        role=account_models.AccountRole.QUALITY_MANAGER,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_create_task_writes_task_and_audit_event(db_session):
    amo = _create_amo(db_session)
    user = _create_user(db_session, amo_id=amo.id)

    task = task_services.create_task(
        db_session,
        amo_id=amo.id,
        title="Respond to finding",
        description="Test",
        owner_user_id=user.id,
        entity_type="qms_finding",
        entity_id="finding-1",
    )
    db_session.commit()

    assert task.id is not None
    event = (
        db_session.query(audit_models.AuditEvent)
        .filter(audit_models.AuditEvent.entity_type == "tasks.task", audit_models.AuditEvent.action == "CREATED")
        .first()
    )
    assert event is not None


def test_escalate_task_updates_escalated_at_and_logs_audit_event(db_session):
    amo = _create_amo(db_session)
    user = _create_user(db_session, amo_id=amo.id)

    task = task_models.Task(
        amo_id=amo.id,
        title="Escalate task",
        description=None,
        status=task_models.TaskStatus.OPEN,
        owner_user_id=user.id,
    )
    db_session.add(task)
    db_session.commit()

    task_services.escalate_task(
        db_session,
        task=task,
        actor_user_id=user.id,
        escalation_level=1,
        new_owner_user_id=user.id,
    )
    db_session.commit()

    assert task.escalated_at is not None
    event = (
        db_session.query(audit_models.AuditEvent)
        .filter(audit_models.AuditEvent.entity_type == "tasks.task", audit_models.AuditEvent.action == "ESCALATED")
        .first()
    )
    assert event is not None


def test_runner_idempotency(db_session):
    amo = _create_amo(db_session)
    user = _create_user(db_session, amo_id=amo.id)

    due_at = datetime.now(timezone.utc) + timedelta(hours=4)
    task = task_models.Task(
        amo_id=amo.id,
        title="Reminder task",
        status=task_models.TaskStatus.OPEN,
        owner_user_id=user.id,
        due_at=due_at,
        metadata_json={},
    )
    db_session.add(task)
    db_session.commit()

    now = datetime.now(timezone.utc)
    summary = task_services.run_task_runner(db_session, now=now, reminder_window_hours=6)
    assert summary["reminders"] == 1

    summary_second = task_services.run_task_runner(db_session, now=now + timedelta(hours=1), reminder_window_hours=6)
    assert summary_second["reminders"] == 0
