"""Contracts for guided reporting-line setup and display-title governance."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ReportingReferenceUser(BaseModel):
    id: str
    full_name: str
    staff_code: str
    email: str
    department_id: Optional[str] = None
    current_title: Optional[str] = None


class ReportingUnitRead(BaseModel):
    id: str
    code: str
    name: str
    unit_type: str
    parent_id: Optional[str] = None
    department_id: Optional[str] = None
    editable: bool = False


class ReportingOccupantRead(BaseModel):
    assignment_id: str
    user_id: str
    user_name: str
    staff_code: str
    canonical_title: str
    display_title: str
    title_preference_status: Optional[str] = None
    reporting_manager_user_id: Optional[str] = None
    reporting_manager_name: Optional[str] = None
    assignment_type: str
    is_primary: bool
    effective_from: date
    effective_to: Optional[date] = None


class ReportingManagerCandidateRead(BaseModel):
    user_id: str
    user_name: str
    position_id: str
    position_title: str
    relationship: str


class ReportingPositionRead(BaseModel):
    id: str
    unit_id: str
    unit_name: str
    code: str
    canonical_title: str
    reports_to_position_id: Optional[str] = None
    reports_to_title: Optional[str] = None
    depth: int = 0
    path_titles: list[str] = Field(default_factory=list)
    is_supervisory: bool = False
    is_regulatory_post: bool = False
    authority_acceptance_required: bool = False
    headcount_limit: int = 1
    occupied_count: int = 0
    vacancy_count: int = 0
    editable: bool = False
    manager_candidates: list[ReportingManagerCandidateRead] = Field(default_factory=list)
    occupants: list[ReportingOccupantRead] = Field(default_factory=list)


class TitlePreferenceRead(BaseModel):
    id: str
    user_id: str
    user_name: str
    assignment_id: str
    canonical_title: str
    requested_title: str
    reason: Optional[str] = None
    source: str
    status: str
    requested_by_user_id: Optional[str] = None
    decided_by_user_id: Optional[str] = None
    requested_at: datetime
    decided_at: Optional[datetime] = None


class ReportingWorkspaceRead(BaseModel):
    actor_mode: str
    can_manage_all: bool = False
    manageable_unit_ids: list[str] = Field(default_factory=list)
    units: list[ReportingUnitRead] = Field(default_factory=list)
    positions: list[ReportingPositionRead] = Field(default_factory=list)
    users: list[ReportingReferenceUser] = Field(default_factory=list)
    pending_title_preferences: list[TitlePreferenceRead] = Field(default_factory=list)
    authorization_boundary: str


class ReportingChainRoleCreate(BaseModel):
    title: str = Field(min_length=2, max_length=128)
    code: Optional[str] = Field(default=None, max_length=64)
    headcount_limit: int = Field(default=1, ge=1, le=9999)
    is_supervisory: bool = False


class ReportingChainCreate(BaseModel):
    unit_id: str
    parent_position_id: Optional[str] = None
    roles: list[ReportingChainRoleCreate] = Field(min_length=1, max_length=20)


class ReportingChainResult(BaseModel):
    created_positions: list[ReportingPositionRead] = Field(default_factory=list)


class ReportingPositionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=128)
    reports_to_position_id: Optional[str] = None
    headcount_limit: Optional[int] = Field(default=None, ge=1, le=9999)
    is_supervisory: Optional[bool] = None
    sync_reporting_managers: bool = True


class GuidedAssignmentCreate(BaseModel):
    user_id: str
    position_id: str
    reporting_manager_user_id: Optional[str] = None
    assignment_type: str = Field(default="SUBSTANTIVE", max_length=32)
    is_primary: bool = True
    effective_from: date
    effective_to: Optional[date] = None
    fte_percent: Decimal = Field(default=Decimal("100"), gt=0, le=100)
    matrix_reporting: bool = False
    matrix_reason: Optional[str] = None
    display_title: Optional[str] = Field(default=None, min_length=2, max_length=128)
    appointment_reference: Optional[str] = Field(default=None, max_length=128)
    authority_acceptance_reference: Optional[str] = Field(default=None, max_length=128)
    authority_accepted_on: Optional[date] = None
    delegation_limitations: Optional[str] = None


class TitlePreferenceCreate(BaseModel):
    requested_title: str = Field(min_length=2, max_length=128)
    reason: Optional[str] = Field(default=None, max_length=1000)


class TitlePreferenceDecision(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    note: Optional[str] = Field(default=None, max_length=1000)


class MyTitleProfileRead(BaseModel):
    assignment_id: Optional[str] = None
    position_id: Optional[str] = None
    canonical_title: Optional[str] = None
    display_title: Optional[str] = None
    unit_name: Optional[str] = None
    reporting_manager_name: Optional[str] = None
    reporting_chain: list[str] = Field(default_factory=list)
    current_preference: Optional[TitlePreferenceRead] = None
    authorization_boundary: str
