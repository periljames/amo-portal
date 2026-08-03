from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


ReliabilitySourceType = Literal[
    "TECH_LOG",
    "FLIGHT_OPERATIONS",
    "MEL_CDL",
    "MAINTENANCE",
    "TECH_RECORDS",
    "COMPONENT_SHOP",
    "EHM",
    "QMS",
    "SMS",
    "PROCUREMENT",
    "MANUAL",
]


class CapabilitySnapshot(BaseModel):
    capabilities: List[str] = Field(default_factory=list)
    superuser: bool = False


class ReliabilitySourceCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=255)
    source_type: ReliabilitySourceType
    transport: Literal["PUSH", "POLL", "INTERNAL"] = "PUSH"
    mapping_version: str = "1"
    configuration_json: Dict[str, Any] = Field(default_factory=dict)
    poll_interval_minutes: Optional[int] = Field(default=None, ge=5, le=43200)


class ReliabilitySourceRead(ORMModel):
    id: str
    amo_id: str
    code: str
    name: str
    source_type: str
    status: str
    transport: str
    mapping_version: str
    configuration_json: Dict[str, Any]
    poll_interval_minutes: Optional[int]
    next_poll_at: Optional[datetime]
    last_received_at: Optional[datetime]
    last_success_at: Optional[datetime]
    last_failure_at: Optional[datetime]
    last_cursor: Optional[str]
    created_at: datetime
    updated_at: datetime


class ReliabilityBatchIngest(BaseModel):
    records: List[Dict[str, Any]] = Field(min_length=1, max_length=5000)
    metadata_json: Dict[str, Any] = Field(default_factory=dict)


class ReliabilityIngestionBatchRead(ORMModel):
    id: str
    amo_id: str
    source_id: str
    status: str
    content_hash: str
    record_count: int
    valid_count: int
    duplicate_count: int
    invalid_count: int
    metadata_json: Dict[str, Any]
    error_summary: Optional[str]
    received_at: datetime
    completed_at: Optional[datetime]


class ReliabilityIngestionResult(BaseModel):
    batch: ReliabilityIngestionBatchRead
    created_event_ids: List[int] = Field(default_factory=list)
    duplicate_external_ids: List[str] = Field(default_factory=list)
    rejected_records: List[Dict[str, Any]] = Field(default_factory=list)


class ReliabilityDataQualityIssueRead(ORMModel):
    id: str
    amo_id: str
    source_id: Optional[str]
    batch_id: Optional[str]
    record_id: Optional[str]
    issue_code: str
    severity: str
    status: str
    message: str
    details_json: Dict[str, Any]
    resolution: Optional[str]
    resolved_at: Optional[datetime]
    created_at: datetime


class DataQualityResolution(BaseModel):
    resolution: str = Field(min_length=3, max_length=4000)
    status: Literal["RESOLVED", "WAIVED"] = "RESOLVED"


class OccurrenceProvenance(BaseModel):
    event_id: int
    source: Optional[ReliabilitySourceRead] = None
    batch: Optional[ReliabilityIngestionBatchRead] = None
    external_id: Optional[str] = None
    payload_hash: Optional[str] = None
    validation_status: Optional[str] = None
    validation_errors: List[Any] = Field(default_factory=list)
    raw_payload: Optional[Dict[str, Any]] = None
    interruption: Optional[Dict[str, Any]] = None


class FracasLifecycleRead(ORMModel):
    id: str
    amo_id: str
    fracas_case_id: int
    stage: str
    triage_disposition: Optional[str]
    containment_required: bool
    containment_complete: bool
    problem_statement: Optional[str]
    root_cause_method: Optional[str]
    root_cause_json: Dict[str, Any]
    risk_assessment_json: Dict[str, Any]
    effectiveness_due_date: Optional[date]
    reopened_count: int
    owner_user_id: Optional[str]
    stage_entered_at: datetime
    created_at: datetime
    updated_at: datetime


class FracasLifecycleUpdate(BaseModel):
    containment_required: Optional[bool] = None
    containment_complete: Optional[bool] = None
    problem_statement: Optional[str] = Field(default=None, max_length=12000)
    root_cause_method: Optional[str] = Field(default=None, max_length=80)
    root_cause_json: Optional[Dict[str, Any]] = None
    risk_assessment_json: Optional[Dict[str, Any]] = None
    effectiveness_due_date: Optional[date] = None
    owner_user_id: Optional[str] = None


class FracasTransitionRequest(BaseModel):
    to_stage: Literal[
        "TRIAGE",
        "ACCEPTED",
        "REJECTED",
        "MERGED",
        "CONTAINMENT",
        "INVESTIGATION",
        "ROOT_CAUSE_REVIEW",
        "ACTION_APPROVAL",
        "IMPLEMENTATION",
        "EFFECTIVENESS",
        "CLOSED",
        "REOPENED",
    ]
    decision: str = Field(min_length=2, max_length=80)
    rationale: str = Field(min_length=5, max_length=12000)
    payload_json: Dict[str, Any] = Field(default_factory=dict)


class FracasEvidenceCreate(BaseModel):
    evidence_type: Literal[
        "TECH_LOG",
        "TASK_CARD",
        "SHOP_REPORT",
        "PHOTO",
        "DOCUMENT",
        "CALCULATION",
        "INTERVIEW",
        "QMS",
        "SMS",
        "OTHER",
    ]
    reference_type: Optional[str] = Field(default=None, max_length=60)
    reference_id: Optional[str] = Field(default=None, max_length=128)
    reference_url: Optional[str] = Field(default=None, max_length=4000)
    title: str = Field(min_length=2, max_length=255)
    description: Optional[str] = Field(default=None, max_length=12000)
    metadata_json: Dict[str, Any] = Field(default_factory=dict)


class FracasEvidenceRead(ORMModel):
    id: str
    amo_id: str
    lifecycle_id: str
    evidence_type: str
    reference_type: Optional[str]
    reference_id: Optional[str]
    reference_url: Optional[str]
    title: str
    description: Optional[str]
    source_hash: str
    metadata_json: Dict[str, Any]
    captured_at: datetime
    captured_by_user_id: Optional[str]


class FracasStageEventRead(ORMModel):
    id: str
    lifecycle_id: str
    from_stage: Optional[str]
    to_stage: str
    decision: str
    rationale: str
    payload_json: Dict[str, Any]
    previous_hash: Optional[str]
    event_hash: str
    actor_user_id: Optional[str]
    created_at: datetime


class EffectivenessReviewCreate(BaseModel):
    review_date: date
    metric_code: Optional[str] = Field(default=None, max_length=80)
    baseline_value: Optional[Decimal] = None
    current_value: Optional[Decimal] = None
    acceptance_criteria: str = Field(min_length=5, max_length=12000)
    outcome: Literal["EFFECTIVE", "PARTIAL", "INEFFECTIVE", "INSUFFICIENT_DATA"]
    evidence_json: List[Dict[str, Any]] = Field(default_factory=list)
    notes: Optional[str] = Field(default=None, max_length=12000)


class EffectivenessReviewApproval(BaseModel):
    rationale: str = Field(min_length=5, max_length=12000)


class EffectivenessReviewRead(ORMModel):
    id: str
    lifecycle_id: str
    review_date: date
    metric_code: Optional[str]
    baseline_value: Optional[Decimal]
    current_value: Optional[Decimal]
    acceptance_criteria: str
    outcome: str
    evidence_json: List[Dict[str, Any]]
    notes: Optional[str]
    reviewer_user_id: Optional[str]
    approved_by_user_id: Optional[str]
    approved_at: Optional[datetime]
    created_at: datetime


class ProgrammeCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=255)
    description: Optional[str] = Field(default=None, max_length=12000)
    owner_user_id: Optional[str] = None


class ProgrammeRead(ORMModel):
    id: str
    amo_id: str
    code: str
    name: str
    description: Optional[str]
    status: str
    owner_user_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class ProgrammeVersionCreate(BaseModel):
    revision: str = Field(min_length=1, max_length=40)
    change_summary: str = Field(min_length=5, max_length=12000)
    regulatory_profiles: List[Literal["EASA_CAMO", "EASA_PART145_PROVIDER", "FAA_CASS", "FAA_PART145", "ICAO"]]
    scope_json: Dict[str, Any]
    data_sources_json: List[Dict[str, Any]] = Field(default_factory=list)
    reporting_json: Dict[str, Any] = Field(default_factory=dict)
    responsibility_matrix_json: Dict[str, Any]
    authority_required: bool = False
    effective_from: Optional[date] = None

    @model_validator(mode="after")
    def validate_responsibility(self):
        required = {"programme_owner", "analysis_provider", "decision_authority"}
        missing = sorted(required - set(self.responsibility_matrix_json))
        if missing:
            raise ValueError(f"responsibility_matrix_json is missing: {', '.join(missing)}")
        return self


class ProgrammeVersionRead(ORMModel):
    id: str
    amo_id: str
    programme_id: str
    revision: str
    status: str
    effective_from: Optional[date]
    effective_to: Optional[date]
    change_summary: str
    regulatory_profiles: List[str]
    scope_json: Dict[str, Any]
    data_sources_json: List[Dict[str, Any]]
    reporting_json: Dict[str, Any]
    responsibility_matrix_json: Dict[str, Any]
    approval_json: Dict[str, Any]
    authority_required: bool
    approved_by_user_id: Optional[str]
    approved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ProgrammeTransitionRequest(BaseModel):
    to_status: Literal["IN_REVIEW", "APPROVED", "EFFECTIVE", "SUPERSEDED", "REJECTED"]
    rationale: str = Field(min_length=5, max_length=12000)


class MetricDefinitionCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=255)
    description: Optional[str] = Field(default=None, max_length=12000)
    scope_type: Literal["FLEET", "AIRCRAFT", "ATA", "COMPONENT", "ENGINE"] = "FLEET"
    method: Literal["RATE", "COUNT", "PERCENT", "MTBUR", "NFF_RATE"] = "RATE"
    numerator_event_types: List[str] = Field(default_factory=list)
    denominator_type: Literal["FH", "FC", "FLIGHTS", "DAYS", "POPULATION", "NONE"] = "FH"
    multiplier: Decimal = Decimal("100")
    window_days: int = Field(default=30, ge=1, le=3650)
    schedule_interval_minutes: int = Field(default=1440, ge=60, le=525600)
    minimum_exposure: Decimal = Decimal("1")
    direction: Literal["ABOVE", "BELOW", "TWO_SIDED"] = "ABOVE"
    formula_version: str = Field(default="1", max_length=40)


class MetricDefinitionRead(ORMModel):
    id: str
    programme_version_id: str
    code: str
    name: str
    description: Optional[str]
    scope_type: str
    method: str
    numerator_event_types: List[str]
    denominator_type: str
    multiplier: Decimal
    window_days: int
    schedule_interval_minutes: int
    minimum_exposure: Decimal
    direction: str
    formula_version: str
    active: bool
    next_run_at: Optional[datetime]
    last_run_at: Optional[datetime]


class ThresholdCreate(BaseModel):
    version: str = Field(min_length=1, max_length=40)
    caution_value: Optional[Decimal] = None
    alert_value: Optional[Decimal] = None
    lower_caution_value: Optional[Decimal] = None
    lower_alert_value: Optional[Decimal] = None
    minimum_exposure: Optional[Decimal] = None
    rationale: str = Field(min_length=5, max_length=12000)
    effective_from: Optional[date] = None


class ThresholdRead(ORMModel):
    id: str
    metric_definition_id: str
    version: str
    status: str
    caution_value: Optional[Decimal]
    alert_value: Optional[Decimal]
    lower_caution_value: Optional[Decimal]
    lower_alert_value: Optional[Decimal]
    minimum_exposure: Optional[Decimal]
    rationale: str
    effective_from: Optional[date]
    effective_to: Optional[date]
    approved_by_user_id: Optional[str]
    approved_at: Optional[datetime]


class ThresholdTransitionRequest(BaseModel):
    to_status: Literal["APPROVED", "EFFECTIVE", "SUPERSEDED", "REJECTED"]
    rationale: str = Field(min_length=5, max_length=12000)


class CalculationExecuteRequest(BaseModel):
    metric_definition_id: str
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    scope_type: Optional[Literal["FLEET", "AIRCRAFT", "ATA", "COMPONENT", "ENGINE"]] = None
    scope_id: Optional[str] = None


class CalculationRunRead(ORMModel):
    id: str
    metric_definition_id: str
    scope_type: str
    scope_id: str
    period_start: date
    period_end: date
    numerator: Optional[Decimal]
    denominator: Optional[Decimal]
    value: Optional[Decimal]
    confidence_lower: Optional[Decimal]
    confidence_upper: Optional[Decimal]
    sample_size: int
    small_fleet: bool
    status: str
    formula_version: str
    source_cutoff_at: datetime
    source_lineage_json: Dict[str, Any]
    result_hash: str
    scheduled: bool
    created_at: datetime


class AnalyticsRow(BaseModel):
    scope_type: str
    scope_id: str
    label: str
    events: int
    exposure: Decimal
    rate: Optional[Decimal]
    confidence_lower: Optional[Decimal]
    confidence_upper: Optional[Decimal]
    small_fleet: bool
    status: str
    details: Dict[str, Any] = Field(default_factory=dict)


class AnalyticsResponse(BaseModel):
    generated_at: datetime
    period_start: date
    period_end: date
    scope_type: str
    denominator_type: str
    multiplier: Decimal
    rows: List[AnalyticsRow]


class MeetingCreate(BaseModel):
    programme_version_id: Optional[str] = None
    meeting_type: str = Field(default="MONTHLY_RELIABILITY", max_length=40)
    title: str = Field(min_length=2, max_length=255)
    scheduled_at: datetime
    data_cutoff_at: Optional[datetime] = None
    agenda_json: List[Dict[str, Any]] = Field(default_factory=list)
    attendees_json: List[Dict[str, Any]] = Field(default_factory=list)
    quorum_json: Dict[str, Any] = Field(default_factory=dict)


class MeetingRead(ORMModel):
    id: str
    programme_version_id: Optional[str]
    meeting_type: str
    title: str
    scheduled_at: datetime
    status: str
    data_cutoff_at: Optional[datetime]
    agenda_json: List[Dict[str, Any]]
    attendees_json: List[Dict[str, Any]]
    quorum_json: Dict[str, Any]
    minutes: Optional[str]
    chaired_by_user_id: Optional[str]
    approved_by_user_id: Optional[str]
    approved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class MeetingTransitionRequest(BaseModel):
    to_status: Literal["AGENDA_LOCKED", "HELD", "APPROVED", "CLOSED", "CANCELLED"]
    minutes: Optional[str] = Field(default=None, max_length=30000)
    rationale: str = Field(min_length=3, max_length=12000)


class MeetingDecisionCreate(BaseModel):
    decision_type: str = Field(min_length=2, max_length=40)
    title: str = Field(min_length=2, max_length=255)
    decision: str = Field(min_length=3, max_length=12000)
    rationale: str = Field(min_length=3, max_length=12000)
    dissent: Optional[str] = Field(default=None, max_length=12000)
    linked_entity_type: Optional[str] = Field(default=None, max_length=60)
    linked_entity_id: Optional[str] = Field(default=None, max_length=128)
    owner_user_id: Optional[str] = None
    due_date: Optional[date] = None


class MeetingDecisionRead(ORMModel):
    id: str
    meeting_id: str
    decision_type: str
    title: str
    decision: str
    rationale: str
    dissent: Optional[str]
    linked_entity_type: Optional[str]
    linked_entity_id: Optional[str]
    owner_user_id: Optional[str]
    due_date: Optional[date]
    status: str
    created_at: datetime


class ChangeProposalCreate(BaseModel):
    programme_version_id: Optional[str] = None
    source_type: str = Field(min_length=2, max_length=60)
    source_id: str = Field(min_length=1, max_length=128)
    proposal_type: Literal["AMP_TASK", "INTERVAL", "THRESHOLD", "PROCEDURE", "SUPPLIER", "MAINTENANCE", "OTHER"]
    title: str = Field(min_length=2, max_length=255)
    problem_statement: str = Field(min_length=5, max_length=12000)
    proposed_change_json: Dict[str, Any]
    impact_assessment_json: Dict[str, Any] = Field(default_factory=dict)
    owner_user_id: Optional[str] = None
    effective_from: Optional[date] = None
    effectiveness_due_date: Optional[date] = None


class ChangeProposalRead(ORMModel):
    id: str
    programme_version_id: Optional[str]
    source_type: str
    source_id: str
    proposal_type: str
    title: str
    problem_statement: str
    proposed_change_json: Dict[str, Any]
    impact_assessment_json: Dict[str, Any]
    simulation_json: Dict[str, Any]
    status: str
    approval_json: Dict[str, Any]
    effective_from: Optional[date]
    effectiveness_due_date: Optional[date]
    owner_user_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class ChangeTransitionRequest(BaseModel):
    to_status: Literal[
        "TECH_REVIEW",
        "QUALITY_REVIEW",
        "APPROVED",
        "AUTHORITY_REVIEW",
        "IMPLEMENTED",
        "REJECTED",
        "CLOSED",
    ]
    rationale: str = Field(min_length=5, max_length=12000)
    approval_json: Dict[str, Any] = Field(default_factory=dict)


class ChangeSimulationRequest(BaseModel):
    annual_utilisation_hours: Optional[Decimal] = None
    annual_utilisation_cycles: Optional[Decimal] = None
    fleet_size: Optional[int] = Field(default=None, ge=1)
    current_interval: Optional[Decimal] = None
    proposed_interval: Optional[Decimal] = None
    average_manhours: Optional[Decimal] = None
    average_material_cost: Optional[Decimal] = None


class HandoffCreate(BaseModel):
    source_type: str = Field(min_length=2, max_length=60)
    source_id: str = Field(min_length=1, max_length=128)
    target_module: Literal["PLANNING", "MAINTENANCE", "TECH_RECORDS", "QMS", "SMS", "PROCUREMENT"]
    target_route: Optional[str] = Field(default=None, max_length=255)
    payload_json: Dict[str, Any]
    owner_user_id: Optional[str] = None


class HandoffRead(ORMModel):
    id: str
    source_type: str
    source_id: str
    target_module: str
    target_route: Optional[str]
    target_record_type: Optional[str]
    target_record_id: Optional[str]
    task_id: Optional[str]
    payload_json: Dict[str, Any]
    status: str
    owner_user_id: Optional[str]
    sent_at: Optional[datetime]
    acknowledged_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class HandoffTransitionRequest(BaseModel):
    to_status: Literal["SENT", "ACKNOWLEDGED", "COMPLETED", "REJECTED", "CANCELLED"]
    target_record_type: Optional[str] = Field(default=None, max_length=80)
    target_record_id: Optional[str] = Field(default=None, max_length=128)
    rationale: str = Field(min_length=3, max_length=12000)


class AuthoritySubmissionCreate(BaseModel):
    programme_version_id: Optional[str] = None
    change_proposal_id: Optional[str] = None
    meeting_id: Optional[str] = None
    authority_profile: Literal["EASA", "FAA", "KCAA", "ICAO", "OTHER"]
    submission_type: str = Field(min_length=2, max_length=60)
    external_reference: Optional[str] = Field(default=None, max_length=128)
    package_manifest_json: Dict[str, Any]


class AuthoritySubmissionRead(ORMModel):
    id: str
    programme_version_id: Optional[str]
    change_proposal_id: Optional[str]
    meeting_id: Optional[str]
    authority_profile: str
    submission_type: str
    status: str
    external_reference: Optional[str]
    package_manifest_json: Dict[str, Any]
    response_json: Dict[str, Any]
    submitted_by_user_id: Optional[str]
    submitted_at: Optional[datetime]
    decision_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class AuthorityTransitionRequest(BaseModel):
    to_status: Literal["READY", "SUBMITTED", "ACKNOWLEDGED", "ACCEPTED", "REJECTED", "WITHDRAWN"]
    rationale: str = Field(min_length=3, max_length=12000)
    response_json: Dict[str, Any] = Field(default_factory=dict)
    external_reference: Optional[str] = Field(default=None, max_length=128)


class AiReviewRequest(BaseModel):
    review_type: Literal["TRIAGE", "REPEAT_CLUSTER", "ROOT_CAUSE", "REPORT_SUMMARY", "EVIDENCE_GAP", "CHANGE_IMPACT"]
    entity_type: str = Field(min_length=2, max_length=60)
    entity_id: str = Field(min_length=1, max_length=128)
    instruction: Optional[str] = Field(default=None, max_length=4000)


class AiReviewRead(ORMModel):
    id: str
    review_type: str
    entity_type: str
    entity_id: str
    model_id: str
    model_version: str
    prompt_hash: str
    input_snapshot_json: Dict[str, Any]
    citations_json: List[Dict[str, Any]]
    output_json: Dict[str, Any]
    confidence: Optional[Decimal]
    advisory_only: bool
    status: str
    review_notes: Optional[str]
    created_by_user_id: Optional[str]
    reviewed_by_user_id: Optional[str]
    reviewed_at: Optional[datetime]
    created_at: datetime


class AiReviewDecision(BaseModel):
    decision: Literal["ACCEPTED", "REJECTED", "REVIEWED"]
    review_notes: str = Field(min_length=3, max_length=12000)


class AuditEventRead(ORMModel):
    id: str
    entity_type: str
    entity_id: str
    action: str
    payload_json: Dict[str, Any]
    actor_user_id: Optional[str]
    previous_hash: Optional[str]
    event_hash: str
    created_at: datetime


class ComplianceCheck(BaseModel):
    code: str
    title: str
    status: Literal["GREEN", "AMBER", "RED", "UNKNOWN"]
    detail: str
    count: Optional[int] = None
    route: Optional[str] = None


class ComplianceOverview(BaseModel):
    generated_at: datetime
    overall_status: Literal["GREEN", "AMBER", "RED", "UNKNOWN"]
    regulatory_profiles: List[str]
    checks: List[ComplianceCheck]
    disclaimer: str


class BootstrapResult(BaseModel):
    programme_id: str
    programme_version_id: str
    source_ids: List[str]
    metric_ids: List[str]
    created: Dict[str, int]
