from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RuleSetCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=3, max_length=200)
    target_kind: str = Field(min_length=2, max_length=40)
    target_reference: str = Field(min_length=1, max_length=160)
    aircraft_type_template_id: str | None = None
    description: str | None = None

    @field_validator("code", "target_kind")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return value.strip().upper()


class RuleSetRead(ORMModel):
    id: str
    code: str
    name: str
    target_kind: str
    target_reference: str
    aircraft_type_template_id: str | None
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class RuleVersionCreate(BaseModel):
    version_code: str = Field(min_length=1, max_length=40)
    effective_date: date | None = None
    expression_json: dict[str, Any]
    source_reference: str = Field(min_length=2, max_length=255)
    source_revision: str = Field(min_length=1, max_length=80)
    source_checksum_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-fA-F]{64}$"
    )
    change_summary: str | None = None
    supersedes_version_id: str | None = None


class RuleVersionRead(ORMModel):
    id: str
    rule_set_id: str
    version_code: str
    status: Literal["DRAFT", "PUBLISHED", "SUPERSEDED", "WITHDRAWN"]
    effective_date: date | None
    expression_json: dict[str, Any]
    content_hash: str | None
    source_reference: str
    source_revision: str
    source_checksum_sha256: str | None
    change_summary: str | None
    supersedes_version_id: str | None
    created_at: datetime
    published_at: datetime | None


class PublishRequest(BaseModel):
    expected_content_hash: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )


class EvaluateRequest(BaseModel):
    expression: dict[str, Any]
    context: dict[str, Any]


class TraceRead(BaseModel):
    path: str
    operator: str
    expected: Any
    actual: Any
    matched: bool
    reason: str


class EvaluationRead(BaseModel):
    applicable: bool
    reasons: list[str]
    trace: list[TraceRead]
    unresolved_paths: list[str]


class ImpactRequest(BaseModel):
    previous_expression: dict[str, Any]
    proposed_expression: dict[str, Any]
    contexts: list[dict[str, Any]] = Field(min_length=1, max_length=5000)
