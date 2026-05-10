"""Pydantic schemas for the platform control-plane API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

CommandRisk = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
CommandStatus = Literal[
    "PENDING",
    "VALIDATING",
    "NEEDS_APPROVAL",
    "APPROVED",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "RETRYING",
    "CANCELLED",
    "EXPIRED",
    "UNSUPPORTED",
    "DENIED",
]


class PlatformList(BaseModel):
    items: list[Any]
    total: int = 0
    limit: int | None = None
    offset: int | None = None


class PlatformCommandCreate(BaseModel):
    command_name: str
    tenant_id: str | None = None
    reason: str | None = None
    dry_run: bool = False
    input_json: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class PlatformCommandRead(BaseModel):
    id: str
    command_name: str
    risk_level: CommandRisk
    status: CommandStatus
    tenant_id: str | None = None
    reason: str | None = None
    dry_run: bool = False
    output_json: dict[str, Any] | None = None
    error_code: str | None = None
    error_detail: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class PlatformTenantCreate(BaseModel):
    tenant_name: str
    tenant_code: str
    owner_email: str
    owner_name: str | None = None
    plan_code: str | None = None
    billing_mode: str | None = None
    enabled_modules: list[str] = Field(default_factory=list)
    initial_status: str = "ACTIVE"
    region: str | None = None
    trial_end_date: datetime | None = None
    custom_limits: dict[str, Any] = Field(default_factory=dict)
    reason: str


class ReasonPayload(BaseModel):
    reason: str
    confirmation: str | None = None


class FeatureFlagPayload(BaseModel):
    key: str | None = None
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    scope: str | None = "GLOBAL"
    tenant_id: str | None = None
    plan_code: str | None = None
    reason: str | None = None


class WebhookPayload(BaseModel):
    name: str
    event_type: str
    target_url: HttpUrl
    secret: str | None = None
    tenant_id: str | None = None
    is_global: bool = True
    reason: str


class ApiKeyCreatePayload(BaseModel):
    name: str
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    reason: str


class SupportSessionCreate(BaseModel):
    tenant_id: str
    reason: str
    mode: Literal["READ_ONLY", "ASSISTED"] = "READ_ONLY"
    expires_in_minutes: int = Field(default=30, ge=1, le=120)
