"""API contracts for corporate structure and personnel governance."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


class OrganizationOverviewRead(BaseModel):
    units: int = 0
    active_units: int = 0
    positions: int = 0
    approved_headcount: int = 0
    active_assignments: int = 0
    vacant_positions: int = 0
    workforce_engagements: int = 0
    contingent_workers: int = 0
    missing_primary_assignment: int = 0
    missing_engagement: int = 0
    compliance_profiles_due: int = 0
    expiring_credentials_90_days: int = 0


class OrganizationUnitBase(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=255)
    unit_type: str = Field(default="DEPARTMENT", max_length=32)
    parent_id: Optional[str] = None
    department_id: Optional[str] = None
    base_station_id: Optional[str] = None
    purpose: Optional[str] = None
    cost_center: Optional[str] = Field(default=None, max_length=64)
    accountable_manager_user_id: Optional[str] = None
    manager_user_id: Optional[str] = None
    deputy_manager_user_id: Optional[str] = None
    quality_owner_user_id: Optional[str] = None
    headcount_limit: Optional[int] = Field(default=None, ge=0)
    sort_order: int = 100
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    is_active: bool = True


class OrganizationUnitCreate(OrganizationUnitBase):
    amo_id: Optional[str] = None


class OrganizationUnitUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    unit_type: Optional[str] = Field(default=None, max_length=32)
    parent_id: Optional[str] = None
    department_id: Optional[str] = None
    base_station_id: Optional[str] = None
    purpose: Optional[str] = None
    cost_center: Optional[str] = Field(default=None, max_length=64)
    accountable_manager_user_id: Optional[str] = None
    manager_user_id: Optional[str] = None
    deputy_manager_user_id: Optional[str] = None
    quality_owner_user_id: Optional[str] = None
    headcount_limit: Optional[int] = Field(default=None, ge=0)
    sort_order: Optional[int] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    is_active: Optional[bool] = None


class OrganizationUnitRead(OrganizationUnitBase):
    id: str
    amo_id: str
    parent_name: Optional[str] = None
    manager_name: Optional[str] = None
    deputy_manager_name: Optional[str] = None
    accountable_manager_name: Optional[str] = None
    position_count: int = 0
    assignment_count: int = 0
    created_at: datetime
    updated_at: datetime


class PositionBase(BaseModel):
    unit_id: str
    code: str = Field(min_length=2, max_length=64)
    title: str = Field(min_length=2, max_length=255)
    reports_to_position_id: Optional[str] = None
    job_family: Optional[str] = Field(default=None, max_length=128)
    grade: Optional[str] = Field(default=None, max_length=64)
    employment_category: str = Field(default="EMPLOYEE", max_length=32)
    headcount_limit: int = Field(default=1, ge=1, le=9999)
    is_supervisory: bool = False
    is_regulatory_post: bool = False
    regulatory_post_type: Optional[str] = Field(default=None, max_length=64)
    authority_acceptance_required: bool = False
    minimum_competence_summary: Optional[str] = None
    responsibilities: Optional[str] = None
    approval_scope: Optional[str] = None
    default_account_role: Optional[str] = Field(default=None, max_length=64)
    succession_criticality: str = Field(default="STANDARD", max_length=32)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    is_active: bool = True


class PositionCreate(PositionBase):
    amo_id: Optional[str] = None


class PositionRead(PositionBase):
    id: str
    amo_id: str
    unit_name: str
    reports_to_position_title: Optional[str] = None
    occupied_count: int = 0
    vacancy_count: int = 0
    created_at: datetime
    updated_at: datetime


class PositionAssignmentCreate(BaseModel):
    amo_id: Optional[str] = None
    user_id: str
    position_id: str
    reporting_manager_user_id: Optional[str] = None
    assignment_type: str = Field(default="SUBSTANTIVE", max_length=32)
    status: str = Field(default="ACTIVE", max_length=32)
    is_primary: bool = True
    matrix_reporting: bool = False
    matrix_reason: Optional[str] = None
    fte_percent: Decimal = Field(default=Decimal("100"), gt=0, le=100)
    effective_from: date
    effective_to: Optional[date] = None
    appointment_reference: Optional[str] = Field(default=None, max_length=128)
    authority_acceptance_reference: Optional[str] = Field(default=None, max_length=128)
    authority_accepted_on: Optional[date] = None
    delegation_limitations: Optional[str] = None
    notes: Optional[str] = None


class PositionAssignmentRead(PositionAssignmentCreate):
    id: str
    amo_id: str
    user_name: str
    staff_code: str
    position_title: str
    unit_name: str
    reporting_manager_name: Optional[str] = None
    approved_by_user_id: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class WorkforceEngagementCreate(BaseModel):
    amo_id: Optional[str] = None
    user_id: str
    engagement_type: str = Field(default="EMPLOYEE", max_length=32)
    status: str = Field(default="ACTIVE", max_length=32)
    contract_reference: Optional[str] = Field(default=None, max_length=128)
    start_date: date
    end_date: Optional[date] = None
    probation_months: Optional[int] = Field(default=None, ge=0, le=60)
    sponsor_user_id: Optional[str] = None
    external_organisation: Optional[str] = Field(default=None, max_length=255)
    institution_or_vendor: Optional[str] = Field(default=None, max_length=255)
    programme_name: Optional[str] = Field(default=None, max_length=255)
    learning_objectives: Optional[str] = None
    work_permit_status: Optional[str] = Field(default=None, max_length=32)
    work_permit_reference: Optional[str] = Field(default=None, max_length=128)
    work_permit_expires_on: Optional[date] = None
    background_check_status: Optional[str] = Field(default=None, max_length=32)
    access_expiry_on: Optional[date] = None
    offboarding_required: bool = True
    notes: Optional[str] = None


class WorkforceEngagementRead(WorkforceEngagementCreate):
    id: str
    amo_id: str
    user_name: str
    staff_code: str
    sponsor_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class GroupPolicyCreate(BaseModel):
    amo_id: Optional[str] = None
    group_id: str
    unit_id: Optional[str] = None
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=255)
    description: Optional[str] = None
    inheritance_mode: str = Field(default="UNIT_AND_DESCENDANTS", max_length=32)
    membership_mode: str = Field(default="MANUAL", max_length=32)
    default_account_role: Optional[str] = Field(default=None, max_length=64)
    permission_template: dict[str, Any] = Field(default_factory=dict)
    segregation_tags: list[str] = Field(default_factory=list)
    requires_manager_approval: bool = True
    requires_quality_approval: bool = False
    maximum_assignment_days: Optional[int] = Field(default=None, ge=1, le=3650)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    is_active: bool = True


class GroupPolicyRead(GroupPolicyCreate):
    id: str
    amo_id: str
    group_name: str
    unit_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ComplianceProfileUpdate(BaseModel):
    legal_name: Optional[str] = Field(default=None, max_length=255)
    preferred_name: Optional[str] = Field(default=None, max_length=128)
    nationality: Optional[str] = Field(default=None, max_length=64)
    residence_country: Optional[str] = Field(default=None, max_length=64)
    identity_verified: bool = False
    identity_reference: Optional[str] = Field(default=None, max_length=128)
    emergency_contact_name: Optional[str] = Field(default=None, max_length=255)
    emergency_contact_relationship: Optional[str] = Field(default=None, max_length=64)
    emergency_contact_phone: Optional[str] = Field(default=None, max_length=64)
    data_classification: str = Field(default="CONFIDENTIAL", max_length=32)
    retention_class: str = Field(default="PERSONNEL_ACTIVE_PLUS_RETENTION", max_length=64)
    confidentiality_ack_at: Optional[datetime] = None
    code_of_conduct_ack_at: Optional[datetime] = None
    conflict_declaration_at: Optional[datetime] = None
    competence_status: str = Field(default="NOT_ASSESSED", max_length=32)
    training_status: str = Field(default="NOT_ASSESSED", max_length=32)
    authorisation_status: str = Field(default="NOT_APPLICABLE", max_length=32)
    medical_fitness_status: str = Field(default="NOT_APPLICABLE", max_length=32)
    last_competence_assessment_on: Optional[date] = None
    next_review_on: Optional[date] = None
    compliance_owner_user_id: Optional[str] = None
    restrictions: Optional[str] = None
    notes: Optional[str] = None


class ComplianceProfileRead(ComplianceProfileUpdate):
    id: str
    amo_id: str
    user_id: str
    identity_verified_at: Optional[datetime] = None
    identity_verified_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PersonnelCredentialCreate(BaseModel):
    amo_id: Optional[str] = None
    user_id: str
    credential_type: str = Field(max_length=32)
    authority: Optional[str] = Field(default=None, max_length=128)
    reference: str = Field(min_length=1, max_length=128)
    title: Optional[str] = Field(default=None, max_length=255)
    scope: dict[str, Any] = Field(default_factory=dict)
    issued_on: Optional[date] = None
    expires_on: Optional[date] = None
    status: str = Field(default="VALID", max_length=32)
    evidence_document_id: Optional[str] = None
    restrictions: Optional[str] = None


class PersonnelCredentialRead(PersonnelCredentialCreate):
    id: str
    amo_id: str
    verified_by_user_id: Optional[str] = None
    verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class UserGovernanceRead(BaseModel):
    user: dict[str, Any]
    primary_assignment: Optional[PositionAssignmentRead] = None
    assignments: list[PositionAssignmentRead] = Field(default_factory=list)
    active_engagement: Optional[WorkforceEngagementRead] = None
    engagements: list[WorkforceEngagementRead] = Field(default_factory=list)
    compliance_profile: Optional[ComplianceProfileRead] = None
    credentials: list[PersonnelCredentialRead] = Field(default_factory=list)
    readiness_score: int = 0
    readiness_gaps: list[str] = Field(default_factory=list)


class ManagerTeamMemberRead(BaseModel):
    user_id: str
    full_name: str
    staff_code: str
    email: str
    position_title: str
    unit_name: str
    engagement_type: Optional[str] = None
    engagement_end_date: Optional[date] = None
    competence_status: str = "NOT_ASSESSED"
    training_status: str = "NOT_ASSESSED"
    expiring_credentials: int = 0
    readiness_score: int = 0
    readiness_gaps: list[str] = Field(default_factory=list)


class MyProfileRead(BaseModel):
    user: dict[str, Any]
    assignment: Optional[PositionAssignmentRead] = None
    engagement: Optional[WorkforceEngagementRead] = None
    compliance_profile: Optional[ComplianceProfileRead] = None
    credentials: list[PersonnelCredentialRead] = Field(default_factory=list)
