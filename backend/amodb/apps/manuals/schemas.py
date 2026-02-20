from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, Field


class ManualCreate(BaseModel):
    code: str
    title: str
    manual_type: str
    owner_role: str = "Library"


class ManualOut(BaseModel):
    id: str
    code: str
    title: str
    manual_type: str
    status: str
    current_published_rev_id: str | None

    class Config:
        from_attributes = True


class RevisionCreate(BaseModel):
    rev_number: str
    issue_number: str | None = None
    effective_date: date | None = None
    notes: str | None = None
    requires_authority_approval_bool: bool = False


class RevisionOut(BaseModel):
    id: str
    manual_id: str
    rev_number: str
    issue_number: str | None
    status_enum: str
    effective_date: date | None
    published_at: datetime | None
    immutable_locked: bool


class TransitionRequest(BaseModel):
    action: str = Field(description="submit_department_review|approve_quality|approve_regulator|publish|archive")
    comment: str | None = None


class AcknowledgeRequest(BaseModel):
    acknowledgement_text: str


class ExportCreate(BaseModel):
    controlled_bool: bool = False
    watermark_uncontrolled_bool: bool = True
    version_label: str | None = None


class PrintLogCreate(BaseModel):
    controlled_copy_no: str | None = None
    recipient: str | None = None
    purpose: str | None = None


class DiffSummaryOut(BaseModel):
    revision_id: str
    baseline_revision_id: str | None
    summary_json: dict


class WorkflowOut(BaseModel):
    revision_id: str
    status: str
    requires_authority_approval: bool
    history: list[dict]


class MasterListEntry(BaseModel):
    manual_id: str
    code: str
    title: str
    current_revision: str | None
    current_status: str
    pending_ack_count: int
