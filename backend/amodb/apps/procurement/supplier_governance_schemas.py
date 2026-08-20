from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SupplierReevaluationRules(BaseModel):
    expiry_lead_days: int = Field(..., ge=0, le=3650)
    lookback_days: int = Field(..., ge=1, le=3650)
    rejected_inspection_threshold: int = Field(..., ge=1, le=10000)
    active_hold_threshold: int = Field(..., ge=1, le=10000)
    action_due_days: int = Field(..., ge=1, le=3650)


class SupplierGovernancePolicyUpdate(BaseModel):
    risk_review_days: dict[str, int]
    re_evaluation_rules: SupplierReevaluationRules
    require_independent_review: bool = True
    conditional_approval_allowed: bool = True
    effective_from: date | None = None

    @field_validator("risk_review_days")
    @classmethod
    def validate_risk_intervals(cls, value: dict[str, int]) -> dict[str, int]:
        normalized = {str(key).strip().upper(): int(days) for key, days in value.items()}
        required = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        if set(normalized) != required:
            raise ValueError("risk_review_days must define LOW, MEDIUM, HIGH and CRITICAL exactly once")
        if any(days < 1 or days > 3650 for days in normalized.values()):
            raise ValueError("risk review intervals must be between 1 and 3650 days")
        return normalized


class SupplierGovernancePolicyRead(OrmModel):
    id: str
    amo_id: str
    revision_no: int
    risk_review_days: dict[str, int]
    re_evaluation_rules: dict[str, Any]
    require_independent_review: bool
    conditional_approval_allowed: bool
    effective_from: date | None = None
    updated_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class SupplierCriterionCreate(BaseModel):
    criterion_key: str = Field(..., min_length=1, max_length=64)
    sequence_no: int = Field(..., ge=1, le=1000)
    label: str = Field(..., min_length=2, max_length=255)
    guidance: str | None = Field(None, max_length=4000)
    response_type: Literal["STRUCTURED", "BOOLEAN", "NUMBER", "TEXT", "RATING", "CHOICE"] = "STRUCTURED"
    weight: Decimal = Field(Decimal("1"), ge=0, le=10000)
    mandatory: bool = True
    evidence_required: bool = False
    failure_is_blocking: bool = False
    scoring_rule: dict[str, Any] = Field(default_factory=dict)

    @field_validator("criterion_key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip().upper().replace(" ", "_")


class SupplierEvaluationTemplateCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = Field(None, max_length=4000)
    pass_threshold: Decimal | None = Field(None, ge=0, le=100)
    manual_references: list[str] = Field(default_factory=list, max_length=100)
    criteria: list[SupplierCriterionCreate] = Field(..., min_length=1, max_length=250)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper().replace(" ", "_")

    @model_validator(mode="after")
    def unique_criteria(self):
        keys = [item.criterion_key for item in self.criteria]
        sequences = [item.sequence_no for item in self.criteria]
        if len(keys) != len(set(keys)):
            raise ValueError("criterion_key values must be unique within a template")
        if len(sequences) != len(set(sequences)):
            raise ValueError("sequence_no values must be unique within a template")
        if sum(item.weight for item in self.criteria) <= 0:
            raise ValueError("at least one criterion must have a positive weight")
        return self


class SupplierEvaluationTemplateActivate(BaseModel):
    rationale: str = Field(..., min_length=8, max_length=4000)


class SupplierCriterionRead(SupplierCriterionCreate, OrmModel):
    id: str
    amo_id: str
    template_id: str
    created_at: datetime


class SupplierEvaluationTemplateRead(OrmModel):
    id: str
    amo_id: str
    code: str
    name: str
    description: str | None = None
    revision_no: int
    status: str
    pass_threshold: Decimal | None = None
    manual_references: list[str] = Field(default_factory=list)
    created_by_user_id: str | None = None
    activated_by_user_id: str | None = None
    activated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    criteria: list[SupplierCriterionRead] = Field(default_factory=list)


class SupplierIntendedScope(BaseModel):
    site_code: str = Field("PRIMARY", min_length=1, max_length=64)
    category: str = Field(..., min_length=2, max_length=64)
    product_family: str = Field("ALL", min_length=1, max_length=128)
    manufacturer: str | None = Field(None, max_length=128)
    authority: str = Field("TENANT_QMS", min_length=1, max_length=64)
    restrictions: str | None = Field(None, max_length=4000)
    incoming_inspection_level: str = Field("STANDARD", min_length=1, max_length=32)


class SupplierEvaluationCreate(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=36)
    intended_scope: list[SupplierIntendedScope] = Field(..., min_length=1, max_length=100)
    supersedes_evaluation_id: str | None = Field(None, max_length=36)


class SupplierEvaluationResponseInput(BaseModel):
    criterion_id: str = Field(..., min_length=1, max_length=36)
    answer: Any
    score_percent: Decimal | None = Field(None, ge=0, le=100)
    evidence_references: list[str] = Field(default_factory=list, max_length=100)
    comment: str | None = Field(None, max_length=4000)


class SupplierEvaluationResponsesUpdate(BaseModel):
    expected_version: int = Field(..., ge=1)
    responses: list[SupplierEvaluationResponseInput] = Field(..., min_length=1, max_length=250)

    @model_validator(mode="after")
    def unique_criterion_responses(self):
        ids = [row.criterion_id for row in self.responses]
        if len(ids) != len(set(ids)):
            raise ValueError("each criterion may be submitted only once per update")
        return self


class SupplierEvaluationSubmit(BaseModel):
    expected_version: int = Field(..., ge=1)
    submission_note: str | None = Field(None, max_length=4000)


class SupplierEvaluationReview(BaseModel):
    expected_version: int = Field(..., ge=1)
    decision: Literal["APPROVE", "CONDITIONALLY_APPROVE", "REJECT", "RETURN"]
    rationale: str = Field(..., min_length=8, max_length=4000)
    conditions: list[str] = Field(default_factory=list, max_length=100)
    qms_finding_id: str | None = Field(None, max_length=36)
    qms_car_id: str | None = Field(None, max_length=36)

    @model_validator(mode="after")
    def conditional_requires_conditions(self):
        if self.decision == "CONDITIONALLY_APPROVE" and not [item for item in self.conditions if item.strip()]:
            raise ValueError("conditional approval requires at least one recorded condition")
        return self


class SupplierEvaluationResponseRead(OrmModel):
    id: str
    criterion_id: str
    answer: Any
    score_percent: Decimal | None = None
    evidence_references: list[str] = Field(default_factory=list)
    comment: str | None = None
    updated_by_user_id: str | None = None
    updated_at: datetime


class SupplierEvaluationRead(OrmModel):
    id: str
    amo_id: str
    supplier_id: int
    template_id: str
    template_revision_no: int
    status: str
    version: int
    intended_scope: list[dict[str, Any]]
    policy_snapshot: dict[str, Any]
    score: Decimal | None = None
    outcome: str | None = None
    valid_until: date | None = None
    qms_finding_id: str | None = None
    qms_car_id: str | None = None
    created_by_user_id: str | None = None
    submitted_by_user_id: str | None = None
    reviewed_by_user_id: str | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    review_comment: str | None = None
    supersedes_evaluation_id: str | None = None
    created_at: datetime
    updated_at: datetime
    responses: list[SupplierEvaluationResponseRead] = Field(default_factory=list)


class SupplierGovernanceDecisionRead(OrmModel):
    id: str
    supplier_id: int
    evaluation_id: str | None = None
    action: str
    rationale: str
    before_snapshot: dict[str, Any] | None = None
    after_snapshot: dict[str, Any] | None = None
    evidence_snapshot: dict[str, Any]
    actor_user_id: str | None = None
    created_at: datetime


class SupplierReevaluationActionRead(OrmModel):
    id: str
    supplier_id: int
    trigger_key: str
    trigger_type: str
    trigger_snapshot: dict[str, Any]
    source_reference: str | None = None
    status: str
    due_on: date | None = None
    assigned_to_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class SupplierGovernanceDetail(BaseModel):
    supplier_id: int
    policy_configured: bool
    current_evaluation: SupplierEvaluationRead | None = None
    evaluations: list[SupplierEvaluationRead] = Field(default_factory=list)
    decisions: list[SupplierGovernanceDecisionRead] = Field(default_factory=list)
    re_evaluation_actions: list[SupplierReevaluationActionRead] = Field(default_factory=list)


class SupplierReevaluationScanResult(BaseModel):
    suppliers_scanned: int
    actions_created: int
    actions_existing: int
    triggers: dict[str, int] = Field(default_factory=dict)
