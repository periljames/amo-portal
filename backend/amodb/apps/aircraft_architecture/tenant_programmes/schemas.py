from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProgrammeCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=3, max_length=200)
    authority: str | None = Field(default=None, max_length=80)
    approval_reference: str | None = Field(default=None, max_length=160)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class TaskCreate(BaseModel):
    task_code: str
    title: str
    ata_chapter: str | None = None
    intervals_json: dict[str, Any] = Field(default_factory=dict)
    effectivity_expression_json: dict[str, Any] = Field(default_factory=dict)
    source_reference: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RevisionCreate(BaseModel):
    revision_code: str
    aircraft_type_revision_id: str
    effectivity_rule_version_id: str | None = None
    source_reference: str
    source_revision: str
    source_checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    change_summary: str | None = None
    supersedes_revision_id: str | None = None
    tasks: list[TaskCreate] = Field(min_length=1)


class ProgrammeRead(ORMModel):
    id: str
    amo_id: str
    code: str
    title: str
    authority: str | None
    approval_reference: str | None
    status: str
    created_at: datetime


class RevisionRead(ORMModel):
    id: str
    programme_id: str
    revision_code: str
    status: str
    aircraft_type_revision_id: str
    effectivity_rule_version_id: str | None
    source_reference: str
    source_revision: str
    content_hash: str | None
    created_at: datetime
    published_at: datetime | None


class PublishRequest(BaseModel):
    expected_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class UpgradeImpactRequest(BaseModel):
    current_tasks: list[dict[str, Any]]
    proposed_tasks: list[dict[str, Any]]
