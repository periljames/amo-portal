from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class WorkbookImportDecision(BaseModel):
    row_id: str
    decision: str


class WorkbookImportCommitRequest(BaseModel):
    decisions: list[WorkbookImportDecision] = Field(default_factory=list)
    force_reimport: bool = False


class WorkbookImportSheetRead(BaseModel):
    id: str
    sheet_name: str
    visibility: str
    classification: str
    portal_destination: str
    is_operational: bool
    display_order: int
    status: str
    total_rows: int
    processed_rows: int
    created_count: int
    updated_count: int
    unchanged_count: int
    skipped_count: int
    failed_count: int
    review_count: int
    message: Optional[str] = None

    class Config:
        from_attributes = True


class WorkbookImportRowRead(BaseModel):
    id: str
    sheet_name: str
    source_row: int
    entity_type: str
    source_key: Optional[str] = None
    display_label: Optional[str] = None
    proposed_action: str
    status: str
    decision_required: bool
    decision: Optional[str] = None
    decision_options: list[str] = Field(default_factory=list)
    changes: list[dict[str, Any]] = Field(default_factory=list)
    issue_code: Optional[str] = None
    issue_message: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    committed_entity_id: Optional[str] = None


class WorkbookImportRowPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[WorkbookImportRowRead]


class TrainingWorkbookImportJobRead(BaseModel):
    id: str
    amo_id: str
    actor_user_id: Optional[str] = None
    filename: str
    size_bytes: int
    file_sha256: str
    duplicate_of_job_id: Optional[str] = None
    status: str
    stage: str
    current_sheet: Optional[str] = None
    current_record_label: Optional[str] = None
    processed_rows: int
    total_rows: int
    created_count: int
    updated_count: int
    unchanged_count: int
    skipped_count: int
    failed_count: int
    review_count: int
    summary: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    cancel_requested: bool
    created_at: datetime
    started_at: Optional[datetime] = None
    preview_completed_at: Optional[datetime] = None
    committed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime
    sheets: list[WorkbookImportSheetRead] = Field(default_factory=list)


class TrainingWorkbookImportJobPage(BaseModel):
    items: list[TrainingWorkbookImportJobRead]
    total: int
    limit: int
    offset: int
    has_more: bool


class PersonnelLicenceRead(BaseModel):
    id: str
    personnel_profile_id: str
    user_id: Optional[str] = None
    authority: str
    country: Optional[str] = None
    licence_number: str
    category_code: Optional[str] = None
    category_source: Optional[str] = None
    issued_on: Optional[date] = None
    expires_on: Optional[date] = None
    expiry_source_record_id: Optional[str] = None
    expiry_source_course_id: Optional[str] = None
    expiry_synced_at: Optional[datetime] = None
    internal_stamp_no: Optional[str] = None
    initial_authorization_date: Optional[date] = None
    status: str
    is_primary: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TrainingRoleGroupRead(BaseModel):
    id: str
    code: str
    description: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class TrainingRoleGroupWrite(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=2000)
    is_active: bool = True


class TrainingPersonRoleRead(BaseModel):
    id: str
    person_id: str
    personnel_profile_id: Optional[str] = None
    user_id: Optional[str] = None
    role_group_id: str
    role_group_code: Optional[str] = None
    person_name: Optional[str] = None
    staff_code: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool


class TrainingPersonRoleWrite(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    role_group_id: str = Field(min_length=1, max_length=64)
    department: Optional[str] = Field(default=None, max_length=255)
    position: Optional[str] = Field(default=None, max_length=255)
    notes: Optional[str] = Field(default=None, max_length=2000)
    is_active: bool = True


class TrainingCourseRoleRuleRead(BaseModel):
    id: str
    course_id: str
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    role_group_id: str
    role_group_code: Optional[str] = None
    is_required: bool
    requirement_type: str
    notes: Optional[str] = None
    is_active: bool


class TrainingCourseRoleRuleWrite(BaseModel):
    course_id: str = Field(min_length=1, max_length=64)
    role_group_id: str = Field(min_length=1, max_length=64)
    is_required: bool = True
    requirement_type: str = Field(default="GENERAL", min_length=1, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=2000)
    is_active: bool = True
