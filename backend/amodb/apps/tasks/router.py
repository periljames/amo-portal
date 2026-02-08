from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from amodb.entitlements import require_module
from amodb.security import get_current_active_user, require_roles
from amodb.apps.accounts import models as account_models
from amodb.database import get_db

from . import models, schemas, services


router = APIRouter(
    tags=["tasks"],
    dependencies=[Depends(require_module("quality"))],
)


@router.get("/tasks/my", response_model=List[schemas.TaskRead])
def list_my_tasks(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    return services.list_tasks_for_user(db, amo_id=current_user.amo_id, owner_user_id=current_user.id)


@router.get("/tasks", response_model=List[schemas.TaskRead])
def list_tasks(
    status: Optional[models.TaskStatus] = None,
    entity_type: Optional[str] = None,
    due_before: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(
            account_models.AccountRole.AMO_ADMIN,
            account_models.AccountRole.QUALITY_MANAGER,
            account_models.AccountRole.SUPERUSER,
        )
    ),
):
    qs = db.query(models.Task).filter(models.Task.amo_id == current_user.amo_id)
    if status:
        qs = qs.filter(models.Task.status == status)
    if entity_type:
        qs = qs.filter(models.Task.entity_type == entity_type)
    if due_before:
        qs = qs.filter(models.Task.due_at.is_not(None), models.Task.due_at <= due_before)
    return qs.order_by(models.Task.due_at.asc().nullslast()).all()


@router.patch("/tasks/{task_id}", response_model=schemas.TaskRead)
def update_task(
    task_id: str,
    payload: schemas.TaskUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    task = (
        db.query(models.Task)
        .filter(models.Task.id == task_id, models.Task.amo_id == current_user.amo_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    is_admin = current_user.role in (
        account_models.AccountRole.AMO_ADMIN,
        account_models.AccountRole.QUALITY_MANAGER,
        account_models.AccountRole.SUPERUSER,
    )
    is_owner = task.owner_user_id == current_user.id
    is_supervisor = task.supervisor_user_id == current_user.id

    data = payload.model_dump(exclude_unset=True)
    detail_changes = {}
    if "description" in data:
        detail_changes["description"] = data["description"]
    if "due_at" in data:
        detail_changes["due_at"] = data["due_at"]
    if "priority" in data:
        detail_changes["priority"] = data["priority"]
    if detail_changes:
        if not (is_admin or is_supervisor):
            raise HTTPException(status_code=403, detail="Not authorized to edit task details")
        services.update_task_details(db, task=task, actor_user_id=current_user.id, changes=detail_changes)

    if payload.escalate:
        if not (is_admin or is_supervisor):
            raise HTTPException(status_code=403, detail="Not authorized to escalate tasks")
        services.escalate_task(
            db,
            task=task,
            actor_user_id=current_user.id,
            escalation_level=int(task.metadata_json.get("escalation_level", 0) if task.metadata_json else 0) + 1,
            new_owner_user_id=task.supervisor_user_id or task.owner_user_id,
        )
        db.commit()
        db.refresh(task)
        return task

    if payload.status is not None:
        if is_owner and payload.status not in (models.TaskStatus.IN_PROGRESS, models.TaskStatus.DONE):
            raise HTTPException(status_code=403, detail="Owners may only mark tasks in progress or done")
        if not is_owner and not (is_admin or is_supervisor):
            raise HTTPException(status_code=403, detail="Not authorized to update tasks")
        services.update_task_status(db, task=task, status=payload.status, actor_user_id=current_user.id)

    db.commit()
    db.refresh(task)
    return task
