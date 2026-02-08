from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import TaskStatus


class TaskCreate(BaseModel):
    title: str = Field(min_length=1)
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.OPEN
    owner_user_id: Optional[str] = None
    supervisor_user_id: Optional[str] = None
    due_at: Optional[datetime] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    priority: int = 3
    metadata: Optional[dict] = None


class TaskUpdate(BaseModel):
    status: Optional[TaskStatus] = None
    due_at: Optional[datetime] = None
    priority: Optional[int] = None
    description: Optional[str] = None
    escalate: Optional[bool] = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    amo_id: str
    title: str
    description: Optional[str]
    status: TaskStatus
    owner_user_id: Optional[str]
    supervisor_user_id: Optional[str]
    due_at: Optional[datetime]
    escalated_at: Optional[datetime]
    closed_at: Optional[datetime]
    entity_type: Optional[str]
    entity_id: Optional[str]
    priority: int
    metadata_json: Optional[dict] = None
    created_at: datetime
    updated_at: datetime
