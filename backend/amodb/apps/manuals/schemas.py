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
    manual_type: str | None = None
    owner_role: str | None = None
    current_issue_number: str | None = None
    current_effective_date: date | None = None
    source_type: str | None = None
    source_filename: str | None = None
    source_mime_type: str | None = None
    page_count: int | None = None
    section_count: int = 0
    block_count: int = 0
    last_published_at: datetime | None = None
    last_opened_at: datetime | None = None
    resume_anchor_slug: str | None = None
    resume_page_number: int | None = None
    open_count: int = 0


class LifecycleTransitionRequest(BaseModel):
    action: str = Field(description="save_draft|submit_for_review|verify_compliance|sign_approval|publish|reject_to_draft")
    comment: str | None = None


class LifecycleTransitionOut(BaseModel):
    revision_id: str
    state: str
    previous_state: str
    approval_chain_reset: bool = False


class ManualFeaturedEntry(BaseModel):
    manual_id: str
    code: str
    title: str
    manual_type: str
    current_revision: str | None = None
    open_count: int = 0


class DocxPreviewOut(BaseModel):
    filename: str
    heading: str
    paragraph_count: int
    sample: list[str]
    outline: list[str] = []
    metadata: dict = Field(default_factory=dict)
    excerpt: str = ""
    source_type: str = "DOCX"
    page_count: int | None = None


class OCRVerifyOut(BaseModel):
    revision_id: str
    detected_ref: str | None = None
    detected_date: date | None = None
    typed_ref: str | None = None
    typed_date: date | None = None
    ref_match: bool = False
    date_match: bool = False
    verified: bool = False
    text_excerpt: str = ""


class StampOverlayRequest(BaseModel):
    signer_name: str
    signer_role: str
    stamp_label: str = "APPROVED FOR SUBMISSION"
    controlled_bool: bool = False


class StampOverlayOut(BaseModel):
    revision_id: str
    export_id: str
    storage_uri: str
    sha256: str


class ManualUploadPreviewOut(BaseModel):
    filename: str
    heading: str
    paragraph_count: int
    sample: list[str]
    outline: list[str] = []
    metadata: dict = Field(default_factory=dict)
    excerpt: str = ""
    source_type: str
    page_count: int | None = None


class ManualReaderProgressRequest(BaseModel):
    last_section_id: str | None = None
    last_anchor_slug: str | None = None
    last_page_number: int | None = None
    scroll_percent: int = 0
    zoom_percent: int = 100
    bookmark_label: str | None = None
    bookmarks: list[dict] = Field(default_factory=list)


class ManualReaderProgressOut(BaseModel):
    revision_id: str
    user_id: str
    last_section_id: str | None = None
    last_anchor_slug: str | None = None
    last_page_number: int | None = None
    scroll_percent: int = 0
    zoom_percent: int = 100
    bookmark_label: str | None = None
    bookmarks: list[dict] = Field(default_factory=list)
    last_opened_at: datetime | None = None
    updated_at: datetime | None = None


class ManualSearchHitOut(BaseModel):
    manual_id: str
    revision_id: str | None = None
    manual_code: str
    manual_title: str
    manual_type: str | None = None
    section_id: str | None = None
    section_heading: str | None = None
    anchor_slug: str | None = None
    page_number: int | None = None
    excerpt: str
    source_type: str | None = None
    score: int = 0
