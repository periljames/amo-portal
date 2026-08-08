from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import schemas


class OemTemporaryRevisionGovernanceDecision(BaseModel):
    action: Literal[
        "ACTIVATE",
        "INCORPORATE",
        "SUPERSEDE",
        "WITHDRAW",
        "REPLACE",
        "REJECT",
    ]
    decision_note: str = Field(min_length=1, max_length=4000)


class OemSourceWatchGovernanceCreate(BaseModel):
    channel_type: Literal["MANUAL_UPLOAD", "OEM_PORTAL", "EMAIL_NOTICE", "RSS", "API", "OTHER"]
    reference: str = Field(min_length=1)
    check_interval_hours: int = Field(default=168, ge=1, le=8760)
    is_active: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class OemSourceWatchGovernanceCheck(BaseModel):
    result_code: Literal["OK", "CHANGE_DETECTED", "ERROR", "AUTH_REQUIRED", "UNAVAILABLE"]
    seen_marker: str | None = Field(default=None, max_length=255)
    detail: str = Field(min_length=1, max_length=8000)
    checked_at: datetime | None = None


class OemSourceWatchGovernanceRead(schemas.OemSourceWatchRead):
    check_interval_hours: int
    next_check_due_at: datetime | None
    last_success_at: datetime | None
    last_result_code: str | None
    consecutive_failures: int
    overdue: bool


class OemPublicationGovernanceCurrentnessRead(schemas.OemPublicationCurrentnessRead):
    currentness_status: Literal[
        "NO_CURRENT_REVISION",
        "CURRENT",
        "CANDIDATE_REVIEW_REQUIRED",
        "TEMPORARY_REVISION_REVIEW_REQUIRED",
        "TEMPORARY_REVISION_ACTIVE",
        "SOURCE_CHANGE_DETECTED",
        "SOURCE_CHECK_REQUIRED",
    ]
    pending_temporary_revisions: list[schemas.OemTemporaryRevisionRead] = Field(default_factory=list)
    governed_watches: list[OemSourceWatchGovernanceRead] = Field(default_factory=list)


class ContentPositionFullRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    label: str
    position_kind: str
    required: bool
    source_reference: str
    metadata_json: dict[str, Any]


class ContentComponentFullRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    definition_code: str
    position_code: str
    description: str
    component_class: str
    accepted_part_numbers_json: list[str]
    life_limit_json: dict[str, Any]
    metadata_json: dict[str, Any]
    source_reference: str


class ContentRevisionFullRead(schemas.ContentRevisionRead):
    sources: list[schemas.ContentSourceRead] = Field(default_factory=list)
    positions: list[ContentPositionFullRead] = Field(default_factory=list)
    components: list[ContentComponentFullRead] = Field(default_factory=list)
    tasks: list[schemas.ContentTaskRead] = Field(default_factory=list)
    resources: list[schemas.ContentResourceRead] = Field(default_factory=list)


class ContentRevisionExtendedDiffRead(BaseModel):
    base_revision_id: str
    target_revision_id: str
    added_sources: list[str]
    removed_sources: list[str]
    changed_sources: list[str]
    added_positions: list[str]
    removed_positions: list[str]
    changed_positions: list[str]
    added_components: list[str]
    removed_components: list[str]
    changed_components: list[str]
    added_tasks: list[str]
    removed_tasks: list[str]
    changed_tasks: list[str]
    unchanged_tasks: int
    added_resources: list[str]
    removed_resources: list[str]
    changed_resources: list[str]


class PageRead(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[dict[str, Any]]


class OemSourceIntakeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    publication_id: str
    publication_revision_id: str
    temporary_revision_id: str | None
    pack_id: str
    submitted_by_amo_id: str | None
    source_filename: str
    storage_locator: str | None
    checksum_sha256: str
    size_bytes: int
    detected_profile: str
    profile_confidence: str
    workbook_kind: str
    status: str
    source_manifest_json: dict[str, Any]
    warnings_json: list[Any]
    validation_summary_json: dict[str, Any]
    normalization_hash: str | None
    materialized_revision_id: str | None
    created_at: datetime
    validated_at: datetime | None
    approved_at: datetime | None
    materialized_at: datetime | None


class OemSourceIntakeRowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    intake_id: str
    sheet_name: str
    row_number: int
    row_kind: str
    identity_key: str | None
    row_hash: str
    source_json: dict[str, Any]
    normalized_json: dict[str, Any]
    status: str
    issues_json: list[Any]
    review_json: dict[str, Any]
    reviewed_by_user_id: str | None
    reviewed_at: datetime | None


class OemSourceIntakeDetailRead(OemSourceIntakeRead):
    rows: list[OemSourceIntakeRowRead] = Field(default_factory=list)


class OemSourceIntakeValidateRead(BaseModel):
    intake_id: str
    status: str
    normalization_hash: str
    total_rows: int
    valid_rows: int
    review_required_rows: int
    invalid_rows: int
    ignored_rows: int
    task_rows: int
    resource_rows: int


class OemSourceIntakeRowResolution(BaseModel):
    action: Literal["CORRECT", "ACCEPT", "IGNORE", "REJECT"]
    rationale: str = Field(min_length=1, max_length=4000)
    normalized_json: dict[str, Any] | None = None

    @model_validator(mode="after")
    def correction_requires_content(self):
        if self.action == "CORRECT" and not self.normalized_json:
            raise ValueError("CORRECT requires normalized_json")
        return self


class OemSourceIntakeApproval(BaseModel):
    expected_normalization_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_note: str = Field(min_length=1, max_length=4000)


class OemSourceIntakeMaterialize(BaseModel):
    revision_code: str = Field(min_length=1, max_length=40)
    expected_normalization_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    change_summary: str | None = Field(default=None, max_length=8000)


class ContentRevisionWithdraw(BaseModel):
    decision_note: str = Field(min_length=1, max_length=4000)


class PublicationStatusDecision(BaseModel):
    status: Literal["ACTIVE", "INACTIVE"]
    decision_note: str = Field(min_length=1, max_length=4000)


class IntakeSourceBinding(BaseModel):
    publication_id: str
    publication_revision_id: str
    pack_id: str
    temporary_revision_id: str | None = None
    storage_locator: str | None = None

    @field_validator("storage_locator")
    @classmethod
    def normalize_locator(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None
