from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from .models import BaseAssignmentKind, BaseStationType


class BaseStationBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=255)
    icao_code: Optional[str] = Field(None, max_length=8)
    iata_code: Optional[str] = Field(None, max_length=8)
    base_type: BaseStationType = BaseStationType.OTHER
    time_zone: Optional[str] = Field(None, max_length=64)
    description: Optional[str] = None
    is_active: bool = True


class BaseStationCreate(BaseStationBase):
    aliases: List[str] = Field(default_factory=list)


class BaseStationUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=32)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    icao_code: Optional[str] = Field(None, max_length=8)
    iata_code: Optional[str] = Field(None, max_length=8)
    base_type: Optional[BaseStationType] = None
    time_zone: Optional[str] = Field(None, max_length=64)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    aliases: Optional[List[str]] = None


class BaseStationAliasRead(BaseModel):
    id: str
    amo_id: str
    base_station_id: str
    alias: str
    source_module: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class BaseStationRead(BaseStationBase):
    id: str
    amo_id: str
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    aliases: List[BaseStationAliasRead] = Field(default_factory=list)

    class Config:
        from_attributes = True


class UserBaseAssignmentCreate(BaseModel):
    user_id: str
    base_station_id: str
    assignment_kind: BaseAssignmentKind = BaseAssignmentKind.HOME_BASE
    effective_from: date = Field(default_factory=date.today)
    effective_to: Optional[date] = None
    is_primary: bool = True
    note: Optional[str] = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self


class UserBaseAssignmentUpdate(BaseModel):
    base_station_id: Optional[str] = None
    assignment_kind: Optional[BaseAssignmentKind] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    is_primary: Optional[bool] = None
    note: Optional[str] = None


class UserBaseAssignmentRead(BaseModel):
    id: str
    amo_id: str
    user_id: str
    base_station_id: str
    assignment_kind: BaseAssignmentKind
    effective_from: date
    effective_to: Optional[date] = None
    is_primary: bool
    note: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    base_station: Optional[BaseStationRead] = None

    class Config:
        from_attributes = True


class AvailabilityStatus(str):
    pass


class AvailabilityCreate(BaseModel):
    user_id: str
    status: str = Field(..., pattern="^(ON_DUTY|AWAY|ON_LEAVE)$")
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    note: Optional[str] = None


class AvailabilityRead(BaseModel):
    id: str
    amo_id: str
    user_id: str
    status: str
    effective_from: datetime
    effective_to: Optional[datetime] = None
    note: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True


class PersonnelIdentityIssue(BaseModel):
    issue_type: str
    user_id: Optional[str] = None
    personnel_profile_id: Optional[str] = None
    staff_code: Optional[str] = None
    person_id: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    detail: str


class PersonnelIdentityHealth(BaseModel):
    amo_id: str
    canonical_key: str = "users.id"
    active_users: int
    active_personnel_profiles: int
    linked_active_profiles: int
    active_users_without_profile: int
    active_profiles_without_user: int
    issues: List[PersonnelIdentityIssue]


class FoundationContracts(BaseModel):
    canonical_personnel_key: str
    ownership: Dict[str, str]
    service_contracts: Dict[str, Any]
    canonical_frontend_routes: Dict[str, str]
