from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ResponsibilityCreate(BaseModel):
    responsibility_type: str = Field(min_length=3, max_length=48)
    assignee_type: Literal["USER", "DEPARTMENT", "ORG_UNIT", "ROLE"]
    assignee_user_id: str | None = None
    assignee_department_id: str | None = None
    assignee_org_unit_id: str | None = None
    assignee_role: str | None = Field(default=None, max_length=96)
    revision_id: str | None = None
    is_primary: bool = True
    delegated_from_id: str | None = None
    effective_from: date
    effective_to: date | None = None
    assignment_source: Literal["MANUAL", "INHERITED", "MIGRATED", "INFERRED", "IMPORTED"] = "MANUAL"
    confidence_percent: int = Field(default=100, ge=0, le=100)
    confirmation_status: Literal[
        "DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT", "CONFIRMED"
    ] = "CONFIRMED"
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_period(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot precede effective_from")
        return self


class GovernanceDecision(BaseModel):
    decision: Literal["CONFIRMED", "REJECTED"]
    comments: str = Field(min_length=3, max_length=2000)


class LocationInput(BaseModel):
    location_key: str = Field(min_length=3, max_length=128)
    location_type: Literal["PDF", "TEXT", "SPREADSHEET", "SLIDE", "IMAGE"]
    page_number: int | None = Field(default=None, ge=1)
    normalized_rects: list[dict[str, float]] = Field(default_factory=list, max_length=100)
    exact_quote: str | None = Field(default=None, max_length=5000)
    prefix_context: str | None = Field(default=None, max_length=1000)
    suffix_context: str | None = Field(default=None, max_length=1000)
    section_id: str | None = None
    block_id: str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    sheet_name: str | None = Field(default=None, max_length=255)
    cell_range: str | None = Field(default=None, max_length=128)
    slide_number: int | None = Field(default=None, ge=1)
    object_id: str | None = Field(default=None, max_length=255)
    image_region: dict[str, Any] = Field(default_factory=dict)
    adapter_name: str = Field(min_length=2, max_length=64)
    adapter_version: str = Field(min_length=1, max_length=64)


class RelationshipCreate(BaseModel):
    source_revision_id: str | None = None
    source_location: LocationInput | None = None
    target_entity_type: str = Field(min_length=2, max_length=48)
    target_entity_id: str | None = Field(default=None, max_length=128)
    target_manual_id: str | None = None
    target_revision_id: str | None = None
    relationship_type: str = Field(min_length=3, max_length=48)
    relationship_source: Literal["MANUAL", "EXTRACTED", "INFERRED", "IMPORTED", "MIGRATED"] = "MANUAL"
    occurrence_key: str = Field(min_length=3, max_length=128)
    exact_token: str | None = Field(default=None, max_length=255)
    exact_quote: str | None = Field(default=None, max_length=5000)
    page_number: int | None = Field(default=None, ge=1)
    section_label: str | None = Field(default=None, max_length=255)
    confidence_percent: int = Field(default=100, ge=0, le=100)
    resolution_status: Literal[
        "DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT", "CONFIRMED"
    ] = "CONFIRMED"
    provenance: dict[str, Any] = Field(default_factory=dict)


class AnnotationCreate(BaseModel):
    revision_id: str
    source_sha256: str = Field(min_length=64, max_length=64)
    location: LocationInput
    annotation_type: Literal["HIGHLIGHT", "NOTE", "QUESTION", "EVIDENCE", "FINDING_LINK", "BOOKMARK"]
    color: Literal["YELLOW", "GREEN", "BLUE", "PINK", "RED"] = "YELLOW"
    visibility: Literal["PRIVATE", "TEAM", "AUDIT", "CONTROLLED_RECORD"] = "PRIVATE"
    note_text: str | None = Field(default=None, max_length=10000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    linked_entity_type: str | None = Field(default=None, max_length=48)
    linked_entity_id: str | None = Field(default=None, max_length=128)


class BackfillRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)
    dry_run: bool = True
    manual_ids: list[str] = Field(default_factory=list, max_length=5000)
    batch_limit: int = Field(default=50, ge=1, le=250)
    retry_failed: bool = True
    reconcile_hierarchy: bool = True


class BackfillResumeRequest(BaseModel):
    batch_limit: int = Field(default=50, ge=1, le=250)
    retry_failed: bool = True
