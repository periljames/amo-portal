from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContentSourceCreate(BaseModel):
    source_type: str = Field(min_length=1, max_length=40)
    reference: str = Field(min_length=1, max_length=255)
    source_revision: str = Field(min_length=1, max_length=80)
    effective_date: date | None = None
    checksum_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    authority: str = Field(min_length=1, max_length=80)
    provenance_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("checksum_sha256")
    @classmethod
    def checksum_lower(cls, value: str) -> str:
        return value.lower()


class ContentPositionCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=160)
    position_kind: str = Field(min_length=1, max_length=40)
    required: bool = True
    source_reference: str = Field(min_length=1, max_length=255)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ContentComponentCreate(BaseModel):
    definition_code: str = Field(min_length=1, max_length=80)
    position_code: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=255)
    component_class: str = Field(min_length=1, max_length=50)
    accepted_part_numbers_json: list[str] = Field(default_factory=list)
    life_limit_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    source_reference: str = Field(min_length=1, max_length=255)


class ContentTaskCreate(BaseModel):
    task_code: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=255)
    ata_chapter: str | None = Field(default=None, max_length=12)
    intervals_json: dict[str, Any]
    effectivity_expression_json: dict[str, Any] = Field(default_factory=dict)
    source_reference: str = Field(min_length=1, max_length=255)
    source_revision: str = Field(min_length=1, max_length=80)
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_controlled_interval(self):
        if not self.intervals_json:
            raise ValueError("Content-pack tasks require an explicit source-backed interval")
        if not any(
            key in self.intervals_json
            for key in ("hours", "cycles", "days", "months", "years", "threshold", "repeat")
        ):
            raise ValueError("Task interval must use a controlled interval field")
        return self

    @field_validator("source_checksum_sha256")
    @classmethod
    def checksum_lower(cls, value: str) -> str:
        return value.lower()


class ContentRevisionCreate(BaseModel):
    revision_code: str = Field(min_length=1, max_length=40)
    change_summary: str | None = None
    sources: list[ContentSourceCreate] = Field(default_factory=list)
    positions: list[ContentPositionCreate] = Field(default_factory=list)
    components: list[ContentComponentCreate] = Field(default_factory=list)
    tasks: list[ContentTaskCreate] = Field(default_factory=list)


class PublishContentRevision(BaseModel):
    expected_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ContentPackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    manufacturer: str
    family: str
    description: str
    status: str
    created_at: datetime


class ContentRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pack_id: str
    revision_code: str
    status: str
    content_hash: str | None
    change_summary: str | None
    created_at: datetime
    published_at: datetime | None
