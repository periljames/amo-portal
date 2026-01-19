from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AuditEventCreate(BaseModel):
    entity_type: str
    entity_id: str
    action: str
    actor_user_id: Optional[str] = None
    occurred_at: Optional[datetime] = None
    before_json: Optional[dict] = None
    after_json: Optional[dict] = None
    correlation_id: Optional[str] = None


class AuditEventRead(AuditEventCreate):
    id: int
    amo_id: str
    created_at: datetime

    class Config:
        from_attributes = True
