from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ExamBlueprintCreate(BaseModel):
    course_revision_id: str
    revision_no: int = Field(ge=1)
    title: str = Field(min_length=1)
    selection_rules: dict[str, Any]
    result_rules: dict[str, Any]
    security_rules: dict[str, Any] = Field(default_factory=dict)
    effective_from: date | None = None
    effective_to: date | None = None

    @model_validator(mode="after")
    def validate_controlled_rules(self):
        if int(self.selection_rules.get("question_count") or 0) <= 0:
            raise ValueError("selection_rules.question_count must be a positive controlled value")
        if not self.result_rules:
            raise ValueError("result_rules must be provided by the controlled assessment policy")
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        return self


class ExamBlueprintRead(ORMModel):
    id: str
    amo_id: str
    course_revision_id: str
    revision_no: int
    title: str
    selection_rules: dict[str, Any]
    result_rules: dict[str, Any]
    security_rules: dict[str, Any]
    status: str
    effective_from: date | None = None
    effective_to: date | None = None


class ExamFormCreate(BaseModel):
    blueprint_id: str
    form_code: str = Field(min_length=1, max_length=64)
    revision_no: int = Field(default=1, ge=1)
    question_revision_ids: list[str] = Field(default_factory=list)


class ExamGenerationCreate(BaseModel):
    event_id: str
    blueprint_id: str
    generation_code: str = Field(min_length=1, max_length=64)
    form_id: str | None = None
    security_metadata: dict[str, Any] = Field(default_factory=dict)


class ExamGenerationRead(BaseModel):
    id: str
    event_id: str
    blueprint_id: str
    generation_code: str
    question_revision_ids: list[str]
    status: str
    generated_at: datetime
    excluded: list[dict[str, Any]] = Field(default_factory=list)


class ExamAttemptCreate(BaseModel):
    generation_id: str
    event_id: str
    attempt_no: int = Field(default=1, ge=1)
    proctor_user_id: str | None = None


class ExamAttemptLearnerRead(BaseModel):
    attempt_id: str
    event_id: str
    status: str
    questions: list[dict[str, Any]]


class ExamAttemptSubmit(BaseModel):
    responses: dict[str, Any]


class ExamSecurityEventCreate(BaseModel):
    event_type: str = Field(min_length=2)
    severity: Literal["INFO", "WARNING", "BLOCK", "CRITICAL"] = "INFO"
    details_json: dict[str, Any] = Field(default_factory=dict)


class ExamAnalysisRun(BaseModel):
    question_revision_id: str
    analysis_window: str = Field(min_length=1, max_length=64)
    policy: dict[str, Any]
    complaint_count: int = Field(default=0, ge=0)
    source_superseded: bool = False


class ExamAnalysisRead(ORMModel):
    id: str
    question_revision_id: str
    analysis_window: str
    sample_size: int
    response_distribution: dict[str, Any]
    percent_correct: Decimal | None = None
    difficulty_index: Decimal | None = None
    discrimination_index: Decimal | None = None
    distractor_performance: dict[str, Any]
    abnormal_patterns: list[Any]
    complaint_count: int
    source_superseded: bool
    review_status: str
    review_reasons: list[Any]
    computed_at: datetime


class ModerationCreate(BaseModel):
    question_revision_id: str | None = None
    generation_id: str | None = None
    reason: str = Field(min_length=4)
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    recommendation: str | None = None

    @model_validator(mode="after")
    def subject_required(self):
        if not self.question_revision_id and not self.generation_id:
            raise ValueError("Moderation must identify a question revision or exam generation")
        return self


class ModerationDecision(BaseModel):
    decision: Literal["NO_CHANGE", "SUSPEND_PENDING_REVIEW", "REVISE_REQUIRED", "RETIRE"]
    decision_reason: str = Field(min_length=4)


class AppealCreate(BaseModel):
    attempt_id: str
    grounds: str = Field(min_length=4)
    evidence_json: list[Any] = Field(default_factory=list)


class AppealDecision(BaseModel):
    decision: Literal["UPHOLD", "DISMISS", "REASSESS", "REMARK"]
    decision_reason: str = Field(min_length=4)
