from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DatasetCode = Literal[
    "AIRCRAFT_MASTER",
    "CONFIGURATION",
    "COMPONENTS",
    "LLP_STATUS",
    "UTILISATION",
    "AMP_STATUS",
    "AD_STATUS",
    "SB_STATUS",
    "MODIFICATIONS",
    "REPAIRS",
    "DEFERRALS",
    "MAINTENANCE_HISTORY",
    "DOCUMENT_INDEX",
]


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FamilyCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=160)
    manufacturer: str = Field(min_length=2, max_length=160)
    description: str | None = None


class FamilyRead(OrmModel):
    id: str
    code: str
    name: str
    manufacturer: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class TypeCreate(BaseModel):
    family_id: str
    type_code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=160)
    type_certificate_number: str | None = None
    authority: str | None = None
    description: str | None = None


class TypeRead(OrmModel):
    id: str
    family_id: str
    type_code: str
    name: str
    type_certificate_number: str | None
    authority: str | None
    description: str | None
    status: str


class VariantCreate(BaseModel):
    aircraft_type_id: str
    variant_code: str = Field(min_length=2, max_length=64)
    model_code: str = Field(min_length=2, max_length=64)
    marketing_name: str | None = None
    description: str | None = None
    serial_effectivity_json: dict[str, Any] = Field(default_factory=dict)
    engine_options_json: list[dict[str, Any]] = Field(default_factory=list)
    propeller_options_json: list[dict[str, Any]] = Field(default_factory=list)
    apu_options_json: list[dict[str, Any]] = Field(default_factory=list)


class VariantRead(OrmModel):
    id: str
    aircraft_type_id: str
    variant_code: str
    model_code: str
    marketing_name: str | None
    description: str | None
    serial_effectivity_json: dict[str, Any]
    engine_options_json: list[dict[str, Any]]
    propeller_options_json: list[dict[str, Any]]
    apu_options_json: list[dict[str, Any]]
    status: str


class TemplateCreate(BaseModel):
    variant_id: str
    code: str = Field(min_length=3, max_length=96)
    title: str = Field(min_length=3, max_length=255)
    visibility: Literal["GLOBAL", "TENANT"] = "GLOBAL"
    description: str | None = None


class TemplateRead(OrmModel):
    id: str
    variant_id: str
    code: str
    title: str
    visibility: str
    owner_amo_id: str | None
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class TemplateRevisionCreate(BaseModel):
    revision_code: str = Field(min_length=1, max_length=48)
    effective_date: date | None = None
    source_reference: str | None = None
    source_hash: str | None = Field(default=None, max_length=64)
    release_notes: str | None = None


class TemplateRevisionRead(OrmModel):
    id: str
    template_id: str
    revision_code: str
    status: str
    effective_date: date | None
    source_reference: str | None
    source_hash: str | None
    content_hash: str | None
    release_notes: str | None
    approved_by_user_id: str | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SourceDocumentCreate(BaseModel):
    document_type: str = Field(min_length=2, max_length=32)
    reference: str = Field(min_length=2, max_length=160)
    revision: str | None = None
    issue_date: date | None = None
    authority: str | None = None
    source_uri: str | None = None
    content_hash: str | None = Field(default=None, max_length=64)
    notes: str | None = None


class SourceDocumentRead(OrmModel):
    id: str
    revision_id: str
    document_type: str
    reference: str
    revision: str | None
    issue_date: date | None
    authority: str | None
    source_uri: str | None
    content_hash: str | None
    notes: str | None


class ConfigurationNodeCreate(BaseModel):
    node_key: str = Field(min_length=1, max_length=128)
    parent_node_key: str | None = None
    node_type: str = Field(min_length=2, max_length=32)
    position_code: str | None = None
    title: str = Field(min_length=2, max_length=255)
    ata_chapter: str | None = None
    minimum_quantity: int = Field(default=0, ge=0)
    maximum_quantity: int | None = Field(default=None, ge=0)
    allowable_parts_json: list[dict[str, Any]] = Field(default_factory=list)
    counter_rules_json: list[dict[str, Any]] = Field(default_factory=list)
    effectivity_json: dict[str, Any] = Field(default_factory=dict)
    sequence_no: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def quantities_are_ordered(self):
        if self.maximum_quantity is not None and self.maximum_quantity < self.minimum_quantity:
            raise ValueError("maximum_quantity must be greater than or equal to minimum_quantity")
        return self


class ConfigurationNodeRead(OrmModel):
    id: str
    revision_id: str
    node_key: str
    parent_node_key: str | None
    node_type: str
    position_code: str | None
    title: str
    ata_chapter: str | None
    minimum_quantity: int
    maximum_quantity: int | None
    allowable_parts_json: list[dict[str, Any]]
    counter_rules_json: list[dict[str, Any]]
    effectivity_json: dict[str, Any]
    sequence_no: int


class RequirementCreate(BaseModel):
    requirement_key: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=2, max_length=32)
    ata_chapter: str | None = None
    task_code: str = Field(min_length=1, max_length=96)
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    governing_logic: Literal["WHICHEVER_FIRST", "WHICHEVER_LAST", "ALL_LIMITS", "CUSTOM"] = "WHICHEVER_FIRST"
    interval_json: dict[str, Any] = Field(default_factory=dict)
    threshold_json: dict[str, Any] = Field(default_factory=dict)
    effectivity_json: dict[str, Any] = Field(default_factory=dict)
    source_reference: str | None = None
    source_document_id: str | None = None
    mandatory: bool = True
    sequence_no: int = Field(default=1, ge=1)


class RequirementRead(OrmModel):
    id: str
    revision_id: str
    requirement_key: str
    category: str
    ata_chapter: str | None
    task_code: str
    title: str
    description: str | None
    governing_logic: str
    interval_json: dict[str, Any]
    threshold_json: dict[str, Any]
    effectivity_json: dict[str, Any]
    source_reference: str | None
    source_document_id: str | None
    mandatory: bool
    sequence_no: int


class PublishRevisionRequest(BaseModel):
    approval_note: str = Field(min_length=3)


class MappingProfileCreate(BaseModel):
    scope: Literal["GLOBAL", "TENANT"] = "TENANT"
    name: str = Field(min_length=3, max_length=160)
    source_system: str = Field(min_length=2, max_length=64)
    source_version: str | None = None
    dataset: DatasetCode
    fingerprint: str = Field(min_length=16, max_length=64)
    header_signature_json: list[str] = Field(default_factory=list)
    mapping_json: dict[str, str] = Field(default_factory=dict)
    transformations_json: dict[str, Any] = Field(default_factory=dict)
    defaults_json: dict[str, Any] = Field(default_factory=dict)
    validation_json: dict[str, Any] = Field(default_factory=dict)


class MappingProfileRead(OrmModel):
    id: str
    amo_id: str | None
    scope: str
    name: str
    version: int
    source_system: str
    source_version: str | None
    dataset: str
    fingerprint: str
    header_signature_json: list[str]
    mapping_json: dict[str, Any]
    transformations_json: dict[str, Any]
    defaults_json: dict[str, Any]
    validation_json: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime


class TenantProgramCreate(BaseModel):
    variant_id: str
    code: str = Field(min_length=2, max_length=96)
    title: str = Field(min_length=3, max_length=255)
    authority: str | None = None
    approval_reference: str | None = None


class TenantProgramRead(OrmModel):
    id: str
    amo_id: str
    variant_id: str
    code: str
    title: str
    authority: str | None
    approval_reference: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class TenantProgramRevisionCreate(BaseModel):
    base_template_revision_id: str
    revision_code: str = Field(min_length=1, max_length=48)
    effective_date: date | None = None
    approval_reference: str | None = None
    approval_date: date | None = None
    notes: str | None = None


class TenantProgramRevisionRead(OrmModel):
    id: str
    program_id: str
    base_template_revision_id: str
    revision_code: str
    status: str
    effective_date: date | None
    approval_reference: str | None
    approval_date: date | None
    notes: str | None
    approved_by_user_id: str | None
    approved_at: datetime | None


class ProgramOverrideCreate(BaseModel):
    requirement_key: str = Field(min_length=1, max_length=128)
    action: Literal["ADD", "MODIFY", "EXCLUDE"]
    patch_json: dict[str, Any] = Field(default_factory=dict)
    effectivity_json: dict[str, Any] = Field(default_factory=dict)
    justification: str = Field(min_length=5)
    authority_reference: str | None = None


class ProgramOverrideRead(OrmModel):
    id: str
    program_revision_id: str
    requirement_key: str
    action: str
    patch_json: dict[str, Any]
    effectivity_json: dict[str, Any]
    justification: str
    authority_reference: str | None


class ApproveProgramRevisionRequest(BaseModel):
    approval_note: str = Field(min_length=3)


class InductionCreate(BaseModel):
    induction_ref: str = Field(min_length=3, max_length=96)
    serial_number: str = Field(min_length=1, max_length=50)
    registration: str = Field(min_length=2, max_length=20)
    variant_id: str
    template_revision_id: str
    program_revision_id: str
    source_system: str | None = None
    source_reference: str | None = None

    @field_validator("serial_number", "registration")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        return value.strip().upper()


class InductionRead(OrmModel):
    id: str
    amo_id: str
    induction_ref: str
    serial_number: str
    registration: str
    variant_id: str
    template_revision_id: str
    program_revision_id: str
    status: str
    source_system: str | None
    source_reference: str | None
    source_hash: str | None
    current_step: str
    counts_json: dict[str, Any]
    validation_json: dict[str, Any]
    activation_manifest_json: dict[str, Any]
    approved_by_user_id: str | None
    approved_at: datetime | None
    activated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StagedRow(BaseModel):
    dataset: DatasetCode
    source_name: str
    source_sheet: str | None = None
    fingerprint: str = Field(min_length=16, max_length=64)
    headers: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(min_length=1)
    mapping_profile_id: str | None = None


class RowDecisionRequest(BaseModel):
    decision: Literal["ACCEPT", "OVERRIDE", "REJECT"]
    final_json: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class DatasetRead(OrmModel):
    id: str
    induction_id: str
    dataset: str
    source_name: str
    source_sheet: str | None
    fingerprint: str
    mapping_profile_id: str | None
    headers_json: list[str]
    row_count: int
    status: str
    created_at: datetime


class RowRead(OrmModel):
    id: str
    dataset_id: str
    row_number: int
    source_json: dict[str, Any]
    normalized_json: dict[str, Any]
    status: str
    errors_json: list[str]
    warnings_json: list[str]
    decision: str | None
    final_json: dict[str, Any]
    decided_by_user_id: str | None
    decided_at: datetime | None


class EffectivityEvaluationRequest(BaseModel):
    expression: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class EffectivityEvaluationRead(BaseModel):
    applicable: bool
    explanations: list[str]


class ApplicabilitySnapshotRead(OrmModel):
    id: str
    amo_id: str
    induction_id: str | None
    aircraft_serial_number: str
    template_revision_id: str
    program_revision_id: str
    configuration_hash: str
    snapshot_hash: str
    context_json: dict[str, Any]
    applicable_requirements_json: list[dict[str, Any]]
    excluded_requirements_json: list[dict[str, Any]]
    created_at: datetime


class CounterBaselineCreate(BaseModel):
    counter_code: str = Field(min_length=2, max_length=48)
    unit: str = Field(min_length=1, max_length=16)
    value: Decimal = Field(ge=0)
    effective_date: date | None = None
    source_reference: str | None = None


class ActivationRequest(BaseModel):
    approval_note: str = Field(min_length=5)
    counters: list[CounterBaselineCreate] = Field(default_factory=list)


class BindingRead(OrmModel):
    id: str
    amo_id: str
    aircraft_serial_number: str
    variant_id: str
    template_revision_id: str
    program_revision_id: str
    applicability_snapshot_id: str
    status: str
    activated_by_user_id: str | None
    activated_at: datetime
    superseded_at: datetime | None


class CatalogueRead(BaseModel):
    families: list[FamilyRead]
    types: list[TypeRead]
    variants: list[VariantRead]
    templates: list[TemplateRead]
    revisions: list[TemplateRevisionRead]


class InductionWorkspaceRead(BaseModel):
    induction: InductionRead
    datasets: list[DatasetRead]
    rows_by_dataset: dict[str, list[RowRead]]
    applicability_snapshot: ApplicabilitySnapshotRead | None = None
    binding: BindingRead | None = None
