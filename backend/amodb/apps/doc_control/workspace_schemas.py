from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


DocumentClass = Literal["INTERNAL", "EXTERNAL", "RECORD"]
WorkflowReadiness = Literal["NOT_REQUIRED", "PENDING", "BLOCKED", "READY", "WAIVED"]


class ProfileUpsert(BaseModel):
    document_class: DocumentClass = "INTERNAL"
    owner_department: str = "DOCUMENT_CONTROL"
    owner_user_id: str | None = None
    language: str = "English"
    criticality: Literal["STANDARD", "IMPORTANT", "CRITICAL"] = "STANDARD"
    regulated_flag: bool = False
    restricted_flag: bool = False
    requires_authority_approval: bool = False
    acknowledgement_required: bool = True
    review_interval_months: int = Field(default=24, ge=1, le=120)
    next_review_due: date | None = None
    access_scope: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    expected_version: int | None = Field(default=None, ge=1)


class ChangeRequestCreate(BaseModel):
    manual_id: str
    revision_id: str | None = None
    source_module: str = "DOCUMENT_CONTROL"
    source_entity_type: str | None = None
    source_entity_id: str | None = None
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=3)
    priority: Literal["LOW", "NORMAL", "HIGH", "CRITICAL"] = "NORMAL"
    owner_user_id: str | None = None
    due_at: datetime | None = None
    impact: dict[str, Any] = Field(default_factory=dict)
    training_impact_required: bool = False
    qms_blocking: bool = False


class ChangeRequestUpdate(BaseModel):
    status: Literal["OPEN", "ASSESSING", "ACCEPTED", "REJECTED", "IMPLEMENTING", "CLOSED"] | None = None
    owner_user_id: str | None = None
    due_at: datetime | None = None
    priority: Literal["LOW", "NORMAL", "HIGH", "CRITICAL"] | None = None
    impact: dict[str, Any] | None = None
    training_impact_required: bool | None = None
    qms_blocking: bool | None = None
    resolution: str | None = None


class WorkflowCreate(BaseModel):
    manual_id: str
    revision_id: str
    requires_authority: bool | None = None
    training_impact_required: bool = False
    training_readiness_status: WorkflowReadiness = "NOT_REQUIRED"
    qms_readiness_status: WorkflowReadiness = "NOT_REQUIRED"
    distribution_readiness_status: WorkflowReadiness = "NOT_REQUIRED"
    effective_at: datetime | None = None


class WorkflowTransitionRequest(BaseModel):
    action: Literal[
        "SUBMIT_TECHNICAL_REVIEW",
        "APPROVE_TECHNICAL",
        "REQUEST_CORRECTIONS",
        "RESUBMIT_TECHNICAL_REVIEW",
        "START_QUALITY_REVIEW",
        "APPROVE_QUALITY",
        "SUBMIT_ACCOUNTABLE_MANAGER",
        "APPROVE_ACCOUNTABLE_MANAGER",
        "MARK_AUTHORITY_SUBMITTED",
        "MARK_AUTHORITY_APPROVED",
        "SCHEDULE_EFFECTIVITY",
        "PUBLISH",
        "ARCHIVE",
    ]
    comments: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    expected_version: int = Field(ge=1)
    effective_at: datetime | None = None
    training_readiness_status: WorkflowReadiness | None = None
    qms_readiness_status: WorkflowReadiness | None = None
    distribution_readiness_status: WorkflowReadiness | None = None


class AuthoritySubmissionCreate(BaseModel):
    manual_id: str
    revision_id: str
    workflow_id: str | None = None
    authority_name: str = Field(min_length=2, max_length=255)
    submission_reference: str = Field(min_length=2, max_length=255)
    response_due_at: datetime | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class AuthoritySubmissionUpdate(BaseModel):
    status: Literal["DRAFT", "SUBMITTED", "IN_REVIEW", "QUERY_RECEIVED", "APPROVED", "REJECTED", "WITHDRAWN"]
    response_summary: str | None = None
    response_due_at: datetime | None = None
    evidence: list[dict[str, Any]] | None = None


class TemporaryRevisionCreate(BaseModel):
    manual_id: str
    base_revision_id: str
    revision_id: str | None = None
    tr_number: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=3, max_length=255)
    reason: str = Field(min_length=3)
    affected_sections: list[dict[str, Any]] = Field(default_factory=list)
    filing_instructions: str | None = None
    effective_date: date
    expiry_date: date

    @model_validator(mode="after")
    def validate_window(self):
        if self.expiry_date < self.effective_date:
            raise ValueError("expiry_date must not be before effective_date")
        return self


class TemporaryRevisionTransition(BaseModel):
    status: Literal["DRAFT", "IN_REVIEW", "APPROVED", "IN_FORCE", "EXPIRED", "WITHDRAWN", "INCORPORATED"]
    approval_status: Literal["PENDING", "APPROVED", "REJECTED"] | None = None
    distribution_campaign_id: str | None = None
    incorporated_revision_id: str | None = None


class DistributionCampaignCreate(BaseModel):
    manual_id: str
    revision_id: str
    temporary_revision_id: str | None = None
    title: str = Field(min_length=3, max_length=255)
    audience: dict[str, Any] = Field(default_factory=dict)
    acknowledgement_required: bool = True
    due_at: datetime | None = None
    recipient_user_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DistributionIssueRequest(BaseModel):
    recipient_user_ids: list[str] = Field(default_factory=list)
    due_at: datetime | None = None


class DistributionAcknowledgeRequest(BaseModel):
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class ReviewPlanCreate(BaseModel):
    manual_id: str
    revision_id: str | None = None
    owner_user_id: str | None = None
    due_at: datetime


class ReviewCompleteRequest(BaseModel):
    outcome: Literal["CONTINUE", "CHANGE_REQUIRED", "WITHDRAW", "SUPERSEDE"]
    findings: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)


class ControlledCopyCreate(BaseModel):
    manual_id: str
    revision_id: str
    copy_number: str = Field(min_length=1, max_length=64)
    format: Literal["HARDCOPY", "OFFLINE_MEDIA"] = "HARDCOPY"
    holder_user_id: str = Field(min_length=1)
    holder_name: str | None = None
    location_text: str = Field(min_length=2, max_length=255)
    due_back_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ControlledCopyEventCreate(BaseModel):
    event_type: Literal["TRANSFER", "RECALL", "RETURN", "WITHDRAW", "DESTROY", "LOCATION_CHANGE"]
    to_holder_user_id: str | None = None
    to_location: str | None = None
    reason: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class ExternalSourceCreate(BaseModel):
    manual_id: str
    provider: str = Field(min_length=2, max_length=255)
    authority: str | None = None
    subscription_reference: str | None = None
    access_url: str | None = None
    update_method: Literal["MANUAL_CHECK", "EMAIL", "PORTAL", "API", "SUBSCRIPTION"] = "MANUAL_CHECK"
    next_check_due_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExternalRevisionReceiptCreate(BaseModel):
    revision_label: str = Field(min_length=1, max_length=128)
    publication_date: date | None = None
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    currency_status: Literal["UNVERIFIED", "CURRENT", "SUPERSEDED", "UNKNOWN"] = "UNVERIFIED"
    applicability_status: Literal["PENDING", "APPLICABLE", "NOT_APPLICABLE", "PARTIAL"] = "PENDING"
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    notes: str | None = None


class ApplicabilityRuleCreate(BaseModel):
    manual_id: str
    revision_id: str | None = None
    rule_type: Literal["INCLUDE", "EXCLUDE", "WARNING"] = "INCLUDE"
    target_type: Literal[
        "AIRCRAFT_TYPE",
        "AIRCRAFT",
        "SERIAL_RANGE",
        "ENGINE_TYPE",
        "COMPONENT_TYPE",
        "BASE",
        "DEPARTMENT",
        "ROLE",
        "AUTHORIZATION_GROUP",
        "WORK_ORDER",
        "WORK_PACKAGE",
    ]
    target_id: str | None = None
    target_value: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    source: str = "MANUAL"
    criteria: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_effectivity(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not be before effective_from")
        if not self.target_id and not self.target_value and not self.criteria:
            raise ValueError("an applicability target or criteria is required")
        return self


class IntegrationLinkCreate(BaseModel):
    manual_id: str
    revision_id: str | None = None
    change_request_id: str | None = None
    workflow_id: str | None = None
    source_module: Literal["QMS", "TRAINING", "WORKFORCE", "PLANNING", "PRODUCTION", "MAINTENANCE", "FLEET", "STORES", "TECHNICAL_RECORDS"]
    entity_type: str = Field(min_length=1, max_length=64)
    entity_id: str = Field(min_length=1, max_length=128)
    relation_type: Literal[
        "CHANGE_DRIVER",
        "BLOCKER",
        "TRAINING_IMPACT",
        "APPLICABILITY",
        "USED_BY",
        "EVIDENCE",
        "SOURCE",
        "COMPLIANCE",
    ]
    blocking: bool = False
    status_snapshot: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
