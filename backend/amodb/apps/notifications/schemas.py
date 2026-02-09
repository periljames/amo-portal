from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .models import EmailStatus


class EmailLogRead(BaseModel):
    id: str
    amo_id: str
    created_at: datetime
    sent_at: Optional[datetime] = None
    recipient: str
    subject: str
    template_key: str
    status: EmailStatus
    error: Optional[str] = None
    context_json: Optional[dict] = None
    correlation_id: Optional[str] = None

    class Config:
        from_attributes = True
        validate_by_name = True
