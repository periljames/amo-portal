from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class OrmModel(BaseModel):
    class Config:
        from_attributes = True


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

    @field_validator("reporting_currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.strip().upper()


class TrainingOperatingSettingsUpdate(TrainingOperatingSettingsBase):
    pass


class TrainingOperatingSettingsRead(TrainingOperatingSettingsBase, OrmModel):
    id: str
    amo_id: str
    updated_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class TrainingPlanParticipantCreate(BaseModel):
    user_id: str


class TrainingPlanParticipantRead(OrmModel):
    id: str
    amo_id: str
    plan_item_id: str
    user_id: str
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
    participant_count: int = Field(0, ge=0)
    planned_month: int | None = Field(None, ge=1, le=12)
    quarter: int | None = Field(None, ge=1, le=4)
    planned_start: date | None = None
    planned_end: date | None = None
    location: str | None = None
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
        if self.participant_ids:
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
