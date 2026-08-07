from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ComponentInductionInput(BaseModel):
    definition_code: str = Field(min_length=1, max_length=80)
    position_code: str = Field(min_length=1, max_length=50)
    part_number: str | None = Field(default=None, max_length=50)
    serial_number: str | None = Field(default=None, max_length=50)
    baseline_hours: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    baseline_cycles: int | None = Field(default=None, ge=0)
    source_reference: str = Field(min_length=1, max_length=255)
    source_revision: str = Field(min_length=1, max_length=80)
    source_checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")

    @field_validator("source_checksum_sha256")
    @classmethod
    def normalise_checksum(cls, value: str | None) -> str | None:
        return value.lower() if value else value


class AircraftInductionCreate(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=120)
    aircraft_serial_number: str = Field(min_length=1, max_length=50)
    registration: str = Field(min_length=1, max_length=20)
    type_revision_id: str
    programme_revision_id: str
    model_code: str | None = Field(default=None, max_length=32)
    manufacturer: str | None = Field(default=None, max_length=50)
    model: str | None = Field(default=None, max_length=50)
    home_base: str | None = Field(default=None, max_length=10)
    operator_code: str | None = Field(default=None, max_length=5)
    company_name: str | None = Field(default=None, max_length=255)
    initial_airframe_hours: Decimal = Field(default=Decimal("0.00"), ge=0, decimal_places=2)
    initial_airframe_cycles: int = Field(default=0, ge=0)
    effectivity_context: dict[str, Any] = Field(default_factory=dict)
    components: list[ComponentInductionInput] = Field(default_factory=list)

    @field_validator("registration", "aircraft_serial_number")
    @classmethod
    def normalise_identity(cls, value: str) -> str:
        return value.strip().upper()


class SnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    snapshot_hash: str
    created_at: datetime


class LineageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type_revision_id: str
    programme_revision_id: str
    configuration_snapshot_id: str
    applicability_snapshot_id: str
    type_content_hash: str
    programme_content_hash: str
    lineage_hash: str
    created_at: datetime


class AircraftInductionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    amo_id: str
    aircraft_serial_number: str
    registration: str
    type_revision_id: str
    programme_revision_id: str
    idempotency_key: str
    request_hash: str
    status: str
    created_by_user_id: str
    created_at: datetime
    completed_at: datetime
    configuration_snapshot: SnapshotRead
    applicability_snapshot: SnapshotRead
    lineage: LineageRead
