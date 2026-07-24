from __future__ import annotations

from datetime import date, datetime
from pathlib import PurePosixPath
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from .schemas import QMSAuditOut


AuditStageState = Literal[
    "NOT_READY",
    "READY",
    "IN_PROGRESS",
    "BLOCKED",
    "COMPLETE",
    "LOCKED",
]


def _safe_legacy_document_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = str(value).replace("\\", "/")
    name = PurePosixPath(normalized).name.strip()
    return name or None


class QualityAuditSafeOut(QMSAuditOut):
    """Compatibility audit DTO that never serializes private storage paths."""

    @field_serializer("checklist_file_ref", "report_file_ref")
    def serialize_document_ref(self, value: str | None) -> str | None:
        return _safe_legacy_document_name(value)


class QualityAuditStageActionOut(BaseModel):
    id: str
    label: str
    enabled: bool = True
    helper: str | None = None
    path: str | None = None
    method: str | None = None


class QualityAuditStageOut(BaseModel):
    id: str
    label: str
    state: AuditStageState
    complete: bool
    active: bool
    metric: str | None = None
    helper: str | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    completed_at: datetime | None = None
    completed_by_user_id: str | None = None
    primary_action: QualityAuditStageActionOut | None = None


class QualityAuditWorkflowV2Out(BaseModel):
    audit_id: UUID
    current_stage_id: str
    current_stage_label: str
    lifecycle_status: str
    percent_complete: int
    findings_total: int
    findings_open: int
    cars_total: int
    cars_open: int
    evidence_total: int
    evidence_pending: int
    checklist_uploaded: bool
    checklist_complete: bool
    report_uploaded: bool
    report_issued: bool
    stages: list[QualityAuditStageOut] = Field(default_factory=list)


class QualityAuditWorkspaceV2Out(BaseModel):
    audit: QualityAuditSafeOut
    workflow: QualityAuditWorkflowV2Out


class QualityAuditDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    audit_id: UUID
    version_number: int
    parent_version_id: UUID | None = None
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    lifecycle_status: str
    created_at: datetime
    created_by_user_id: str | None = None
    committed_at: datetime | None = None
    issued_at: datetime | None = None
    issued_by_user_id: str | None = None
    source_type: str | None = None
    fillable: str | None = None
    field_count: int | None = None
    issue_label: str | None = None
    distribution_status: str | None = None
    download_url: str


class QualityAuditChecklistMetadataOut(BaseModel):
    available: bool
    current: QualityAuditDocumentOut | None = None
    source: QualityAuditDocumentOut | None = None
    versions: list[QualityAuditDocumentOut] = Field(default_factory=list)
    portal_item_count: int = 0
    portal_completed_count: int = 0
    explicitly_completed: bool = False
    read_only: bool = False
    read_only_reason: str | None = None


class QualityAuditReportMetadataOut(BaseModel):
    available: bool
    current_draft: QualityAuditDocumentOut | None = None
    issued: QualityAuditDocumentOut | None = None
    versions: list[QualityAuditDocumentOut] = Field(default_factory=list)
    read_only: bool = False
    read_only_reason: str | None = None


class QualityAuditPreviousReportOut(BaseModel):
    available: bool
    document_id: UUID | None = None
    filename: str | None = None
    issued_at: datetime | None = None
    issue_label: str | None = None
    download_url: str | None = None


class QualityAuditPreviousAuditOut(BaseModel):
    id: UUID
    audit_ref: str
    title: str
    status: str
    planned_start: date | None = None
    actual_end: date | None = None
    lead_auditor_name: str | None = None
    findings_total: int = 0
    open_carryovers: int = 0
    possible_repeat_findings: int = 0
    match_reason: str
    report: QualityAuditPreviousReportOut
    workspace_path: str


class QualityAuditCarryoverFindingOut(BaseModel):
    finding_id: UUID
    finding_ref: str | None = None
    level: str
    requirement_ref: str | None = None
    description: str
    target_close_date: date | None = None
    car_id: UUID | None = None
    car_number: str | None = None
    car_status: str | None = None
    overdue: bool = False


class QualityAuditNoticeEventOut(BaseModel):
    id: str
    action: str
    label: str
    occurred_at: datetime
    actor_user_id: str | None = None
    actor_name: str | None = None
    detail: str | None = None


class QualityAuditActionItemOut(BaseModel):
    id: str
    label: str
    state: Literal["PENDING", "READY", "COMPLETE", "BLOCKED", "WARNING"]
    owner_label: str | None = None
    due_at: datetime | None = None
    helper: str | None = None
    action_path: str | None = None


class QualityAuditReadinessOut(BaseModel):
    ready: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QualityAuditWarRoomContextOut(BaseModel):
    audit: QualityAuditSafeOut
    workflow: QualityAuditWorkflowV2Out
    readiness: QualityAuditReadinessOut
    previous_audits: list[QualityAuditPreviousAuditOut] = Field(default_factory=list)
    carryover_findings: list[QualityAuditCarryoverFindingOut] = Field(default_factory=list)
    notice_history: list[QualityAuditNoticeEventOut] = Field(default_factory=list)
    action_queue: list[QualityAuditActionItemOut] = Field(default_factory=list)
    checklist: QualityAuditChecklistMetadataOut
    report: QualityAuditReportMetadataOut


class QualityAuditStageTransitionIn(BaseModel):
    note: str | None = Field(default=None, max_length=4000)
    metadata: dict[str, Any] | None = None


class QualityAuditChecklistCommitIn(BaseModel):
    version_id: UUID
    field_count: int | None = Field(default=None, ge=0, le=10000)
    fillable: Literal["UNKNOWN", "YES", "NO"] = "UNKNOWN"
    note: str | None = Field(default=None, max_length=4000)


class QualityAuditReportIssueIn(BaseModel):
    version_id: UUID
    issue_label: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=4000)


class QualityAuditEvidenceReviewIn(BaseModel):
    entity_type: Literal[
        "CHECKLIST_VERSION",
        "FINDING_ATTACHMENT",
        "CAR_ATTACHMENT",
        "REPORT_VERSION",
        "OTHER",
    ]
    entity_id: str = Field(min_length=1, max_length=64)
    status: Literal["PENDING", "ACCEPTED", "REJECTED"]
    note: str | None = Field(default=None, max_length=4000)


class QualityAuditEvidenceReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    audit_id: UUID
    entity_type: str
    entity_id: str
    status: str
    note: str | None = None
    reviewed_by_user_id: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
