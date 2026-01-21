from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from .models import IntegrationConfigStatus, IntegrationOutboundStatus


class IntegrationConfigBase(BaseModel):
    integration_key: str = Field(..., max_length=64)
    display_name: str = Field(..., max_length=128)
    status: IntegrationConfigStatus = IntegrationConfigStatus.ACTIVE
    enabled: bool = True
    base_url: Optional[str] = None
    signing_secret: Optional[str] = None
    allowed_ips: Optional[str] = None
    credentials_json: Optional[Dict[str, Any]] = None
    metadata_json: Optional[Dict[str, Any]] = None


class IntegrationConfigCreate(IntegrationConfigBase):
    pass


class IntegrationConfigRead(IntegrationConfigBase):
    id: str
    amo_id: str
    created_at: datetime
    updated_at: datetime
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None

    class Config:
        from_attributes = True


class IntegrationOutboundEventCreate(BaseModel):
    integration_id: str
    event_type: str
    payload_json: Dict[str, Any]
    idempotency_key: Optional[str] = None


class IntegrationOutboundEventRead(BaseModel):
    id: str
    amo_id: str
    integration_id: str
    event_type: str
    payload_json: Dict[str, Any]
    status: IntegrationOutboundStatus
    attempt_count: int
    next_attempt_at: Optional[datetime] = None
    last_error: Optional[str] = None
    idempotency_key: Optional[str] = None
    created_at: datetime
    created_by_user_id: Optional[str] = None

    class Config:
        from_attributes = True


class IntegrationInboundIngest(BaseModel):
    event_type: str
    payload: Dict[str, Any]


class IntegrationInboundEventRead(BaseModel):
    id: str
    amo_id: str
    integration_id: str
    event_type: str
    payload_json: Dict[str, Any]
    received_at: datetime
    idempotency_key: str
    signature_valid: bool
    source_ip: Optional[str] = None
    payload_hash: str
    error: Optional[str] = None
    created_by_user_id: Optional[str] = None

    class Config:
        from_attributes = True
