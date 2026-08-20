from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AuthorityCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    jurisdiction: str | None = None
    authority_type: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class AuthorityRead(ORMModel):
    id: str
    amo_id: str
    code: str
    name: str
    jurisdiction: str | None = None
    authority_type: str | None = None
    status: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class GovernanceRuleCreate(BaseModel):
    rule_code: str = Field(min_length=2, max_length=128)
    authority_id: str | None = None
    source_type: str = "MANUAL"
    source_document_id: str | None = None
    source_revision_id: str | None = None
    source_title: str | None = None
    source_section: str | None = None
    source_paragraph: str | None = None
    applicability: dict[str, Any] = Field(default_factory=dict)
    value_json: dict[str, Any] = Field(default_factory=dict)
    condition_json: dict[str, Any] = Field(default_factory=dict)
    severity: Literal["BLOCK", "APPROVAL_REQUIRED", "WARNING", "ADVISORY"] = "BLOCK"
    exception_permitted: bool = False
    exception_approver_capability: str | None = None
    evidence_required: list[Any] = Field(default_factory=list)
    effective_from: date | None = None
    effective_to: date | None = None

    @model_validator(mode="after")
    def validate_source_and_dates(self):
        if not self.source_revision_id:
            raise ValueError("A controlled source revision is required for a material Training rule.")
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        if self.exception_permitted and not self.exception_approver_capability:
            raise ValueError("An exception approver capability is required when exceptions are permitted.")
        return self


class GovernanceRuleRead(ORMModel):
    id: str
    amo_id: str
    rule_code: str
    authority_id: str | None = None
    source_type: str
    source_document_id: str | None = None
    source_revision_id: str | None = None
    source_title: str | None = None
    source_section: str | None = None
    source_paragraph: str | None = None
    applicability: dict[str, Any]
    value_json: dict[str, Any]
    condition_json: dict[str, Any]
    severity: str
    exception_permitted: bool
    exception_approver_capability: str | None = None
    evidence_required: list[Any]
    effective_from: date | None = None
    effective_to: date | None = None
    status: str


class RuleSetRead(BaseModel):
    rules: list[GovernanceRuleRead]
    conflicts: list[dict[str, Any]]
    status: Literal["CLEAR", "CONFLICT"]


class GovernanceConflictResolution(BaseModel):
    resolved_rule_id: str
    resolution: str = Field(min_length=4)


class ApprovalCreate(BaseModel):
    authority_id: str
    approval_number: str = Field(min_length=1, max_length=128)
    approval_type: str = Field(min_length=1, max_length=64)
    title: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    limitations: str | None = None
    supporting_dms_document_id: str | None = None
    supporting_dms_revision_id: str | None = None
    authority_correspondence_id: str | None = None
    recognition_json: list[Any] = Field(default_factory=list)


class ApprovalRead(ORMModel):
    id: str
    amo_id: str
    authority_id: str
    approval_number: str
    approval_type: str
    title: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    status: str
    limitations: str | None = None
    supporting_dms_document_id: str | None = None
    supporting_dms_revision_id: str | None = None
    recognition_json: list[Any]
    verified_by_user_id: str | None = None
    verified_at: datetime | None = None


class ApprovalTransition(BaseModel):
    status: Literal["ACTIVE", "SUSPENDED", "EXPIRED", "REVOKED"]
    verification_note: str | None = None


class ApprovalScopeCreate(BaseModel):
    scope_type: str
    course_id: str | None = None
    facility_id: str | None = None
    provider_id: str | None = None
    aircraft: str | None = None
    engine: str | None = None
    component_system: str | None = None
    training_level: str | None = None
    theory_privilege: bool = False
    practical_privilege: bool = False
    limitations: str | None = None
    applicability: dict[str, Any] = Field(default_factory=dict)


class TechnicalAuthorisationCreate(BaseModel):
    user_id: str
    privilege_type: Literal["INSTRUCTOR", "EXAMINER", "ASSESSOR", "OJT"]
    authority_id: str | None = None
    approval_id: str | None = None
    aircraft: str | None = None
    engine: str | None = None
    system_scope: str | None = None
    course_ids: list[str] = Field(default_factory=list)
    theoretical_privilege: bool = False
    practical_privilege: bool = False
    ojt_privilege: bool = False
    limitations: str | None = None
    licence_dependency: dict[str, Any] = Field(default_factory=dict)
    training_dependencies: list[Any] = Field(default_factory=list)
    observation_requirements: dict[str, Any] = Field(default_factory=dict)
    recurrent_requirements: dict[str, Any] = Field(default_factory=dict)
    appointment_authority: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    evidence_json: list[Any] = Field(default_factory=list)


class TechnicalAuthorisationRead(ORMModel):
    id: str
    amo_id: str
    user_id: str
    privilege_type: str
    authority_id: str | None = None
    approval_id: str | None = None
    aircraft: str | None = None
    engine: str | None = None
    system_scope: str | None = None
    course_ids: list[str]
    theoretical_privilege: bool
    practical_privilege: bool
    ojt_privilege: bool
    limitations: str | None = None
    licence_dependency: dict[str, Any]
    training_dependencies: list[Any]
    observation_requirements: dict[str, Any]
    recurrent_requirements: dict[str, Any]
    appointment_authority: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    status: str
    evidence_json: list[Any]
    suspended_reason: str | None = None
    revoked_reason: str | None = None


class TechnicalAuthorisationTransition(BaseModel):
    status: Literal["ACTIVE", "SUSPENDED", "REVOKED", "EXPIRED"]
    reason: str | None = None


class TechnicalReadinessRead(BaseModel):
    eligible: bool
    authorisation_id: str | None = None
    reasons: list[str]


class CourseRevisionCreate(BaseModel):
    course_id: str
    revision_no: int = Field(ge=1)
    title: str = Field(min_length=1)
    authority_id: str | None = None
    course_approval_id: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    theory_hours: Decimal = Field(default=Decimal("0"), ge=0)
    practical_hours: Decimal = Field(default=Decimal("0"), ge=0)
    total_hours: Decimal = Field(default=Decimal("0"), ge=0)
    delivery_methods: list[str] = Field(default_factory=list)
    completion_rules: dict[str, Any] = Field(default_factory=dict)
    assessment_blueprint: dict[str, Any] = Field(default_factory=dict)
    instructor_requirements: dict[str, Any] = Field(default_factory=dict)
    facility_requirements: dict[str, Any] = Field(default_factory=dict)
    certificate_rules: dict[str, Any] = Field(default_factory=dict)
    source_document_id: str | None = None
    source_revision_id: str | None = None
    source_section: str | None = None


class CourseRevisionRead(ORMModel):
    id: str
    amo_id: str
    course_id: str
    revision_no: int
    title: str
    status: str
    authority_id: str | None = None
    course_approval_id: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    theory_hours: Decimal
    practical_hours: Decimal
    total_hours: Decimal
    delivery_methods: list[str]
    completion_rules: dict[str, Any]
    assessment_blueprint: dict[str, Any]
    instructor_requirements: dict[str, Any]
    facility_requirements: dict[str, Any]
    certificate_rules: dict[str, Any]
    source_document_id: str | None = None
    source_revision_id: str | None = None
    source_section: str | None = None


class CourseModuleCreate(BaseModel):
    sequence_no: int = Field(ge=1)
    code: str | None = None
    subject: str = Field(min_length=1)
    theory_hours: Decimal = Field(default=Decimal("0"), ge=0)
    practical_hours: Decimal = Field(default=Decimal("0"), ge=0)
    delivery_method: str | None = None
    required_materials: list[Any] = Field(default_factory=list)
    manual_references: list[Any] = Field(default_factory=list)
    assessment_requirements: dict[str, Any] = Field(default_factory=dict)
    instructor_requirements: dict[str, Any] = Field(default_factory=dict)
    required: bool = True


class LearningObjectiveCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    statement: str = Field(min_length=3)
    knowledge_level: str | None = None
    competency_reference: str | None = None
    assessment_required: bool = False


class PracticalTaskCreate(BaseModel):
    module_id: str | None = None
    code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1)
    competency_reference: str | None = None
    evidence_requirements: list[Any] = Field(default_factory=list)
    assessor_requirements: dict[str, Any] = Field(default_factory=dict)
    required: bool = True


class PrerequisiteCreate(BaseModel):
    group_key: str = "ROOT"
    group_operator: Literal["AND", "OR"] = "AND"
    requirement_type: Literal["COURSE", "LICENCE", "EXPERIENCE", "AUTHORISATION", "ROLE", "DEPARTMENT", "COMPETENCE", "EXTERNAL_QUALIFICATION"]
    requirement_json: dict[str, Any]
    required: bool = True


class CourseReferenceCreate(BaseModel):
    module_id: str | None = None
    source_document_id: str
    source_revision_id: str
    section: str | None = None
    paragraph: str | None = None
    reference_type: str = "REQUIRED"


class MaterialRevisionCreate(BaseModel):
    material_code: str
    title: str
    revision_no: int = Field(ge=1)
    material_type: str
    dms_document_id: str | None = None
    dms_revision_id: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    required: bool = True


class FacilityCreate(BaseModel):
    code: str
    name: str
    facility_type: Literal["PERMANENT", "CLASSROOM", "WORKSHOP", "HANGAR", "SIMULATOR", "REMOTE", "CUSTOMER"] = "PERMANENT"
    address: str | None = None
    approval_id: str | None = None
    authority_id: str | None = None
    approved_scope: dict[str, Any] = Field(default_factory=dict)
    classroom_capacity: int | None = Field(default=None, ge=0)
    practical_capacity: int | None = Field(default=None, ge=0)
    equipment: list[Any] = Field(default_factory=list)
    training_aids: list[Any] = Field(default_factory=list)
    technical_library_access: bool = False
    product_access: list[Any] = Field(default_factory=list)
    contracts: list[Any] = Field(default_factory=list)
    restrictions: str | None = None
    evidence_json: list[Any] = Field(default_factory=list)
    expiry_date: date | None = None


class FacilityRead(ORMModel):
    id: str
    amo_id: str
    code: str
    name: str
    facility_type: str
    approval_id: str | None = None
    authority_id: str | None = None
    approved_scope: dict[str, Any]
    classroom_capacity: int | None = None
    practical_capacity: int | None = None
    expiry_date: date | None = None
    status: str
    restrictions: str | None = None


class ProviderCreate(BaseModel):
    legal_name: str
    authority_id: str | None = None
    approval_id: str | None = None
    approval_number: str | None = None
    approved_scope: dict[str, Any] = Field(default_factory=dict)
    recognition_status: str = "UNVERIFIED"
    locations: list[Any] = Field(default_factory=list)
    audits: list[Any] = Field(default_factory=list)
    contracts: list[Any] = Field(default_factory=list)
    findings: list[Any] = Field(default_factory=list)
    evidence_json: list[Any] = Field(default_factory=list)
    approved_course_ids: list[str] = Field(default_factory=list)
    approved_instructor_ids: list[str] = Field(default_factory=list)
    effective_date: date | None = None
    expiry_date: date | None = None


class ProviderRead(ORMModel):
    id: str
    amo_id: str
    legal_name: str
    authority_id: str | None = None
    approval_id: str | None = None
    approval_number: str | None = None
    approved_scope: dict[str, Any]
    recognition_status: str
    approved_course_ids: list[str]
    effective_date: date | None = None
    expiry_date: date | None = None
    status: str


class ExternalCreditCheck(BaseModel):
    provider_id: str
    training_date: date
    course_id: str | None = None
    authority_id: str | None = None


class SessionGovernanceUpsert(BaseModel):
    course_revision_id: str
    facility_id: str | None = None
    provider_id: str | None = None
    instructor_authorisation_ids: list[str] = Field(default_factory=list)
    examiner_authorisation_ids: list[str] = Field(default_factory=list)
    assessor_authorisation_ids: list[str] = Field(default_factory=list)


class SessionReadinessRead(BaseModel):
    status: Literal["READY", "WARNING", "BLOCKED"]
    checks: list[dict[str, Any]]
    blockers: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    event_id: str
    evaluated_at: datetime


class ModuleAttendanceUpsert(BaseModel):
    user_id: str
    status: Literal["ATTENDED", "PARTIAL", "MAKE_UP_REQUIRED", "SUPPLEMENTAL_IN_PROGRESS", "COMPLETE", "INCOMPLETE"]
    attended_minutes: int | None = Field(default=None, ge=0)
    evidence_json: list[Any] = Field(default_factory=list)
    correction_reason: str | None = None


class PracticalAssessmentCreate(BaseModel):
    user_id: str
    assessor_authorisation_id: str
    result: Literal["PASS", "FAIL", "NEEDS_MORE_PRACTICE"]
    evidence_json: list[Any] = Field(default_factory=list)
    comments: str | None = None


class QuestionItemCreate(BaseModel):
    question_code: str
    course_revision_id: str
    module_id: str | None = None
    learning_objective_id: str | None = None


class QuestionRevisionCreate(BaseModel):
    revision_no: int = Field(ge=1)
    prompt: str = Field(min_length=3)
    options_json: list[Any] = Field(default_factory=list)
    answer_key_json: dict[str, Any]
    explanation: str | None = None
    ata_chapter: str | None = None
    knowledge_level: str | None = None
    difficulty: Decimal | None = None
    marks: Decimal = Field(default=Decimal("1"), ge=0)
    source_document_id: str | None = None
    source_revision_id: str
    source_section: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None


class QuestionLearnerRead(BaseModel):
    question_revision_id: str
    prompt: str
    options: list[Any]
    marks: Decimal


class ExamBlueprintCreate(BaseModel):
    course_revision_id: str
    revision_no: int = Field(ge=1)
    title: str
    selection_rules: dict[str, Any] = Field(default_factory=dict)
    result_rules: dict[str, Any] = Field(default_factory=dict)
    security_rules: dict[str, Any] = Field(default_factory=dict)
    effective_from: date | None = None
    effective_to: date | None = None


class ImpactPreviewCreate(BaseModel):
    source_document_id: str
    previous_revision_id: str | None = None
    new_revision_id: str


class ImpactAssessmentRead(ORMModel):
    id: str
    amo_id: str
    source_document_id: str
    previous_revision_id: str | None = None
    new_revision_id: str
    status: str
    summary_json: dict[str, Any]
    blockers_json: list[Any]
    created_at: datetime


class LearnerCompletionInput(BaseModel):
    required_module_ids: list[str] = Field(default_factory=list)
    completed_module_ids: list[str] = Field(default_factory=list)
    required_practical_task_ids: list[str] = Field(default_factory=list)
    passed_practical_task_ids: list[str] = Field(default_factory=list)
    required_assessments: list[str] = Field(default_factory=list)
    passed_assessments: list[str] = Field(default_factory=list)
    additional_blockers: list[str] = Field(default_factory=list)


class BatchCertificateCandidate(BaseModel):
    user_id: str
    status: str
    certificate_eligible: bool
    blockers: list[str] = Field(default_factory=list)


class AuthoritySubmissionCreate(BaseModel):
    authority_id: str
    submission_type: str
    subject_type: str
    subject_id: str
    application_reference: str | None = None
    evidence_json: list[Any] = Field(default_factory=list)
    externally_received: bool = False


class AuthoritySubmissionDecision(BaseModel):
    status: Literal["RETURNED", "APPROVED", "ACCEPTED", "REJECTED"]
    authority_comments: str | None = None
    approval_number: str | None = None
    effective_date: date | None = None
    independently_verified: bool = False


class QualityLinkCreate(BaseModel):
    training_entity_type: str
    training_entity_id: str
    qms_entity_type: Literal["FINDING", "CAR", "AUDIT", "ACTION"]
    qms_entity_id: str
    relationship_type: str = "RELATED"
