from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Sequence

from sqlalchemy.orm import Session

from amodb.apps.audit import services as audit_services
from amodb.apps.accounts import models as account_models
from amodb.apps.notifications import service as notification_service

from . import models


REMINDER_COOLDOWN_HOURS = 24
ESCALATION_THRESHOLDS_HOURS = (24, 72)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _merge_metadata(task: models.Task, updates: dict) -> None:
    if task.metadata_json is None:
        task.metadata_json = {}
    task.metadata_json.update(updates)


def create_task(
    db: Session,
    *,
    amo_id: str,
    title: str,
    description: Optional[str] = None,
    status: models.TaskStatus = models.TaskStatus.OPEN,
    owner_user_id: Optional[str] = None,
    supervisor_user_id: Optional[str] = None,
    due_at: Optional[datetime] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    priority: int = 3,
    metadata: Optional[dict] = None,
) -> models.Task:
    existing = (
        db.query(models.Task)
        .filter(
            models.Task.amo_id == amo_id,
            models.Task.title == title,
            models.Task.owner_user_id == owner_user_id,
            models.Task.entity_type == entity_type,
            models.Task.entity_id == entity_id,
            models.Task.status.in_([models.TaskStatus.OPEN, models.TaskStatus.IN_PROGRESS]),
        )
        .first()
    )
    if existing:
        return existing

    task = models.Task(
        amo_id=amo_id,
        title=title,
        description=description,
        status=status,
        owner_user_id=owner_user_id,
        supervisor_user_id=supervisor_user_id,
        due_at=due_at,
        entity_type=entity_type,
        entity_id=entity_id,
        priority=priority,
        metadata_json=metadata or {},
    )
    db.add(task)
    db.flush()
    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=owner_user_id,
        entity_type="task",
        entity_id=str(task.id),
        action="task_create",
        after={
            "title": task.title,
            "status": task.status.value,
            "owner_user_id": task.owner_user_id,
            "entity_type": task.entity_type,
            "entity_id": task.entity_id,
        },
        metadata={"module": "tasks"},
    )
    return task


def update_task_status(
    db: Session,
    *,
    task: models.Task,
    status: models.TaskStatus,
    actor_user_id: Optional[str],
) -> models.Task:
    task.status = status
    if status in (models.TaskStatus.DONE, models.TaskStatus.CANCELLED):
        task.closed_at = _utcnow()
    else:
        task.closed_at = None
    db.add(task)
    audit_services.log_event(
        db,
        amo_id=task.amo_id,
        actor_user_id=actor_user_id,
        entity_type="task",
        entity_id=str(task.id),
        action="task_update",
        after={"status": task.status.value, "closed_at": str(task.closed_at) if task.closed_at else None},
        metadata={"module": "tasks"},
    )
    return task


def update_task_details(
    db: Session,
    *,
    task: models.Task,
    actor_user_id: Optional[str],
    changes: dict,
) -> models.Task:
    for field, value in changes.items():
        setattr(task, field, value)
    db.add(task)
    audit_services.log_event(
        db,
        amo_id=task.amo_id,
        actor_user_id=actor_user_id,
        entity_type="task",
        entity_id=str(task.id),
        action="task_update",
        after={k: str(v) if isinstance(v, datetime) else v for k, v in changes.items()},
        metadata={"module": "tasks"},
    )
    return task


def escalate_task(
    db: Session,
    *,
    task: models.Task,
    actor_user_id: Optional[str],
    escalation_level: int,
    new_owner_user_id: Optional[str],
) -> models.Task:
    task.escalated_at = _utcnow()
    if new_owner_user_id:
        task.owner_user_id = new_owner_user_id
    _merge_metadata(
        task,
        {
            "last_escalated_at": task.escalated_at.isoformat(),
            "escalation_level": escalation_level,
        },
    )
    db.add(task)
    audit_services.log_event(
        db,
        amo_id=task.amo_id,
        actor_user_id=actor_user_id,
        entity_type="task",
        entity_id=str(task.id),
        action="task_escalate",
        after={
            "owner_user_id": task.owner_user_id,
            "escalated_at": str(task.escalated_at),
            "escalation_level": escalation_level,
        },
        metadata={"module": "tasks"},
        critical=True,
    )
    return task


def list_tasks_for_user(
    db: Session,
    *,
    amo_id: str,
    owner_user_id: str,
) -> Sequence[models.Task]:
    return (
        db.query(models.Task)
        .filter(models.Task.amo_id == amo_id, models.Task.owner_user_id == owner_user_id)
        .order_by(models.Task.due_at.asc().nullslast())
        .all()
    )


def close_tasks_for_entity(
    db: Session,
    *,
    amo_id: str,
    entity_type: str,
    entity_id: str,
    actor_user_id: Optional[str],
) -> int:
    tasks = (
        db.query(models.Task)
        .filter(
            models.Task.amo_id == amo_id,
            models.Task.entity_type == entity_type,
            models.Task.entity_id == entity_id,
            models.Task.status.in_([models.TaskStatus.OPEN, models.TaskStatus.IN_PROGRESS]),
        )
        .all()
    )
    for task in tasks:
        update_task_status(db, task=task, status=models.TaskStatus.DONE, actor_user_id=actor_user_id)
    return len(tasks)


def _get_qa_user_id(db: Session, amo_id: str) -> Optional[str]:
    user = (
        db.query(account_models.User)
        .filter(
            account_models.User.amo_id == amo_id,
            account_models.User.role.in_(
                [
                    account_models.AccountRole.QUALITY_MANAGER,
                    account_models.AccountRole.AMO_ADMIN,
                    account_models.AccountRole.SUPERUSER,
                ]
            ),
        )
        .order_by(account_models.User.created_at.asc())
        .first()
    )
    return user.id if user else None


def _resolve_recipient_email(db: Session, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    user = db.query(account_models.User).filter(account_models.User.id == user_id).first()
    if not user or not user.email:
        return None
    cleaned_email = user.email.strip()
    return cleaned_email or None


def _should_notify(task: models.Task, *, now: datetime, cooldown_hours: int) -> bool:
    if not task.metadata_json:
        return True
    last = task.metadata_json.get("last_notified_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return True
    return now - last_dt >= timedelta(hours=cooldown_hours)


def run_task_runner(
    db: Session,
    *,
    now: Optional[datetime] = None,
    reminder_window_hours: int = 24,
    reminder_cooldown_hours: int = REMINDER_COOLDOWN_HOURS,
) -> dict:
    now = now or _utcnow()
    reminder_cutoff = now + timedelta(hours=reminder_window_hours)

    reminders_sent = 0
    escalations_sent = 0

    reminders = (
        db.query(models.Task)
        .filter(
            models.Task.status.in_([models.TaskStatus.OPEN, models.TaskStatus.IN_PROGRESS]),
            models.Task.due_at.is_not(None),
            models.Task.due_at >= now,
            models.Task.due_at <= reminder_cutoff,
        )
        .all()
    )

    for task in reminders:
        if not _should_notify(task, now=now, cooldown_hours=reminder_cooldown_hours):
            continue
        recipient = _resolve_recipient_email(db, task.owner_user_id)
        notification_service.send_email(
            "task_reminder",
            recipient,
            f"Task reminder: {task.title}",
            {
                "task_id": str(task.id),
                "title": task.title,
                "description": task.description,
                "due_at": task.due_at.isoformat() if task.due_at else None,
                "owner_user_id": task.owner_user_id,
            },
            correlation_id=f"task:{task.id}:reminder",
            critical=False,
            amo_id=task.amo_id,
            db=db,
        )
        _merge_metadata(task, {"last_notified_at": now.isoformat()})
        db.add(task)
        audit_services.log_event(
            db,
            amo_id=task.amo_id,
            actor_user_id=task.owner_user_id,
            entity_type="task",
            entity_id=str(task.id),
            action="task_reminder",
            after={"due_at": str(task.due_at)},
            metadata={"module": "tasks"},
        )
        reminders_sent += 1

    overdue_tasks = (
        db.query(models.Task)
        .filter(
            models.Task.status.in_([models.TaskStatus.OPEN, models.TaskStatus.IN_PROGRESS]),
            models.Task.due_at.is_not(None),
            models.Task.due_at < now,
        )
        .all()
    )

    for task in overdue_tasks:
        escalation_level = 0
        if task.metadata_json and "escalation_level" in task.metadata_json:
            escalation_level = int(task.metadata_json.get("escalation_level") or 0)

        if task.metadata_json and task.metadata_json.get("last_escalated_at"):
            try:
                last_escalated = datetime.fromisoformat(task.metadata_json["last_escalated_at"])
            except ValueError:
                last_escalated = None
            if last_escalated and now - last_escalated < timedelta(hours=reminder_cooldown_hours):
                continue

        overdue_hours = (now - task.due_at).total_seconds() / 3600
        target_level = escalation_level
        for idx, threshold in enumerate(ESCALATION_THRESHOLDS_HOURS, start=1):
            if overdue_hours >= threshold:
                target_level = idx

        if target_level <= escalation_level:
            continue

        new_owner = task.owner_user_id
        if target_level == 1 and task.supervisor_user_id:
            new_owner = task.supervisor_user_id
        elif target_level >= 2:
            qa_user_id = _get_qa_user_id(db, task.amo_id)
            if qa_user_id:
                new_owner = qa_user_id

        escalate_task(
            db,
            task=task,
            actor_user_id=new_owner,
            escalation_level=target_level,
            new_owner_user_id=new_owner,
        )
        recipient = _resolve_recipient_email(db, new_owner)
        try:
            notification_service.send_email(
                "task_escalation",
                recipient,
                f"Task escalation: {task.title}",
                {
                    "task_id": str(task.id),
                    "title": task.title,
                    "description": task.description,
                    "due_at": task.due_at.isoformat() if task.due_at else None,
                    "owner_user_id": task.owner_user_id,
                    "escalation_level": target_level,
                    "new_owner_user_id": new_owner,
                },
                correlation_id=f"task:{task.id}:escalation:{target_level}",
                critical=True,
                amo_id=task.amo_id,
                db=db,
            )
        except Exception:
            db.commit()
            raise
        escalations_sent += 1

    return {"reminders": reminders_sent, "escalations": escalations_sent}
