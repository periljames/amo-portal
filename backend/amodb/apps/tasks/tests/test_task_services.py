from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.apps.tasks import models as task_models
from amodb.apps.tasks import services as task_services
from amodb.apps.tasks import schemas as task_schemas
from amodb.apps.tasks.router import create_personal_task, update_personal_task


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


def test_personal_tasks_are_owner_scoped_and_editable(db_session):
    amo = _create_amo(db_session)
    owner = _create_user(db_session, amo.id)
    task = create_personal_task(task_schemas.PersonalTaskCreate(title="  Follow up  "), db_session, owner)
    assert task.title == "Follow up"
    assert task.owner_user_id == owner.id
    assert task.entity_type == "quality_personal"
    payload = task_schemas.PersonalTaskUpdate(title="Updated follow-up", status="DONE", priority=1)
    for stranger in [SimpleNamespace(id="another-user", amo_id=amo.id), SimpleNamespace(id=owner.id, amo_id="another-tenant")]:
        with pytest.raises(HTTPException) as error:
            update_personal_task(task.id, payload, db_session, stranger)
        assert error.value.status_code == 404
    updated = update_personal_task(task.id, payload, db_session, owner)
    assert updated.status == task_models.TaskStatus.DONE
    assert updated.closed_at is not None
    reopened = update_personal_task(task.id, payload.model_copy(update={"status": task_models.TaskStatus.OPEN}), db_session, owner)
    assert reopened.closed_at is None


def test_personal_task_validation():
    for values in [{"title": "   "}, {"title": "A", "priority": 0}, {"title": "A", "owner_user_id": "other"}, {"title": "A", "reminder_at": "2026-09-11T10:00:00"}]:
        with pytest.raises(ValidationError):
            task_schemas.PersonalTaskCreate(**values)


def test_personal_reminders_persist_once_and_do_not_escalate(db_session, monkeypatch):
    from amodb.apps.notifications.models import EmailStatus

    amo = _create_amo(db_session)
    owner = _create_user(db_session, amo.id)
    now = datetime.now(timezone.utc)
    task = create_personal_task(task_schemas.PersonalTaskCreate(
        title="Review evidence", due_at=now - timedelta(days=4), reminder_at=now - timedelta(minutes=1),
    ), db_session, owner)
    deliveries = []
    monkeypatch.setattr(task_services.notification_service, "send_email", lambda *args, **kwargs: deliveries.append(kwargs) or SimpleNamespace(status=EmailStatus.SENT))
    assert task_services.run_task_runner(db_session, now=now) == {"reminders": 1, "escalations": 0}
    db_session.commit()
    db_session.expire_all()
    assert task_services.run_task_runner(db_session, now=now + timedelta(minutes=1)) == {"reminders": 0, "escalations": 0}
    assert len(deliveries) == 1
    assert task.owner_user_id == owner.id
    assert task.metadata_json["reminder_sent_at"]
    update_personal_task(task.id, task_schemas.PersonalTaskUpdate(title=task.title, status="OPEN", reminder_at=now + timedelta(days=1)), db_session, owner)
    assert "reminder_sent_at" not in task.metadata_json


def test_personal_calendar_includes_owned_tasks_and_reminders(db_session, monkeypatch):
    from amodb.apps.rostering import calendar_feed

    amo = _create_amo(db_session)
    owner = _create_user(db_session, amo.id)
    now = datetime.now(timezone.utc)
    task = create_personal_task(task_schemas.PersonalTaskCreate(
        title="Evidence, review", due_at=now + timedelta(days=1), reminder_at=now + timedelta(hours=1),
    ), db_session, owner)
    db_session.add(task_models.Task(amo_id=amo.id, owner_user_id=None, title="Not mine", entity_type="quality_personal", due_at=now))
    db_session.commit()
    monkeypatch.setattr(calendar_feed, "_published_assignments", lambda *args, **kwargs: [])
    monkeypatch.setattr(calendar_feed.commitments, "list_commitments", lambda *args, **kwargs: SimpleNamespace(items=[]))
    feed = calendar_feed.personal_calendar(db_session, amo_id=amo.id, user_id=owner.id)
    assert f"UID:quality-task-{task.id}@amo-portal" in feed
    assert "Evidence\\, review" in feed
    assert "BEGIN:VALARM" in feed
    assert "Not mine" not in feed
    task.status = task_models.TaskStatus.DONE
    db_session.commit()
    feed = calendar_feed.personal_calendar(db_session, amo_id=amo.id, user_id=owner.id)
    assert "STATUS:CANCELLED" in feed
    assert "BEGIN:VALARM" not in feed


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
