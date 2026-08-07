from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


BASE_INTERVAL_FIELDS = {"hours", "cycles", "landings", "days", "months", "years"}
COMPOUND_INTERVAL_FIELDS = {"threshold", "repeat"}
CONTROLLED_INTERVAL_FIELDS = BASE_INTERVAL_FIELDS | COMPOUND_INTERVAL_FIELDS
PLACEHOLDER_VALUES = {
    "dummy",
    "example",
    "example task",
    "not provided",
    "placeholder",
    "sample task",
    "tbd",
    "test task",
    "to be provided",
    "todo",
    "unknown",
}


def _normalised_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _reject_placeholder(value: str, *, field_name: str) -> None:
    normalised = _normalised_text(value)
    if normalised in PLACEHOLDER_VALUES or any(
        normalised.startswith(f"{marker} ")
        for marker in ("placeholder", "dummy", "tbd", "todo")
    ):
        raise ValueError(f"{field_name} contains fabricated placeholder content")


def _positive_decimal(value: Any, *, field_name: str) -> None:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"{field_name} must use an exact integer or canonical decimal string")
    if isinstance(value, int):
        if value <= 0:
            raise ValueError(f"{field_name} must be greater than zero")
        return
    if isinstance(value, Decimal):
        decimal_value = value
    elif isinstance(value, str):
        try:
            decimal_value = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"{field_name} must be a canonical decimal string") from exc
    else:
        raise ValueError(f"{field_name} must use an exact integer or canonical decimal string")
    if not decimal_value.is_finite() or decimal_value <= 0:
        raise ValueError(f"{field_name} must be a finite value greater than zero")


def _positive_integer(value: Any, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _validate_interval_mapping(value: dict[str, Any], *, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    unknown = sorted(set(value) - CONTROLLED_INTERVAL_FIELDS)
    if unknown:
        raise ValueError(
            f"{field_name} contains unsupported interval fields: {', '.join(unknown)}"
        )
    for key, item in value.items():
        path = f"{field_name}.{key}"
        if key in COMPOUND_INTERVAL_FIELDS:
            if not isinstance(item, dict):
                raise ValueError(f"{path} must be a controlled interval object")
            if not item:
                raise ValueError(f"{path} must not be empty")
            nested_unknown = sorted(set(item) - BASE_INTERVAL_FIELDS)
            if nested_unknown:
                raise ValueError(
                    f"{path} contains unsupported interval fields: {', '.join(nested_unknown)}"
                )
            for nested_key, nested_value in item.items():
                nested_path = f"{path}.{nested_key}"
                if nested_key == "hours":
                    _positive_decimal(nested_value, field_name=nested_path)
                else:
                    _positive_integer(nested_value, field_name=nested_path)
        elif key == "hours":
            _positive_decimal(item, field_name=path)
        else:
            _positive_integer(item, field_name=path)


def _reject_inexact_numbers(value: Any, *, field_name: str) -> None:
    if isinstance(value, float):
        raise ValueError(f"{field_name} must not contain IEEE-754 floating-point values")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_inexact_numbers(item, field_name=f"{field_name}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_inexact_numbers(item, field_name=f"{field_name}[{index}]")


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

    @model_validator(mode="after")
    def require_or_build_provenance(self):
        if "provenance_json" not in self.model_fields_set:
            self.provenance_json = {
                "authority": self.authority,
                "source_reference": self.reference,
                "source_revision": self.source_revision,
                "checksum_sha256": self.checksum_sha256,
                "provenance_basis": "CONTROLLED_SOURCE_TUPLE",
            }
        elif not self.provenance_json:
            raise ValueError("Controlled sources require provenance metadata")
        return self


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

    @field_validator("life_limit_json")
    @classmethod
    def exact_life_limits(cls, value: dict[str, Any]) -> dict[str, Any]:
        _reject_inexact_numbers(value, field_name="life_limit_json")
        return value


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
    def require_controlled_content(self):
        _reject_placeholder(self.task_code, field_name="task_code")
        _reject_placeholder(self.title, field_name="title")
        _validate_interval_mapping(self.intervals_json, field_name="intervals_json")
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

    @model_validator(mode="after")
    def reject_duplicate_controlled_identities(self):
        identities = {
            "source": [(row.reference, row.source_revision) for row in self.sources],
            "position": [row.code for row in self.positions],
            "component": [row.definition_code for row in self.components],
            "task": [row.task_code for row in self.tasks],
        }
        for label, values in identities.items():
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate controlled {label} identity")
        return self


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
