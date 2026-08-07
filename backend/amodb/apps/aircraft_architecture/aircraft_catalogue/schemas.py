from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FamilyCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    manufacturer: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=2, max_length=160)
    category: str = Field(min_length=2, max_length=40)
    description: str | None = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class FamilyRead(ORMModel):
    id: str
    code: str
    manufacturer: str
    name: str
    category: str
    status: str
    description: str | None
    created_at: datetime


class TemplateCreate(BaseModel):
    family_id: str
    code: str = Field(min_length=2, max_length=50)
    manufacturer: str = Field(min_length=2, max_length=120)
    model: str = Field(min_length=1, max_length=80)
    variant: str | None = Field(default=None, max_length=80)
    series: str | None = Field(default=None, max_length=80)
    type_certificate: str | None = Field(default=None, max_length=80)
    icao_type_designator: str | None = Field(default=None, max_length=8)
    category: str = Field(min_length=2, max_length=40)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("series")
    @classmethod
    def normalize_series(cls, value: str | None) -> str | None:
        return value.strip().upper() if value and value.strip() else None


class TemplateRead(ORMModel):
    id: str
    family_id: str
    code: str
    manufacturer: str
    model: str
    variant: str | None
    series: str | None
    type_certificate: str | None
    icao_type_designator: str | None
    category: str
    status: str
    created_at: datetime


class RevisionCreate(BaseModel):
    revision_code: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=3, max_length=200)
    effective_date: date | None = None
    supersedes_revision_id: str | None = None
    configuration_schema_json: dict[str, Any] = Field(default_factory=dict)
    applicability_defaults_json: dict[str, Any] = Field(default_factory=dict)
    change_summary: str | None = None


class PositionCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=160)
    position_kind: str = Field(min_length=2, max_length=40)
    parent_code: str | None = Field(default=None, max_length=50)
    sequence_no: str | None = Field(default=None, max_length=20)
    required: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    effectivity_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code", "parent_code")
    @classmethod
    def normalize_position_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class ComponentDefinitionCreate(BaseModel):
    definition_code: str = Field(min_length=1, max_length=80)
    position_code: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=2, max_length=255)
    component_class: str = Field(min_length=2, max_length=50)
    accepted_part_numbers_json: list[str] = Field(default_factory=list)
    life_limit_json: dict[str, Any] = Field(default_factory=dict)
    effectivity_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SourceCreate(BaseModel):
    source_type: str = Field(min_length=2, max_length=40)
    reference: str = Field(min_length=2, max_length=200)
    source_revision: str = Field(min_length=1, max_length=80)
    effective_date: date | None = None
    checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    authority: str | None = Field(default=None, max_length=80)
    provenance_json: dict[str, Any] = Field(default_factory=dict)


class PositionRead(ORMModel):
    id: str
    revision_id: str
    code: str
    label: str
    position_kind: str
    parent_code: str | None
    sequence_no: str | None
    required: bool
    metadata_json: dict[str, Any]
    effectivity_json: dict[str, Any]


class ComponentDefinitionRead(ORMModel):
    id: str
    revision_id: str
    definition_code: str
    position_code: str
    description: str
    component_class: str
    accepted_part_numbers_json: list[str]
    life_limit_json: dict[str, Any]
    effectivity_json: dict[str, Any]
    metadata_json: dict[str, Any]


class SourceRead(ORMModel):
    id: str
    revision_id: str
    source_type: str
    reference: str
    source_revision: str
    effective_date: date | None
    checksum_sha256: str | None
    authority: str | None
    provenance_json: dict[str, Any]
    created_at: datetime


class RevisionRead(ORMModel):
    id: str
    template_id: str
    revision_code: str
    title: str
    status: Literal["DRAFT", "PUBLISHED", "SUPERSEDED", "WITHDRAWN"]
    effective_date: date | None
    supersedes_revision_id: str | None
    configuration_schema_json: dict[str, Any]
    applicability_defaults_json: dict[str, Any]
    content_hash: str | None
    change_summary: str | None
    created_at: datetime
    published_at: datetime | None
    positions: list[PositionRead] = Field(default_factory=list)
    component_definitions: list[ComponentDefinitionRead] = Field(default_factory=list)
    sources: list[SourceRead] = Field(default_factory=list)


class PublishRequest(BaseModel):
    expected_content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
