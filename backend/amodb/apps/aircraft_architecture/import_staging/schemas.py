from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MappingProfileCreate(BaseModel):
    amo_id: str | None = None
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=3, max_length=200)
    scope: Literal["GLOBAL", "TENANT"] = "TENANT"
    source_system: str = Field(min_length=2, max_length=40)
    dataset_kind: str = Field(min_length=2, max_length=60)

    @field_validator("code", "source_system", "dataset_kind")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return value.strip().upper()


class MappingVersionCreate(BaseModel):
    version_code: str = Field(min_length=1, max_length=40)
    headers: list[str] = Field(min_length=1)
    mapping_json: dict[str, Any]
    parser_options_json: dict[str, Any] = Field(default_factory=dict)


class MappingProfileRead(ORMModel):
    id: str
    amo_id: str | None
    code: str
    name: str
    scope: str
    source_system: str
    dataset_kind: str
    status: str
    created_at: datetime


class MappingVersionRead(ORMModel):
    id: str
    profile_id: str
    version_code: str
    status: str
    header_fingerprint: str
    mapping_json: dict[str, Any]
    parser_options_json: dict[str, Any]
    content_hash: str | None
    created_at: datetime
    published_at: datetime | None


class PublishMappingVersionRequest(BaseModel):
    expected_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class DatasetCreate(BaseModel):
    dataset_kind: str
    adapter_code: str
    file_name: str
    content_hash: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    headers: list[str] = Field(min_length=1)
    row_count: int = Field(default=0, ge=0)


class BatchCreate(BaseModel):
    source_system: str
    idempotency_key: str = Field(min_length=8, max_length=96)
    datasets: list[DatasetCreate] = Field(min_length=1, max_length=100)


class BatchRead(ORMModel):
    id: str
    amo_id: str
    source_system: str
    idempotency_key: str
    manifest_hash: str
    status: str
    created_at: datetime
