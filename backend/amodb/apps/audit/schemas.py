from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AuditEventCreate(BaseModel):
    entity_type: str
    entity_id: str
    action: str
    actor_user_id: Optional[str] = None
    occurred_at: Optional[datetime] = None
    before: Optional[dict] = None
    after: Optional[dict] = None
    before_json: Optional[dict] = None
    after_json: Optional[dict] = None
    correlation_id: Optional[str] = None
    metadata: Optional[dict] = None


class AuditEventRead(BaseModel):
    id: str
    amo_id: str
    entity_type: str
    entity_id: str
    action: str
    actor_user_id: Optional[str] = None
    occurred_at: Optional[datetime] = None
    before: Optional[dict] = None
    after: Optional[dict] = None
    correlation_id: Optional[str] = None
    metadata: Optional[dict] = Field(default=None, alias="metadata_json")
    created_at: datetime

    class Config:
        from_attributes = True
        allow_population_by_field_name = True
