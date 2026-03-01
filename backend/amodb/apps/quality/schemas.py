# backend/amodb/apps/quality/schemas.py
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, EmailStr

from amodb.apps.accounts.models import AccountRole
from .enums import (
    CARActionType,
    CARPriority,
    CARProgram,
    CARStatus,
    QMSNotificationSeverity,
    QMSDomain,
    QMSDocType,
    QMSDocStatus,
    QMSDistributionFormat,
    QMSRetentionCategory,
    QMSRevisionLifecycleStatus,
    QMSSecurityLevel,
    QMSPhysicalCopyStatus,
    QMSCustodyAction,
    QMSChangeRequestStatus,
    QMSAuditKind,
    QMSAuditStatus,
    QMSAuditScheduleFrequency,
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
    security_level: QMSSecurityLevel = QMSSecurityLevel.INTERNAL
    retention_category: QMSRetentionCategory = QMSRetentionCategory.MAINT_RECORD_5Y
    owner_user_id: Optional[str] = None


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
    security_level: QMSSecurityLevel
    retention_category: QMSRetentionCategory
    owner_user_id: Optional[str]

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
    version_semver: Optional[str] = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    lifecycle_status: QMSRevisionLifecycleStatus = QMSRevisionLifecycleStatus.DRAFT

    issued_date: Optional[date] = None
    entered_date: Optional[date] = None

    pages_affected: Optional[str] = None
    tracking_serial: Optional[str] = None
    change_summary: Optional[str] = None

    is_temporary: bool = False
    temporary_expires_on: Optional[date] = None

    file_ref: Optional[str] = None
    sha256: Optional[str] = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    primary_storage_provider: Optional[str] = None
    primary_storage_key: Optional[str] = None
    primary_storage_etag: Optional[str] = None
    byte_size: Optional[int] = None
    mime_type: Optional[str] = None

    approved_by_authority: bool = False
    authority_ref: Optional[str] = None
    approved_by_user_id: Optional[str] = None
    approved_at: Optional[datetime] = None


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
    version_semver: Optional[str]
    lifecycle_status: QMSRevisionLifecycleStatus
    sha256: Optional[str]
    primary_storage_provider: Optional[str]
    primary_storage_key: Optional[str]
    primary_storage_etag: Optional[str]
    byte_size: Optional[int]
    mime_type: Optional[str]

    approved_by_authority: bool
    authority_ref: Optional[str]
    approved_by_user_id: Optional[str]
    approved_at: Optional[datetime]

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
    auditee_email: Optional[str] = None
    auditee_user_id: Optional[str] = None
    lead_auditor_user_id: Optional[str] = None
    observer_auditor_user_id: Optional[str] = None
    assistant_auditor_user_id: Optional[str] = None

    planned_start: Optional[date] = None
    planned_end: Optional[date] = None


class QMSAuditUpdate(BaseModel):
    status: Optional[QMSAuditStatus] = None

    scope: Optional[str] = None
    criteria: Optional[str] = None
    auditee: Optional[str] = None
    auditee_email: Optional[str] = None
    auditee_user_id: Optional[str] = None
    lead_auditor_user_id: Optional[str] = None
    observer_auditor_user_id: Optional[str] = None
    assistant_auditor_user_id: Optional[str] = None

    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    actual_start: Optional[date] = None
    actual_end: Optional[date] = None

    report_file_ref: Optional[str] = None
    checklist_file_ref: Optional[str] = None


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
    auditee_email: Optional[str]
    auditee_user_id: Optional[str]

    lead_auditor_user_id: Optional[str]
    observer_auditor_user_id: Optional[str]
    assistant_auditor_user_id: Optional[str]

    planned_start: Optional[date]
    planned_end: Optional[date]
    actual_start: Optional[date]
    actual_end: Optional[date]

    report_file_ref: Optional[str]
    checklist_file_ref: Optional[str]
    retention_until: Optional[date]
    upcoming_notice_sent_at: Optional[datetime]
    day_of_notice_sent_at: Optional[datetime]

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


class QMSFindingVerify(BaseModel):
    objective_evidence: Optional[str] = None
    verified_at: Optional[datetime] = None


class QMSFindingAcknowledge(BaseModel):
    acknowledged_by_name: Optional[str] = None
    acknowledged_by_email: Optional[EmailStr] = None
    acknowledged_at: Optional[datetime] = None


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
    verified_at: Optional[datetime] = None
    verified_by_user_id: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by_user_id: Optional[str] = None
    acknowledged_by_name: Optional[str] = None
    acknowledged_by_email: Optional[str] = None

    created_at: datetime


class QMSAuditScheduleCreate(BaseModel):
    domain: QMSDomain
    kind: QMSAuditKind = QMSAuditKind.INTERNAL
    frequency: QMSAuditScheduleFrequency = QMSAuditScheduleFrequency.MONTHLY
    title: str = Field(min_length=1, max_length=255)
    scope: Optional[str] = None
    criteria: Optional[str] = None
    auditee: Optional[str] = None
    auditee_email: Optional[EmailStr] = None
    auditee_user_id: Optional[str] = None
    lead_auditor_user_id: Optional[str] = None
    observer_auditor_user_id: Optional[str] = None
    assistant_auditor_user_id: Optional[str] = None
    duration_days: int = Field(default=1, ge=1, le=90)
    next_due_date: date


class QMSAuditScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    domain: QMSDomain
    kind: QMSAuditKind
    frequency: QMSAuditScheduleFrequency
    title: str
    scope: Optional[str]
    criteria: Optional[str]
    auditee: Optional[str]
    auditee_email: Optional[str]
    auditee_user_id: Optional[str]
    lead_auditor_user_id: Optional[str]
    observer_auditor_user_id: Optional[str]
    assistant_auditor_user_id: Optional[str]
    duration_days: int
    next_due_date: date
    last_run_at: Optional[datetime]
    is_active: bool
    created_by_user_id: Optional[str]
    created_at: datetime


class QMSCAPUpsert(BaseModel):
    root_cause: Optional[str] = None
    containment_action: Optional[str] = None
    corrective_action: Optional[str] = None
    preventive_action: Optional[str] = None

    responsible_user_id: Optional[str] = None
    due_date: Optional[date] = None
    evidence_ref: Optional[str] = None
    verified_at: Optional[datetime] = None
    verified_by_user_id: Optional[str] = None
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
    verified_at: Optional[datetime]
    verified_by_user_id: Optional[str]

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


class CockpitActionItemOut(BaseModel):
    id: str
    kind: str
    title: str
    status: str
    priority: str
    due_date: Optional[date] = None
    assignee_user_id: Optional[str] = None




class AuditClosureTrendPointOut(BaseModel):
    period_start: date
    period_end: date
    closed_count: int
    audit_ids: list[str]


class MostCommonFindingTrendPointOut(BaseModel):
    period_start: date
    finding_type: str
    count: int




class QMSManpowerAvailabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: str
    status: str
    effective_from: datetime
    effective_to: Optional[datetime] = None
    note: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    updated_at: datetime


class QMSManpowerAvailabilityUpsert(BaseModel):
    user_id: str
    status: str
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    note: Optional[str] = None


class QMSManpowerOut(BaseModel):
    scope: str
    total_employees: int
    by_role: dict[str, int]
    availability: Optional[dict[str, int]] = None
    by_department: Optional[list[dict[str, int | str]]] = None
    updated_at: datetime


class QMSCockpitSnapshotOut(BaseModel):
    generated_at: datetime
    pending_acknowledgements: int
    audits_open: int
    audits_total: int
    findings_overdue: int
    findings_open_total: int
    documents_active: int
    documents_draft: int
    documents_obsolete: int
    change_requests_open: int
    cars_open_total: int
    cars_overdue: int
    training_records_expiring_30d: int
    training_records_expired: int
    training_records_unverified: int
    training_deferrals_pending: int
    suppliers_active: int
    suppliers_inactive: int
    tasks_due_today: int = 0
    tasks_overdue: int = 0
    change_control_pending_approvals: int = 0
    events_hold_count: int = 0
    events_new_count: int = 0
    manpower: Optional[QMSManpowerOut] = None
    audit_closure_trend: list[AuditClosureTrendPointOut]
    most_common_finding_trend_12m: list[MostCommonFindingTrendPointOut]
    action_queue: list[CockpitActionItemOut]


# -----------------------------
# Corrective Action Requests (CAR)
# -----------------------------


class CARCreate(BaseModel):
    program: CARProgram = CARProgram.QUALITY
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1)
    priority: CARPriority = CARPriority.MEDIUM
    due_date: Optional[date] = None
    target_closure_date: Optional[date] = None
    assigned_to_user_id: Optional[str] = None
    finding_id: UUID
    evidence_required: bool = True


class CARUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    summary: Optional[str] = None
    priority: Optional[CARPriority] = None
    status: Optional[CARStatus] = None
    due_date: Optional[date] = None
    target_closure_date: Optional[date] = None
    assigned_to_user_id: Optional[str] = None
    closed_at: Optional[datetime] = None
    reminder_interval_days: Optional[int] = Field(default=None, ge=1, le=90)
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    preventive_action: Optional[str] = None


class CAROut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    program: CARProgram
    car_number: str
    title: str
    summary: str
    priority: CARPriority
    status: CARStatus
    due_date: Optional[date]
    target_closure_date: Optional[date]
    closed_at: Optional[datetime]
    escalated_at: Optional[datetime]
    finding_id: UUID
    requested_by_user_id: Optional[str]
    assigned_to_user_id: Optional[str]
    invite_token: str
    reminder_interval_days: int
    next_reminder_at: Optional[datetime]
    containment_action: Optional[str] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    preventive_action: Optional[str] = None
    evidence_ref: Optional[str] = None
    submitted_by_name: Optional[str] = None
    submitted_by_email: Optional[str] = None
    submitted_at: Optional[datetime] = None
    root_cause_text: Optional[str] = None
    root_cause_status: str
    root_cause_review_note: Optional[str] = None
    capa_text: Optional[str] = None
    capa_status: str
    capa_review_note: Optional[str] = None
    evidence_required: bool
    evidence_received_at: Optional[datetime] = None
    evidence_verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class CARActionCreate(BaseModel):
    action_type: CARActionType = CARActionType.COMMENT
    message: str = Field(min_length=1)


class CARActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    car_id: UUID
    action_type: CARActionType
    message: str
    actor_user_id: Optional[str]
    created_at: datetime


class CARAssigneeOut(BaseModel):
    id: str
    full_name: str
    email: Optional[str] = None
    staff_code: Optional[str] = None
    role: AccountRole
    department_id: Optional[str] = None
    department_code: Optional[str] = None
    department_name: Optional[str] = None


class CARInviteOut(BaseModel):
    car_id: UUID
    invite_token: str
    invite_url: str
    next_reminder_at: Optional[datetime]
    car_number: str
    title: str
    summary: str
    priority: CARPriority
    status: CARStatus
    due_date: Optional[date]
    target_closure_date: Optional[date]


class CARInviteUpdate(BaseModel):
    containment_action: Optional[str] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    preventive_action: Optional[str] = None
    evidence_ref: Optional[str] = None
    target_closure_date: Optional[date] = None
    due_date: Optional[date] = None
    submitted_by_name: Optional[str] = Field(default=None, max_length=255)
    submitted_by_email: Optional[str] = Field(default=None, max_length=255)
    root_cause_text: Optional[str] = None
    capa_text: Optional[str] = None


class CARReviewUpdate(BaseModel):
    root_cause_status: Optional[str] = None
    capa_status: Optional[str] = None
    message: Optional[str] = None
    root_cause_review_note: Optional[str] = None
    capa_review_note: Optional[str] = None


class CARAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    car_id: UUID
    filename: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    uploaded_at: datetime
    download_url: str


class QMSNotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: str
    message: str
    severity: QMSNotificationSeverity
    created_by_user_id: Optional[str]
    created_at: datetime
    read_at: Optional[datetime]


class AuditorStatsOut(BaseModel):
    user_id: str
    audits_total: int
    audits_open: int
    audits_closed: int
    lead_audits: int
    observer_audits: int
    assistant_audits: int


class QMSUploadRevisionOut(BaseModel):
    revision_id: UUID
    sha256: str
    viewer_url: str


class QMSPhysicalCopyRequest(BaseModel):
    revision_id: UUID
    count: int = Field(ge=1, le=200)
    base_serial: str = Field(min_length=3, max_length=80)
    storage_location_path: Optional[str] = None


class QMSPhysicalCopyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    digital_revision_id: UUID
    copy_serial_number: str
    current_holder_user_id: Optional[str]
    storage_location_path: Optional[str]
    status: QMSPhysicalCopyStatus
    is_controlled_copy: bool
    copy_number: int
    voided_at: Optional[datetime]
    replaced_by_copy_id: Optional[UUID]


class QMSCustodyActionCreate(BaseModel):
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    notes: Optional[str] = None


class QMSCustodyLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    physical_copy_id: UUID
    user_id: Optional[str]
    action: QMSCustodyAction
    occurred_at: datetime
    gps_lat: Optional[float]
    gps_lng: Optional[float]
    notes: Optional[str]


class QMSPhysicalVerifyOut(BaseModel):
    serial: str
    status: str
    current: bool
    approved_version: Optional[str] = None


class QMSIssueRevisionRequest(BaseModel):
    doc_id: UUID
    issue_no: int = Field(ge=0)
    rev_no: int = Field(ge=0)
    version_semver: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    change_summary: Optional[str] = None


class QMSDamageReportRequest(BaseModel):
    storage_location_path: Optional[str] = None
    notes: Optional[str] = None


class QMSDamageReportOut(BaseModel):
    old_copy_id: UUID
    new_copy_id: UUID
    old_serial: str
    new_serial: str
