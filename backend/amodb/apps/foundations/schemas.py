# backend/amodb/apps/foundations/schemas.py
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .models import AvailabilityStatus, BaseAssignmentKind, BaseStationType

LocationSource = Literal["MANUAL", "DEVICE_SINGLE", "DEVICE_CONSENSUS", "AERODROME_DATASET"]


class BaseStationAliasRead(BaseModel):
    id: str
    amo_id: str
    base_station_id: str
    alias: str
    source_module: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class BaseStationBase(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=160)
    icao_code: Optional[str] = Field(default=None, max_length=8)
    iata_code: Optional[str] = Field(default=None, max_length=8)
    base_type: BaseStationType = BaseStationType.MAIN_BASE
    time_zone: Optional[str] = Field(default=None, max_length=80)
    description: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    coordinate_accuracy_m: Optional[float] = Field(default=None, ge=0, le=5000)
    location_source: Optional[LocationSource] = None
    airport_reference_ident: Optional[str] = Field(default=None, max_length=16)
    geofence_radius_m: int = Field(default=250, ge=50, le=5000)
    checkin_prompt_enabled: bool = False
    checkout_reminder_enabled: bool = False
    suspicious_location_review_enabled: bool = False
    is_active: bool = True

    @model_validator(mode="after")
    def validate_location_policy(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be provided together.")
        has_location = self.latitude is not None and self.longitude is not None
        if not has_location and (
            self.checkin_prompt_enabled
            or self.checkout_reminder_enabled
            or self.suspicious_location_review_enabled
        ):
            raise ValueError("Location prompts require approved base coordinates.")
        if has_location and not self.location_source:
            self.location_source = "MANUAL"
        return self


class BaseStationCreate(BaseStationBase):
    aliases: List[str] = Field(default_factory=list)


class BaseStationUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=32)
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    icao_code: Optional[str] = Field(default=None, max_length=8)
    iata_code: Optional[str] = Field(default=None, max_length=8)
    base_type: Optional[BaseStationType] = None
    time_zone: Optional[str] = Field(default=None, max_length=80)
    description: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    coordinate_accuracy_m: Optional[float] = Field(default=None, ge=0, le=5000)
    location_source: Optional[LocationSource] = None
    airport_reference_ident: Optional[str] = Field(default=None, max_length=16)
    geofence_radius_m: Optional[int] = Field(default=None, ge=50, le=5000)
    checkin_prompt_enabled: Optional[bool] = None
    checkout_reminder_enabled: Optional[bool] = None
    suspicious_location_review_enabled: Optional[bool] = None
    is_active: Optional[bool] = None
    aliases: Optional[List[str]] = None


class BaseStationRead(BaseStationBase):
    id: str
    amo_id: str
    location_verified_at: Optional[datetime] = None
    location_verified_by_user_id: Optional[str] = None
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    aliases: List[BaseStationAliasRead] = Field(default_factory=list)

    class Config:
        from_attributes = True


class BaseLocationObservationCreate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(gt=0, le=2500)
    captured_at: datetime


class BaseLocationConsensusRead(BaseModel):
    base_station_id: str
    sample_count: int
    distinct_contributor_count: int
    candidate_latitude: Optional[float] = None
    candidate_longitude: Optional[float] = None
    median_accuracy_m: Optional[float] = None
    max_spread_m: Optional[float] = None
    ready_for_approval: bool
    reason: str
    expires_at: Optional[datetime] = None


class BaseLocationConsensusApproval(BaseModel):
    expected_sample_count: int = Field(ge=2)


class LocationEvaluationRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(gt=0, le=5000)
    base_station_id: Optional[str] = None


class LocationEvaluationRead(BaseModel):
    base_station_id: Optional[str] = None
    base_code: Optional[str] = None
    base_name: Optional[str] = None
    distance_m: Optional[float] = None
    geofence_radius_m: Optional[int] = None
    inside_geofence: bool = False
    location_confidence: Literal["HIGH", "MEDIUM", "LOW", "UNAVAILABLE"]
    checkin_prompt_enabled: bool = False
    checkout_reminder_enabled: bool = False
    review_signal: bool = False
    review_reason: Optional[str] = None
    note: str


class AirportCatalogItem(BaseModel):
    ident: str
    name: str
    airport_type: Optional[str] = None
    municipality: Optional[str] = None
    iso_country: Optional[str] = None
    iso_region: Optional[str] = None
    icao_code: Optional[str] = None
    iata_code: Optional[str] = None
    local_code: Optional[str] = None
    latitude: float
    longitude: float
    distance_km: Optional[float] = None
    source: Literal["OURAIRPORTS"] = "OURAIRPORTS"


class AirportCatalogSearchRead(BaseModel):
    items: List[AirportCatalogItem]
    provider: str = "OurAirports public-domain dataset"
    advisory: str = "Suggestions must be confirmed against current authority or AIP data before operational use."
    cached_at: Optional[datetime] = None


class UserBaseAssignmentCreate(BaseModel):
    user_id: str
    base_station_id: str
    assignment_kind: BaseAssignmentKind = BaseAssignmentKind.HOME_BASE
    effective_from: date = Field(default_factory=date.today)
    effective_to: Optional[date] = None
    is_primary: bool = False
    note: Optional[str] = None


class UserBaseAssignmentRead(UserBaseAssignmentCreate):
    id: str
    amo_id: str
    created_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    base_station: Optional[BaseStationRead] = None

    class Config:
        from_attributes = True


class AvailabilityCreate(BaseModel):
    user_id: str
    status: AvailabilityStatus
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    note: Optional[str] = None


class AvailabilityRead(BaseModel):
    id: str
    amo_id: str
    user_id: str
    status: AvailabilityStatus
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
    canonical_key: Literal["users.id"] = "users.id"
    active_users: int
    active_personnel_profiles: int
    linked_active_profiles: int
    active_users_without_profile: int
    active_profiles_without_user: int
    issues: List[PersonnelIdentityIssue] = Field(default_factory=list)


class FoundationContracts(BaseModel):
    canonical_personnel_key: Literal["users.id"] = "users.id"
    ownership: Dict[str, str]
    service_contracts: Dict[str, object]
    canonical_frontend_routes: Dict[str, str]
