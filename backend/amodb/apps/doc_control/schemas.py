from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class DocControlSettingsIn(BaseModel):
    default_retention_years: int = 5
    default_review_interval_months: int = 24
    regulated_workflow_enabled: bool = False
    default_ack_required: bool = True


class DocControlSettingsOut(DocControlSettingsIn):
    tenant_id: str

    class Config:
        from_attributes = True


class ControlledDocumentIn(BaseModel):
    doc_id: str
    title: str
    doc_type: str
    owner_department: str
    issue_no: int = 1
    revision_no: int = 0
    version: str = "1.0"
    effective_date: Optional[date] = None
    status: str = "Draft"
    regulated_flag: bool = False
    authority_name: Optional[str] = None
    authority_approval_status: Optional[str] = None
    authority_evidence_asset_id: Optional[str] = None
    restricted_flag: bool = False
    access_policy_id: Optional[str] = None
    current_asset_id: Optional[str] = None
    physical_locations: list[dict[str, Any]] = Field(default_factory=list)


class ControlledDocumentOut(ControlledDocumentIn):
    id: str
    tenant_id: str
    next_review_due: Optional[date]

    class Config:
        from_attributes = True


class DraftIn(BaseModel):
    doc_id: str
    metadata_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    asset_id: Optional[str] = None
    status: Literal["Draft", "Review", "ApprovedInternal", "Rejected"] = "Draft"
    authority_evidence_asset_id: Optional[str] = None


class ChangeProposalIn(BaseModel):
    doc_id: str
    description: str
    attachment_asset_ids: list[str] = Field(default_factory=list)
    dept_head_decision: Optional[str] = None
    quality_decision: Optional[str] = None
    accountable_manager_decision: Optional[str] = None
    authority_status: Optional[str] = None
    authority_evidence_asset_ids: list[str] = Field(default_factory=list)


class RevisionPackageIn(BaseModel):
    doc_id: str
    revision_no: int
    reference_serial_no: str
    change_summary: str
    transmittal_notice: str
    filing_instructions: str
    replacement_pages: list[dict[str, Any]] = Field(default_factory=list)
    effective_date: date
    internal_approval_status: str = "Pending"
    authority_status: Optional[str] = None
    authority_evidence_asset_id: Optional[str] = None
    published_revision_asset_id: Optional[str] = None


class LEPIn(BaseModel):
    doc_id: str
    revision_no: int
    lep_date: date
    rows: list[dict[str, Any]]
    export_asset_id: Optional[str] = None


class TemporaryRevisionIn(BaseModel):
    doc_id: str
    tr_no: str
    effective_date: date
    expiry_date: date
    reason: str
    filing_instructions: str
    updated_lep_asset_id: Optional[str] = None
    tr_pages: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["Draft", "InForce", "Expired", "Withdrawn", "Incorporated"] = "Draft"
    incorporated_revision_package_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_window(self):
        month = self.effective_date.month + 6
        year = self.effective_date.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        import calendar
        day = min(self.effective_date.day, calendar.monthrange(year, month)[1])
        max_expiry = date(year, month, day)
        if self.expiry_date > max_expiry:
            raise ValueError("expiry_date must be <= effective_date + 6 months")
        return self


class DistributionEventIn(BaseModel):
    doc_id: str
    source_type: Literal["RevisionPackage", "TR"]
    source_id: str
    method: Literal["Portal", "Email", "Hardcopy"]
    acknowledgement_required: bool = True


class AcknowledgementIn(BaseModel):
    event_id: str
    recipient_user_id: Optional[str] = None
    copy_no: Optional[str] = None
    method: Literal["Form", "ReadReceipt"]
    evidence_asset_id: Optional[str] = None


class PublishRevisionIn(BaseModel):
    current_asset_id: str


class PublishTRIn(BaseModel):
    status: Literal["InForce", "Withdrawn", "Incorporated"]
    incorporated_revision_package_id: Optional[str] = None


class GenericOut(BaseModel):
    id: str


class EventOut(BaseModel):
    type: str
    payload: dict[str, Any]


class DashboardOut(BaseModel):
    pending_internal_approvals: int
    pending_authority_approval: int
    trs_in_force: int
    trs_expiring_30_days: int
    manuals_due_review_60_days: int
    outstanding_acknowledgements: int
    recently_published_revisions_30_days: int
