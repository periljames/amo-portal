from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class AuditEventCreate(BaseModel):
    entity_type: str
    entity_id: str
    action: str
    actor_user_id: Optional[str] = None
    occurred_at: Optional[datetime] = None
    before: Optional[dict] = None
    after: Optional[dict] = None
    correlation_id: Optional[str] = None
    metadata: Optional[dict] = None

    @model_validator(mode="before")
    @classmethod
    def promote_legacy_payload_keys(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        next_data = dict(data)
        if ("before" not in next_data or next_data.get("before") is None) and "before_json" in next_data:
            next_data["before"] = next_data.get("before_json")
        if ("after" not in next_data or next_data.get("after") is None) and "after_json" in next_data:
            next_data["after"] = next_data.get("after_json")
        next_data.pop("before_json", None)
        next_data.pop("after_json", None)
        return next_data


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
        populate_by_name = True
