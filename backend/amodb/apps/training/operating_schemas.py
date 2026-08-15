from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TrainingAccessRead(BaseModel):
    capabilities: list[str]
    can_open_operating_system: bool
    self_service_only: bool
    tenant_id: str


class ActionQueueItem(BaseModel):
    key: str
    label: str
    count: int | None
    severity: Literal["INFO", "WARNING", "CRITICAL"]
    reason: str
    action_label: str
    path: str
    available: bool = True


class TrainingControlRoomRead(BaseModel):
    generated_at: datetime
    queues: list[ActionQueueItem]
    source_errors: list[str] = Field(default_factory=list)


class SourceHealthItem(BaseModel):
    source: str
    status: Literal["HEALTHY", "DEGRADED", "UNAVAILABLE", "NOT_CONFIGURED"]
    checked_at: datetime
    freshness_at: datetime | None = None
    detail: str
    retryable: bool = True
    action_path: str | None = None


class SourceHealthRead(BaseModel):
    generated_at: datetime
    overall_status: Literal["HEALTHY", "DEGRADED", "UNAVAILABLE"]
    sources: list[SourceHealthItem]


class PageMeta(BaseModel):
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)
    has_more: bool
    filtered_totals: dict[str, int | float | str | None] = Field(default_factory=dict)


class PersonComplianceRow(BaseModel):
    id: str
    full_name: str
    staff_code: str | None = None
    email: str | None = None
    position_title: str | None = None
    department: str | None = None
    active: bool
    outstanding: int = 0
    overdue: int = 0
    due_soon: int = 0
    never_completed: int = 0
    next_due: date | None = None
    next_action: str
    status: Literal["CURRENT", "DUE_SOON", "OVERDUE", "INCOMPLETE", "UNKNOWN"]
    provenance: dict[str, Any] = Field(default_factory=dict)


class PersonCompliancePage(PageMeta):
    items: list[PersonComplianceRow]


class TrainingOperatingSettingsBase(BaseModel):
    default_planning_lead_days: int = Field(45, ge=1, le=365)
    default_recurrent_window_days: int = Field(45, ge=1, le=365)
    attendance_window_minutes: int = Field(30, ge=5, le=720)
    attendance_qr_lifetime_minutes: int = Field(10, ge=1, le=60)
    competence_review_frequency_months: int = Field(24, ge=1, le=120)
    experience_review_frequency_months: int = Field(3, ge=1, le=24)
    auditor_observer_count: int = Field(3, ge=1, le=20)
    reporting_currency: str = Field("USD", min_length=3, max_length=3)
    budget_rounding_places: int = Field(2, ge=0, le=6)
    plan_form_reference: str | None = None
    budget_form_reference: str | None = None
    attendance_form_reference: str | None = None
    assessment_form_mappings: dict[str, str] = Field(default_factory=dict)
    authorization_form_mappings: dict[str, str] = Field(default_factory=dict)
    approval_roles: dict[str, list[str]] = Field(default_factory=dict)
    timezone: str = Field("UTC", min_length=1, max_length=64)
    plan_automation_enabled: bool = True
    plan_run_day: int = Field(1, ge=1, le=28)
    plan_run_hour: int = Field(2, ge=0, le=23)
    notification_policy: dict[str, Any] = Field(default_factory=dict)
    certificate_number_prefix: str = Field("TRN", min_length=1, max_length=32)
    certificate_template_reference: str | None = Field(None, max_length=128)
    certificate_signatories: list[dict[str, str]] = Field(default_factory=list, max_length=10)
    certificate_public_privacy_text: str | None = Field(None, max_length=2000)
    default_committee_positions: list[str] = Field(
        default_factory=lambda: ["QUALITY_MANAGER", "BASE_MAINTENANCE_MANAGER", "LINE_MAINTENANCE_MANAGER"],
        max_length=20,
    )
    setup_status: Literal["DRAFT", "ACTIVE"] = "DRAFT"

    @field_validator("reporting_currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.strip().upper()


class TrainingOperatingSettingsUpdate(TrainingOperatingSettingsBase):
    pass


class TrainingOperatingSettingsRead(TrainingOperatingSettingsBase, OrmModel):
    id: str | None = None
    amo_id: str
    configured: bool = False
    configuration_revision_no: int = Field(0, ge=0)
    updated_by_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SetupReadinessItem(BaseModel):
    key: str
    label: str
    status: Literal["READY", "WARNING", "BLOCKED"]
    blocking: bool
    reason: str
    action_path: str


class SetupReadinessRead(BaseModel):
    generated_at: datetime
    go_live_ready: bool
    completion_percent: int = Field(..., ge=0, le=100)
    items: list[SetupReadinessItem]


class TrainingReferenceResourceCreate(BaseModel):
    resource_type: Literal["PROVIDER", "LOCATION", "INSTRUCTOR"]
    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=2, max_length=255)
    contact_name: str | None = Field(None, max_length=255)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=64)
    address: str | None = Field(None, max_length=2000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class TrainingReferenceResourceRead(TrainingReferenceResourceCreate, OrmModel):
    id: str
    amo_id: str
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ControlledFormTemplateCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str = Field(..., min_length=2, max_length=64)
    title: str = Field(..., min_length=2, max_length=255)
    workflow: Literal["PLAN", "BUDGET", "ATTENDANCE", "ASSESSMENT", "AUTHORIZATION", "EFFECTIVENESS", "OTHER"]
    dms_document_id: str | None = None
    dms_revision_id: str | None = None
    form_schema: dict[str, Any] = Field(default_factory=dict, alias="schema_json")
    retention_rule: str | None = Field(None, max_length=255)
    effective_from: date | None = None
    effective_to: date | None = None


class ControlledFormTemplateRead(ControlledFormTemplateCreate, OrmModel):
    id: str
    amo_id: str
    revision_no: int
    status: str
    created_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ControlledFormTransition(BaseModel):
    target: Literal["ACTIVE", "RETIRED"]


class ConfigurationRevisionRead(OrmModel):
    id: str
    revision_no: int
    snapshot: dict[str, Any]
    change_summary: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime


class SetupVersionCreate(BaseModel):
    source_mode: Literal["BLANK", "TEMPLATE_PACK", "WORKBOOK"] = "BLANK"
    title: str = Field(..., min_length=2, max_length=255)
    change_summary: str | None = Field(None, max_length=4000)
    snapshot: dict[str, Any] = Field(default_factory=dict)


class SetupVersionRead(SetupVersionCreate, OrmModel):
    id: str
    amo_id: str
    version_no: int
    status: str
    validation_result: dict[str, Any] = Field(default_factory=dict)
    effective_from: datetime | None = None
    created_by_user_id: str | None = None
    reviewed_by_user_id: str | None = None
    activated_by_user_id: str | None = None
    supersedes_version_id: str | None = None
    created_at: datetime
    updated_at: datetime


class SetupVersionTransition(BaseModel):
    target: Literal["IN_REVIEW", "ACTIVE", "ROLLED_BACK"]
    reason: str | None = Field(None, max_length=4000)
    effective_from: datetime | None = None


class ChangePreviewCreate(BaseModel):
    object_type: Literal["REQUIREMENT", "RECORD", "PLAN", "CERTIFICATE", "AUTHORIZATION", "COURSE", "SESSION"]
    object_id: str | None = None
    operation: str = Field(..., min_length=2, max_length=48)
    requested_payload: dict[str, Any] = Field(default_factory=dict)


class ChangeRequestRead(ChangePreviewCreate, OrmModel):
    id: str
    amo_id: str
    status: str
    impact_summary: dict[str, Any] = Field(default_factory=dict)
    validation_result: dict[str, Any] = Field(default_factory=dict)
    source_cutoff_at: datetime
    requested_by_user_id: str | None = None
    decided_by_user_id: str | None = None
    decision_reason: str | None = None
    applied_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ChangeDecision(BaseModel):
    decision: Literal["ACCEPT", "REJECT"]
    reason: str = Field(..., min_length=3, max_length=4000)


class WorkflowStepInput(BaseModel):
    step_key: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=2, max_length=255)
    sequence_no: int = Field(1, ge=1, le=1000)
    assigned_user_id: str | None = None


class WorkflowInstanceCreate(BaseModel):
    workflow_type: Literal["QMS_36_ATTENDANCE", "QAM_51_INDUCTION", "QAM_52_COMPETENCE", "QAM_58_EXPERIENCE", "OJT", "AUTHORIZATION_APPLICATION", "CUSTOM"]
    form_template_id: str | None = None
    subject_user_id: str | None = None
    owner_user_id: str | None = None
    reviewer_user_id: str | None = None
    event_id: str | None = None
    course_id: str | None = None
    authorization_case_id: str | None = None
    title: str = Field(..., min_length=2, max_length=255)
    due_at: datetime | None = None
    data_json: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(..., min_length=8, max_length=128)
    steps: list[WorkflowStepInput] = Field(default_factory=list, max_length=500)


class WorkflowInstanceUpdate(BaseModel):
    data_json: dict[str, Any] = Field(default_factory=dict)
    due_at: datetime | None = None
    owner_user_id: str | None = None


class WorkflowStepComplete(BaseModel):
    response_json: dict[str, Any] = Field(default_factory=dict)
    signature: str | None = Field(None, max_length=500)


class WorkflowStepRead(WorkflowStepInput, OrmModel):
    id: str
    status: str
    response_json: dict[str, Any] = Field(default_factory=dict)
    signature_json: dict[str, Any] = Field(default_factory=dict)
    completed_by_user_id: str | None = None
    completed_at: datetime | None = None


class WorkflowInstanceRead(OrmModel):
    id: str
    amo_id: str
    workflow_type: str
    form_template_id: str | None = None
    form_revision_no: int | None = None
    subject_user_id: str | None = None
    owner_user_id: str | None = None
    reviewer_user_id: str | None = None
    event_id: str | None = None
    course_id: str | None = None
    authorization_case_id: str | None = None
    status: str
    title: str
    due_at: datetime | None = None
    data_json: dict[str, Any] = Field(default_factory=dict)
    validation_result: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    revision_no: int
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime
    steps: list[WorkflowStepRead] = Field(default_factory=list)


class WorkflowPage(PageMeta):
    items: list[WorkflowInstanceRead]


class WorkflowTransition(BaseModel):
    target: Literal["SUBMITTED", "RETURNED", "APPROVED", "COMPLETED", "CANCELLED"]
    comment: str | None = Field(None, max_length=4000)


class InvitationCreate(BaseModel):
    participant_user_ids: list[str] = Field(default_factory=list, min_length=1, max_length=2000)
    channels: list[Literal["IN_APP", "EMAIL"]] = Field(default_factory=lambda: ["IN_APP"])
    message: str | None = Field(None, max_length=4000)


class InvitationRead(OrmModel):
    id: str
    event_id: str
    user_id: str
    channel: str
    delivery_status: str
    attempt_count: int
    last_error: str | None = None
    rsvp_status: str
    responded_at: datetime | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class InvitationPage(PageMeta):
    items: list[InvitationRead]


class InvitationRsvp(BaseModel):
    response: Literal["ACCEPTED", "DECLINED", "TENTATIVE"]


class ReportDefinitionCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = Field(None, max_length=4000)
    dataset: Literal["PEOPLE_COMPLIANCE", "TRAINING_PLAN", "ATTENDANCE", "ASSESSMENTS", "AUTHORIZATIONS", "CERTIFICATES", "BUDGET", "AUDIT"]
    allowed_formats: list[Literal["PDF", "XLSX", "CSV"]] = Field(default_factory=lambda: ["PDF", "XLSX"])
    default_filters: dict[str, Any] = Field(default_factory=dict)
    schedule_json: dict[str, Any] = Field(default_factory=dict)
    retention_days: int = Field(365, ge=1, le=3650)
    active: bool = True


class ReportDefinitionRead(ReportDefinitionCreate, OrmModel):
    id: str
    created_at: datetime
    updated_at: datetime


class ReportJobCreate(BaseModel):
    report_code: str = Field(..., min_length=2, max_length=64)
    output_format: Literal["PDF", "XLSX", "CSV"]
    filters_json: dict[str, Any] = Field(default_factory=dict)


class ReportJobRead(ReportJobCreate, OrmModel):
    id: str
    status: str
    scope_manifest: dict[str, Any] = Field(default_factory=dict)
    artifact_checksum: str | None = None
    error_text: str | None = None
    requested_by_user_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime


class ReportJobPage(PageMeta):
    items: list[ReportJobRead]


class SavedViewCreate(BaseModel):
    workspace: str = Field(..., min_length=2, max_length=48)
    name: str = Field(..., min_length=2, max_length=100)
    filter_json: dict[str, Any] = Field(default_factory=dict)
    column_json: dict[str, Any] = Field(default_factory=dict)
    density: Literal["COMPACT", "COMFORTABLE"] = "COMPACT"
    is_default: bool = False


class SavedViewRead(SavedViewCreate, OrmModel):
    id: str
    created_at: datetime
    updated_at: datetime


class AutomationRunRead(OrmModel):
    id: str
    period_year: int
    period_month: int
    trigger: str
    status: str
    plan_id: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    error_text: str | None = None
    actor_user_id: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


class AutomationStatusRead(BaseModel):
    enabled: bool
    timezone: str
    run_day: int
    run_hour: int
    next_run_at: datetime | None = None
    last_run: AutomationRunRead | None = None


class CertificateLifecycleAction(BaseModel):
    reason: str = Field(..., min_length=8, max_length=2000)


class CertificateIssueRead(OrmModel):
    id: str
    record_id: str
    certificate_number: str
    issued_at: datetime
    issued_by_user_id: str | None = None
    artifact_hash: str | None = None
    qr_value: str | None = None
    status: str


class CertificateEligibilityItem(BaseModel):
    record_id: str
    user_id: str
    person_name: str
    staff_code: str | None = None
    course_id: str
    course_code: str
    course_name: str
    completion_date: date
    valid_until: date | None = None
    eligible: bool
    blockers: list[dict[str, str]] = Field(default_factory=list)


class CertificateEligibilityPage(PageMeta):
    items: list[CertificateEligibilityItem]


class CertificateBatchIssueCreate(BaseModel):
    record_ids: list[str] = Field(..., min_length=1, max_length=500)
    reason: str = Field(..., min_length=8, max_length=2000)


class CertificateBatchIssueItem(BaseModel):
    record_id: str
    status: Literal["ISSUED", "BLOCKED", "NOT_FOUND", "ALREADY_ISSUED"]
    certificate_id: str | None = None
    certificate_number: str | None = None
    blockers: list[dict[str, str]] = Field(default_factory=list)


class CertificateBatchIssueRead(BaseModel):
    requested: int
    issued: int
    blocked: int
    items: list[CertificateBatchIssueItem]


class TrainingPlanParticipantCreate(BaseModel):
    user_id: str
    person_name: str | None = None
    staff_code: str | None = None
    last_completion_date: date | None = None
    expiry_date: date | None = None
    planned_due_date: date | None = None
    obligation_status: str = "PLANNED"
    source_type: str = "REQUIREMENT"
    source_record_id: str | None = None
    source_reference: str | None = None


class TrainingPlanParticipantRead(OrmModel):
    id: str
    amo_id: str
    plan_item_id: str
    user_id: str
    person_name_snapshot: str
    staff_code_snapshot: str | None = None
    last_completion_date: date | None = None
    expiry_date: date | None = None
    planned_due_date: date | None = None
    obligation_status: str
    source_type: str
    source_record_id: str | None = None
    source_reference: str | None = None
    status: str
    exclusion_reason: str | None = None
    created_at: datetime


class TrainingPlanItemBase(BaseModel):
    course_id: str | None = None
    course_name: str | None = None
    training_kind: str = "OTHER"
    provider_mode: str = "INTERNAL"
    provider: str | None = None
    participant_ids: list[str] = Field(default_factory=list)
    participant_obligations: list[TrainingPlanParticipantCreate] = Field(default_factory=list)
    participant_count: int = Field(0, ge=0)
    planned_month: int | None = Field(None, ge=1, le=12)
    quarter: int | None = Field(None, ge=1, le=4)
    planned_start: date | None = None
    planned_end: date | None = None
    location: str | None = None
    instructor_ids: list[str] = Field(default_factory=list)
    duration_days: int | None = Field(None, ge=0)
    justification: str | None = None
    source_type: str = "MANUAL"
    manual_reference: str | None = None
    authorization_impact: str | None = None
    priority: str = "NORMAL"
    original_currency: str = Field("USD", min_length=3, max_length=3)
    estimated_unit_cost: Decimal = Field(Decimal("0"), ge=0)
    owner_user_id: str | None = None
    notes: str | None = None

    @field_validator("original_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_dates_and_period(self) -> "TrainingPlanItemBase":
        if self.planned_start and self.planned_end and self.planned_end < self.planned_start:
            raise ValueError("planned_end must be on or after planned_start")
        if self.planned_month and not self.quarter:
            self.quarter = ((self.planned_month - 1) // 3) + 1
        if self.participant_obligations:
            self.participant_ids = list(dict.fromkeys(value.user_id for value in self.participant_obligations))
            self.participant_count = len(self.participant_ids)
        elif self.participant_ids:
            self.participant_count = len(set(self.participant_ids))
        return self


class TrainingPlanItemCreate(TrainingPlanItemBase):
    pass


class TrainingPlanItemRead(OrmModel):
    id: str
    amo_id: str
    plan_id: str
    course_id: str | None = None
    scheduled_event_id: str | None = None
    course_code_snapshot: str | None = None
    course_name_snapshot: str
    training_kind: str
    provider_mode: str
    provider: str | None = None
    participant_count: int
    planned_month: int | None = None
    quarter: int | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    location: str | None = None
    instructor_ids: list[str] = Field(default_factory=list)
    duration_days: int | None = None
    justification: str | None = None
    source_type: str
    manual_reference: str | None = None
    authorization_impact: str | None = None
    priority: str
    original_currency: str
    estimated_unit_cost: Decimal
    estimated_total_cost: Decimal
    owner_user_id: str | None = None
    notes: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime
    participants: list[TrainingPlanParticipantRead] = Field(default_factory=list)


class TrainingPlanCreate(BaseModel):
    plan_year: int = Field(..., ge=2000, le=2200)
    title: str = "Annual Training Plan"
    notes: str | None = None
    generate_from_obligations: bool = True
    items: list[TrainingPlanItemCreate] = Field(default_factory=list)


class TrainingPlanRead(OrmModel):
    id: str
    amo_id: str
    plan_year: int
    revision_no: int
    title: str
    status: str
    form_reference: str | None = None
    issue_date: date | None = None
    notes: str | None = None
    supersedes_plan_id: str | None = None
    prepared_by_user_id: str | None = None
    submitted_by_user_id: str | None = None
    reviewed_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    items: list[TrainingPlanItemRead] = Field(default_factory=list)


class TrainingPlanSummaryRead(BaseModel):
    id: str
    plan_year: int
    revision_no: int
    title: str
    status: str
    form_reference: str | None = None
    notes: str | None = None
    item_count: int = 0
    participant_count: int = 0
    estimated_total_cost: Decimal = Decimal("0")
    original_currency: str = "USD"
    created_at: datetime
    updated_at: datetime


class TrainingPlanObligationRead(BaseModel):
    key: str
    plan_item_id: str
    participant_id: str
    month: int
    course_code: str | None = None
    course_name: str
    manual_reference: str | None = None
    user_id: str
    person_name: str
    staff_code: str | None = None
    last_completion_date: date | None = None
    expiry_date: date | None = None
    planned_due_date: date | None = None
    obligation_status: str
    source_type: str
    source_record_id: str | None = None
    source_reference: str | None = None
    status: str


class TrainingPlanObligationPage(BaseModel):
    items: list[TrainingPlanObligationRead]
    total: int
    limit: int
    offset: int
    month_counts: list[int] = Field(default_factory=lambda: [0] * 12)


class TrainingPlanMatrixPerson(BaseModel):
    user_id: str
    person_name: str
    staff_code: str | None = None
    planned_due_date: date | None = None
    expiry_date: date | None = None
    obligation_status: str


class TrainingPlanMatrixCell(BaseModel):
    month: int
    personnel_count: int
    preview: list[TrainingPlanMatrixPerson] = Field(default_factory=list)


class TrainingPlanMatrixCourse(BaseModel):
    course_key: str
    course_id: str | None = None
    course_code: str | None = None
    course_name: str
    training_kind: str
    provider_mode: str
    personnel_count: int
    cells: list[TrainingPlanMatrixCell] = Field(default_factory=list)


class TrainingPlanMatrixPage(BaseModel):
    plan_id: str
    plan_year: int
    months: list[int] = Field(default_factory=lambda: list(range(1, 13)))
    items: list[TrainingPlanMatrixCourse]
    total: int
    limit: int
    offset: int
    has_more: bool
    kind_counts: dict[str, int] = Field(default_factory=dict)


class TrainingPlanMatrixPersonPage(BaseModel):
    course_key: str
    month: int
    items: list[TrainingPlanMatrixPerson]
    total: int
    limit: int
    offset: int
    has_more: bool


class ExchangeRateQuoteRead(BaseModel):
    base_currency: str
    quote_currency: str
    rate: Decimal
    rate_date: date
    quoted_at: datetime
    next_update_at: datetime | None = None
    provider: str
    source_url: str | None = None
    attribution_url: str | None = None
    cached: bool


class WorkflowDecision(BaseModel):
    comment: str | None = None


class BudgetBuildCreate(BaseModel):
    plan_id: str
    reporting_currency: str = Field("USD", min_length=3, max_length=3)
    rate_date: date
    rate_source: str = Field(..., min_length=2, max_length=255)
    exchange_rates: dict[str, Decimal] = Field(default_factory=dict)

    @field_validator("reporting_currency")
    @classmethod
    def normalize_reporting_currency(cls, value: str) -> str:
        return value.strip().upper()


class TrainingBudgetLineRead(OrmModel):
    id: str
    amo_id: str
    budget_id: str
    plan_item_id: str | None = None
    course_id: str | None = None
    course_code_snapshot: str | None = None
    course_name_snapshot: str
    training_kind: str
    provider: str | None = None
    original_currency: str
    reporting_currency: str
    unit_cost: Decimal
    trainee_count: int
    planned_amount: Decimal
    approved_amount: Decimal
    committed_amount: Decimal
    actual_amount: Decimal
    exchange_rate: Decimal
    rate_date: date
    rate_source: str
    converted_planned_amount: Decimal
    converted_approved_amount: Decimal
    converted_committed_amount: Decimal
    converted_actual_amount: Decimal
    quarter: int
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class TrainingBudgetLineUpdate(BaseModel):
    provider: str | None = Field(None, max_length=255)
    unit_cost: Decimal | None = Field(None, ge=0)
    trainee_count: int | None = Field(None, ge=0)
    approved_amount: Decimal | None = Field(None, ge=0)
    committed_amount: Decimal | None = Field(None, ge=0)
    actual_amount: Decimal | None = Field(None, ge=0)
    exchange_rate: Decimal | None = Field(None, gt=0)
    rate_date: date | None = None
    rate_source: str | None = Field(None, min_length=2, max_length=255)
    quarter: int | None = Field(None, ge=1, le=4)
    notes: str | None = Field(None, max_length=2000)


class TrainingBudgetRead(OrmModel):
    id: str
    amo_id: str
    plan_id: str
    revision_no: int
    status: str
    reporting_currency: str
    form_reference: str | None = None
    notes: str | None = None
    supersedes_budget_id: str | None = None
    prepared_by_user_id: str | None = None
    reviewed_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    lines: list[TrainingBudgetLineRead] = Field(default_factory=list)
    quarter_totals: dict[str, Decimal] = Field(default_factory=dict)
    annual_totals: dict[str, Decimal] = Field(default_factory=dict)


class AuditorQualificationRead(BaseModel):
    user_id: str
    completed_observer_audits: int
    required_observer_audits: int
    remaining_observer_audits: int
    status: Literal["QUALIFIED", "IN_PROGRESS"]
    source: str
    audit_ids: list[str] = Field(default_factory=list)


class AttendanceWindowCreate(BaseModel):
    event_id: str
    lifetime_minutes: int | None = Field(None, ge=1, le=60)
    sign_in_path: str | None = Field(None, min_length=1, max_length=400)

    @field_validator("sign_in_path")
    @classmethod
    def validate_sign_in_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = value.strip()
        if not path.startswith("/") or path.startswith("//") or "://" in path:
            raise ValueError("sign_in_path must be a same-origin application path")
        return path


class AttendanceWindowRead(OrmModel):
    id: str
    amo_id: str
    event_id: str
    status: str
    attendance_code: str | None = None
    expires_at: datetime
    opened_by_user_id: str | None = None
    opened_at: datetime
    closed_by_user_id: str | None = None
    closed_at: datetime | None = None
    certified_by_user_id: str | None = None
    certified_at: datetime | None = None
    register_revision: int
    certification_note: str | None = None
    sign_in_path: str | None = None
    notifications_sent: int = 0
    notifications_queued: int = 0
    notification_delivery_status: Literal["QUEUED", "NONE", "UNKNOWN"] = "UNKNOWN"


class AttendanceSelfSignCreate(BaseModel):
    attendance_code: str = Field(..., min_length=20, max_length=256)
    attestation: str = Field("I confirm that I attended this training session.", min_length=8, max_length=500)
    idempotency_key: str = Field(..., min_length=8, max_length=128)


class AttendanceAdminMarkCreate(BaseModel):
    user_id: str
    status: Literal["PRESENT", "ABSENT", "PARTIAL"] = "PRESENT"
    method: Literal["TRAINER", "MANUAL", "IMPORT"] = "TRAINER"
    note: str | None = None
    idempotency_key: str = Field(..., min_length=8, max_length=128)


class AttendanceRosterItemRead(BaseModel):
    participant_id: str
    user_id: str
    full_name: str
    staff_code: str | None = None
    participant_status: str
    attendance_entry_id: str | None = None
    attendance_status: str | None = None
    method: str | None = None
    signed_at: datetime | None = None


class AttendanceRosterPage(BaseModel):
    items: list[AttendanceRosterItemRead]
    total: int
    signed_count: int
    limit: int
    offset: int


class AttendanceCorrectionCreate(BaseModel):
    new_status: Literal["PRESENT", "ABSENT", "PARTIAL"]
    reason: str = Field(..., min_length=8, max_length=2000)


class AttendanceCertificationCreate(BaseModel):
    note: str | None = Field(None, max_length=2000)


class AttendanceEntryRead(OrmModel):
    id: str
    amo_id: str
    window_id: str | None = None
    event_id: str
    participant_id: str
    user_id: str
    status: str
    method: str
    signed_by_user_id: str | None = None
    signed_at: datetime
    attestation: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class AssessmentQuestionCreate(BaseModel):
    sequence_no: int = Field(..., ge=1)
    question_text: str = Field(..., min_length=2, max_length=4000)
    response_type: Literal["TEXT", "NUMBER", "BOOLEAN", "SINGLE_CHOICE", "MULTI_CHOICE", "RATING"] = "TEXT"
    answer_options: list[str] = Field(default_factory=list)
    evaluation_rule: dict[str, Any] = Field(default_factory=dict)
    answer_key: Any | None = None
    marks: Decimal = Field(Decimal("0"), ge=0)
    mandatory: bool = False
    manual_reference: str | None = Field(None, max_length=255)


class AssessmentQuestionRead(AssessmentQuestionCreate, OrmModel):
    id: str
    amo_id: str
    template_id: str
    active: bool
    created_at: datetime


class AssessmentTemplateCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=2, max_length=255)
    purpose: str | None = None
    assessment_type: Literal[
        "WRITTEN", "ORAL", "PRACTICAL", "OJT", "OBSERVATION", "SUPERVISOR_REVIEW", "PERFORMANCE_REVIEW", "TRAINING_EFFECTIVENESS"
    ]
    outcome_scheme: Literal["NUMERIC", "PASS_FAIL", "COMPETENT", "SATISFACTORY", "STRUCTURED"] = "PASS_FAIL"
    effective_from: date | None = None
    effective_to: date | None = None
    pass_threshold: Decimal | None = Field(None, ge=0, le=100)
    mandatory_criteria: list[str] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)
    assessor_capability: str = "training.assessment.perform"
    approval_required: bool = True
    manual_reference: str | None = None
    questions: list[AssessmentQuestionCreate] = Field(default_factory=list, max_length=200)


class AssessmentTemplateRead(OrmModel):
    id: str
    amo_id: str
    code: str
    name: str
    purpose: str | None = None
    assessment_type: str
    outcome_scheme: str
    revision_no: int
    effective_from: date | None = None
    effective_to: date | None = None
    pass_threshold: Decimal | None = None
    mandatory_criteria: list[str] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)
    assessor_capability: str
    approval_required: bool
    manual_reference: str | None = None
    active: bool
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime
    questions: list[AssessmentQuestionRead] = Field(default_factory=list)


class AssessmentCreate(BaseModel):
    template_id: str
    candidate_user_id: str
    course_id: str | None = None
    event_id: str | None = None
    authorization_case_id: str | None = None
    assessor_user_id: str | None = None
    planned_at: datetime | None = None


class AssessmentSubmit(BaseModel):
    results: dict[str, Any] = Field(default_factory=dict)
    score: Decimal | None = Field(None, ge=0, le=100)
    outcome: str | None = None
    comments: str | None = None


class AssessmentReview(BaseModel):
    decision: Literal["APPROVED", "FAILED", "NOT_COMPETENT", "RETURNED"]
    comment: str | None = None


class AssessmentRead(OrmModel):
    id: str
    amo_id: str
    template_id: str
    candidate_user_id: str
    course_id: str | None = None
    event_id: str | None = None
    authorization_case_id: str | None = None
    assessor_user_id: str | None = None
    reviewer_user_id: str | None = None
    planned_at: datetime | None = None
    performed_at: datetime | None = None
    status: str
    results: dict[str, Any] = Field(default_factory=dict)
    score: Decimal | None = None
    outcome: str | None = None
    comments: str | None = None
    review_decision: str | None = None
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None
    supersedes_assessment_id: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ExperienceLogCreate(BaseModel):
    candidate_user_id: str
    log_type: str = "EXPERIENCE"
    aircraft_component_task: str | None = None
    activity: str = Field(..., min_length=3)
    supervisor_user_id: str | None = None
    activity_date: date
    duration_hours: Decimal | None = Field(None, ge=0)
    reference: str | None = None
    training_file_id: str | None = None


class ExperienceReviewCreate(BaseModel):
    candidate_user_id: str
    authorization_case_id: str | None = None
    review_status: Literal["SATISFACTORY", "GAPS_IDENTIFIED", "REJECTED"]
    reviewed_on: date
    evidence_summary: str | None = None
    training_file_id: str | None = None


class AuthorizationCaseCreate(BaseModel):
    candidate_user_id: str
    authorisation_type_id: str
    requested_scope: str | None = None
    requested_privileges: list[str] = Field(default_factory=list)
    owner_user_id: str | None = None
    application_date: date = Field(default_factory=date.today)
    required_assessment_types: list[str] = Field(default_factory=lambda: ["WRITTEN", "PRACTICAL", "ORAL"])
    manual_references: list[str] = Field(default_factory=list)
    required_committee_positions: list[str] = Field(default_factory=list)


class ReadinessItem(BaseModel):
    key: str
    label: str
    status: Literal["CURRENT", "COMPLETE", "MISSING", "OVERDUE", "NOT_STARTED", "BLOCKED", "FAILED", "READY", "NOT_APPLICABLE"]
    blocking: bool
    reason: str
    source: str


class AuthorizationReadiness(BaseModel):
    case_id: str
    overall_status: Literal["NOT_READY", "READY_FOR_ASSESSMENT", "ASSESSMENT_IN_PROGRESS", "READY_FOR_COMMITTEE", "DECISION_REQUIRED", "APPROVED", "REJECTED", "DEFERRED"]
    items: list[ReadinessItem]
    next_required_action: str
    action_owner: str | None = None
    computed_at: datetime


class AuthorizationCaseRead(OrmModel):
    id: str
    amo_id: str
    candidate_user_id: str
    authorisation_type_id: str
    requested_scope: str | None = None
    requested_privileges: list[str] = Field(default_factory=list)
    requested_by_user_id: str | None = None
    owner_user_id: str | None = None
    application_date: date
    status: str
    required_assessment_types: list[str] = Field(default_factory=list)
    manual_references: list[str] = Field(default_factory=list)
    required_committee_positions: list[str] = Field(default_factory=list)
    readiness_snapshot: dict[str, Any] = Field(default_factory=dict)
    readiness_computed_at: datetime | None = None
    recommendation: str | None = None
    decision: str | None = None
    restrictions: str | None = None
    decision_at: datetime | None = None
    issued_user_authorisation_id: str | None = None
    created_at: datetime
    updated_at: datetime


class CommitteeDecisionCreate(BaseModel):
    position_code: str = Field(..., min_length=2, max_length=80)
    decision: Literal["APPROVE", "REJECT", "DEFER"]
    comments: str | None = None


class AuthorizationIssueCreate(BaseModel):
    effective_from: date
    expires_at: date | None = None
    restrictions: str | None = None


class AuthorizationRecommendationCreate(BaseModel):
    recommendation: Literal["RECOMMEND_APPROVAL", "RECOMMEND_RESTRICTION", "DO_NOT_RECOMMEND", "DEFER"]
    rationale: str = Field(..., min_length=3, max_length=4000)
    proposed_restrictions: str | None = Field(None, max_length=4000)


class AuthorizationLifecycleAction(BaseModel):
    action: Literal["RESTRICT", "SUSPEND", "WITHDRAW"]
    reason: str = Field(..., min_length=3, max_length=4000)
    restrictions: str | None = Field(None, max_length=4000)


class EffectivenessCreate(BaseModel):
    course_id: str
    event_id: str | None = None
    user_id: str | None = None
    level: int = Field(..., ge=1, le=4)
    evaluation_period_start: date | None = None
    evaluation_period_end: date | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    rating: Decimal | None = None
    conclusion: str | None = None
    causation_claimed: bool = False
    status: str = "DRAFT"


class EffectivenessRead(OrmModel):
    id: str
    amo_id: str
    course_id: str
    event_id: str | None = None
    user_id: str | None = None
    level: int
    evaluation_period_start: date | None = None
    evaluation_period_end: date | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    rating: Decimal | None = None
    conclusion: str | None = None
    causation_claimed: bool
    reviewer_user_id: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class CompetenceReviewCreate(BaseModel):
    candidate_user_id: str
    review_type: str = "CONTINUED_COMPETENCE"
    period_start: date
    period_end: date
    authorization_case_id: str | None = None
    course_id: str | None = None
    criteria: list[dict[str, Any]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    outcome: Literal["COMPETENT", "TRAINING_REQUIRED", "SUPERVISED_EXPERIENCE_REQUIRED", "REASSESSMENT_REQUIRED", "RESTRICT", "ESCALATE"]
    strengths: str | None = None
    gaps: str | None = None
    actions: str | None = None
    reassessment_due: date | None = None


class RemedialActionCreate(BaseModel):
    candidate_user_id: str
    source_assessment_id: str | None = None
    source_competence_review_id: str | None = None
    course_id: str | None = None
    gap: str = Field(..., min_length=3)
    required_activity: str = Field(..., min_length=3)
    owner_user_id: str | None = None
    due_date: date
    supervised_experience_required: bool = False
    reassessment_required: bool = True


class NextBatchCandidate(BaseModel):
    user_id: str
    full_name: str
    staff_code: str | None = None
    department: str | None = None
    status: str
    due_date: date | None = None
    days_remaining: int | None = None
    existing_booking: str | None = None
    availability_conflict: str | None = None
    authorization_impact: str | None = None
    eligible: bool
    rank_reason: str


class NextBatchRead(BaseModel):
    course_id: str
    course_code: str
    course_name: str
    candidates: list[NextBatchCandidate]


class CourseAuditException(BaseModel):
    user_id: str
    full_name: str
    staff_code: str | None = None
    exception_code: str
    severity: Literal["INFO", "WARNING", "CRITICAL"]
    detail: str
    correction_path: str


class CourseAuditRead(BaseModel):
    course_id: str
    course_code: str
    course_name: str
    required_people: int
    current_people: int
    overdue_people: int
    never_completed_people: int
    exceptions: list[CourseAuditException]
