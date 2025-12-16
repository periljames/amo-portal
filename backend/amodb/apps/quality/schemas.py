# backend/amodb/apps/quality/schemas.py
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    QMSDomain,
    QMSDocType,
    QMSDocStatus,
    QMSDistributionFormat,
    QMSChangeRequestStatus,
    QMSAuditKind,
    QMSAuditStatus,
    QMSFindingType,
    QMSFindingSeverity,
    FindingLevel,
    QMSCAPStatus,
)


class QMSDocumentCreate(BaseModel):
    domain: QMSDomain
    doc_type: QMSDocType
    doc_code: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    restricted_access: bool = False


class QMSDocumentUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    restricted_access: Optional[bool] = None
    status: Optional[QMSDocStatus] = None


class QMSDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    domain: QMSDomain
    doc_type: QMSDocType
    doc_code: str
    title: str
    description: Optional[str]
    status: QMSDocStatus

    current_issue_no: Optional[int]
    current_rev_no: Optional[int]
    effective_date: Optional[date]
    restricted_access: bool
    current_file_ref: Optional[str]

    created_by_user_id: Optional[str]
    updated_by_user_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class QMSDocumentRevisionCreate(BaseModel):
    issue_no: int = Field(ge=0)
    rev_no: int = Field(ge=0)

    issued_date: Optional[date] = None
    entered_date: Optional[date] = None

    pages_affected: Optional[str] = None
    tracking_serial: Optional[str] = None
    change_summary: Optional[str] = None

    is_temporary: bool = False
    temporary_expires_on: Optional[date] = None

    file_ref: Optional[str] = None

    approved_by_authority: bool = False
    authority_ref: Optional[str] = None


class QMSDocumentRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID

    issue_no: int
    rev_no: int

    issued_date: Optional[date]
    entered_date: Optional[date]

    pages_affected: Optional[str]
    tracking_serial: Optional[str]
    change_summary: Optional[str]

    is_temporary: bool
    temporary_expires_on: Optional[date]

    file_ref: Optional[str]

    approved_by_authority: bool
    authority_ref: Optional[str]

    created_by_user_id: Optional[str]
    created_at: datetime


class QMSPublishRevision(BaseModel):
    effective_date: date
    current_file_ref: Optional[str] = None


class QMSDistributionCreate(BaseModel):
    document_id: UUID
    revision_id: Optional[UUID] = None
    copy_number: Optional[str] = None

    holder_label: str = Field(min_length=1, max_length=255)
    holder_user_id: Optional[str] = None

    dist_format: QMSDistributionFormat = QMSDistributionFormat.SOFT_COPY
    requires_ack: bool = False


class QMSDistributionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    revision_id: Optional[UUID]

    copy_number: Optional[str]
    holder_label: str
    holder_user_id: Optional[str]

    dist_format: QMSDistributionFormat
    requires_ack: bool

    acked_at: Optional[datetime]
    acked_by_user_id: Optional[str]

    distributed_at: datetime


class QMSChangeRequestCreate(BaseModel):
    domain: QMSDomain

    petitioner_name: str = Field(min_length=1, max_length=255)
    petitioner_email: Optional[str] = None
    petitioner_phone: Optional[str] = None
    petitioner_department: Optional[str] = None

    manual_title: str = Field(min_length=1, max_length=255)
    manual_reference: Optional[str] = None
    manual_copy_no: Optional[str] = None
    manual_rev: Optional[str] = None
    manual_location: Optional[str] = None

    media_source: Optional[str] = None
    remarks: Optional[str] = None

    change_request_text: str = Field(min_length=1)


class QMSChangeRequestUpdate(BaseModel):
    status: Optional[QMSChangeRequestStatus] = None
    manual_owner_decision: Optional[str] = None
    qa_decision: Optional[str] = None
    librarian_decision: Optional[str] = None
    review_feedback: Optional[str] = None


class QMSChangeRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    domain: QMSDomain

    petitioner_name: str
    petitioner_email: Optional[str]
    petitioner_phone: Optional[str]
    petitioner_department: Optional[str]

    manual_title: str
    manual_reference: Optional[str]
    manual_copy_no: Optional[str]
    manual_rev: Optional[str]
    manual_location: Optional[str]

    media_source: Optional[str]
    remarks: Optional[str]

    change_request_text: str
    status: QMSChangeRequestStatus

    manual_owner_decision: Optional[str]
    qa_decision: Optional[str]
    librarian_decision: Optional[str]
    review_feedback: Optional[str]

    created_by_user_id: Optional[str]
    submitted_at: datetime


class QMSAuditCreate(BaseModel):
    domain: QMSDomain
    kind: QMSAuditKind = QMSAuditKind.INTERNAL

    audit_ref: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)

    scope: Optional[str] = None
    criteria: Optional[str] = None
    auditee: Optional[str] = None

    planned_start: Optional[date] = None
    planned_end: Optional[date] = None


class QMSAuditUpdate(BaseModel):
    status: Optional[QMSAuditStatus] = None

    scope: Optional[str] = None
    criteria: Optional[str] = None
    auditee: Optional[str] = None

    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    actual_start: Optional[date] = None
    actual_end: Optional[date] = None

    report_file_ref: Optional[str] = None


class QMSAuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    domain: QMSDomain
    kind: QMSAuditKind
    status: QMSAuditStatus

    audit_ref: str
    title: str

    scope: Optional[str]
    criteria: Optional[str]
    auditee: Optional[str]

    lead_auditor_user_id: Optional[str]

    planned_start: Optional[date]
    planned_end: Optional[date]
    actual_start: Optional[date]
    actual_end: Optional[date]

    report_file_ref: Optional[str]
    retention_until: Optional[date]

    created_by_user_id: Optional[str]
    created_at: datetime


class QMSFindingCreate(BaseModel):
    finding_ref: Optional[str] = None
    finding_type: QMSFindingType = QMSFindingType.NON_CONFORMITY

    severity: QMSFindingSeverity = QMSFindingSeverity.MINOR
    level: Optional[FindingLevel] = None  # if None, inferred from severity

    requirement_ref: Optional[str] = None
    description: str = Field(min_length=1)
    objective_evidence: Optional[str] = None

    safety_sensitive: bool = False

    target_close_date: Optional[date] = None  # if None, computed from level


class QMSFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    audit_id: UUID

    finding_ref: Optional[str]
    finding_type: QMSFindingType

    severity: QMSFindingSeverity
    level: FindingLevel

    requirement_ref: Optional[str]
    description: str
    objective_evidence: Optional[str]

    safety_sensitive: bool

    target_close_date: Optional[date]
    closed_at: Optional[datetime]

    created_at: datetime


class QMSCAPUpsert(BaseModel):
    root_cause: Optional[str] = None
    containment_action: Optional[str] = None
    corrective_action: Optional[str] = None
    preventive_action: Optional[str] = None

    responsible_user_id: Optional[str] = None
    due_date: Optional[date] = None
    evidence_ref: Optional[str] = None
    status: Optional[QMSCAPStatus] = None


class QMSCAPOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    finding_id: UUID

    root_cause: Optional[str]
    containment_action: Optional[str]
    corrective_action: Optional[str]
    preventive_action: Optional[str]

    responsible_user_id: Optional[str]
    due_date: Optional[date]
    evidence_ref: Optional[str]

    status: QMSCAPStatus

    created_at: datetime
    updated_at: datetime


class QMSDashboardOut(BaseModel):
    domain: Optional[QMSDomain] = None

    documents_total: int
    documents_active: int
    documents_draft: int
    documents_obsolete: int

    distributions_pending_ack: int

    change_requests_total: int
    change_requests_open: int  # submitted + under_review

    audits_total: int
    audits_open: int  # planned + in_progress + cap_open

    findings_open_total: int
    findings_open_level_1: int
    findings_open_level_2: int
    findings_open_level_3: int

    findings_overdue_total: int
