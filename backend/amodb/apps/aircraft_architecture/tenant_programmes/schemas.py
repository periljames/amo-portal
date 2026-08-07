from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from amodb.apps.aircraft_architecture.content_packs.schemas import _reject_inexact_numbers, _validate_interval_mapping


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
    task_code: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=255)
    ata_chapter: str | None = Field(default=None, max_length=12)
    intervals_json: dict[str, Any]
    effectivity_expression_json: dict[str, Any] = Field(default_factory=dict)
    source_reference: str = Field(min_length=1, max_length=255)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("intervals_json")
    @classmethod
    def controlled_intervals(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_interval_mapping(value, field_name="intervals_json")
        return value

    @model_validator(mode="after")
    def exact_payload(self):
        _reject_inexact_numbers(self.effectivity_expression_json, field_name="effectivity_expression_json")
        return self


class RevisionCreate(BaseModel):
    """Legacy/manual draft entry retained for compatibility.

    New AMP configuration should use CreateFromOemRequest so every OEM-derived
    requirement has immutable canonical lineage.
    """

    revision_code: str
    aircraft_type_revision_id: str
    effectivity_rule_version_id: str | None = None
    base_content_pack_revision_id: str | None = None
    source_reference: str
    source_revision: str
    source_checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    change_summary: str | None = None
    supersedes_revision_id: str | None = None
    tasks: list[TaskCreate] = Field(min_length=1)


class CreateFromOemRequest(BaseModel):
    revision_code: str = Field(min_length=1, max_length=40)
    aircraft_type_revision_id: str
    base_content_pack_revision_id: str | None = None
    effectivity_rule_version_id: str | None = None
    change_summary: str | None = None
    supersedes_revision_id: str | None = None
    confirm_derived_series: bool = False


class TaskDecisionUpdate(BaseModel):
    decision: Literal["INHERIT", "TIGHTEN"]
    intervals_json: dict[str, Any] | None = None
    justification: str | None = Field(default=None, max_length=4000)
    approval_reference: str | None = Field(default=None, max_length=160)

    @field_validator("intervals_json")
    @classmethod
    def controlled_intervals(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            _validate_interval_mapping(value, field_name="intervals_json")
        return value


class OperatorTaskCreate(TaskCreate):
    justification: str = Field(min_length=3, max_length=4000)
    approval_reference: str | None = Field(default=None, max_length=160)


class ProgrammeRead(ORMModel):
    id: str
    amo_id: str
    code: str
    title: str
    authority: str | None
    approval_reference: str | None
    status: str
    created_at: datetime


class TaskRead(ORMModel):
    id: str
    revision_id: str
    source_content_task_id: str | None
    decision: str
    task_code: str
    title: str
    ata_chapter: str | None
    intervals_json: dict[str, Any]
    effectivity_expression_json: dict[str, Any]
    source_reference: str
    justification: str | None
    approval_reference: str | None
    source_task_hash: str | None
    metadata_json: dict[str, Any]


class RevisionRead(ORMModel):
    id: str
    programme_id: str
    revision_code: str
    status: str
    aircraft_type_revision_id: str
    effectivity_rule_version_id: str | None
    base_content_pack_revision_id: str | None
    source_reference: str
    source_revision: str
    source_currentness_at_approval: str | None
    approval_reference: str | None
    content_hash: str | None
    change_summary: str | None
    created_at: datetime
    published_at: datetime | None


class RevisionDetailRead(RevisionRead):
    tasks: list[TaskRead] = Field(default_factory=list)


class PublishRequest(BaseModel):
    expected_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_reference: str = Field(min_length=2, max_length=160)


class UpgradeImpactRequest(BaseModel):
    current_tasks: list[dict[str, Any]]
    proposed_tasks: list[dict[str, Any]]


class BaselineCandidate(BaseModel):
    pack_id: str
    pack_code: str
    manufacturer: str
    family: str
    series: str | None
    revision_id: str
    revision_code: str
    content_hash: str | None


class BaselineResolutionRead(BaseModel):
    aircraft_type_revision_id: str
    template_id: str
    template_code: str
    model: str
    variant: str | None
    series: str | None
    series_confidence: Literal["EXPLICIT", "DERIVED", "UNRESOLVED"]
    series_reason: str
    state: Literal["RESOLVED", "CONFIRM_DERIVED_SERIES", "AMBIGUOUS", "UNRESOLVED"]
    candidates: list[BaselineCandidate] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    severity: Literal["BLOCK", "WARN", "INFO"]
    code: str
    message: str
    task_code: str | None = None


class ValidationRead(BaseModel):
    status: Literal["PASS", "WARN", "BLOCKED"]
    blocking_count: int
    warning_count: int
    issues: list[ValidationIssue]
    summary: dict[str, Any]
    validation_run_id: str | None = None


class ValidationRunRead(ORMModel):
    id: str
    amo_id: str
    revision_id: str
    baseline_revision_id: str
    programme_content_hash: str
    baseline_content_hash: str
    status: str
    blocking_count: int
    warning_count: int
    issues_json: list[dict[str, Any]]
    summary_json: dict[str, Any]
    created_at: datetime
