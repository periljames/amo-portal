from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class TechnicalDashboardTile(BaseModel):
    key: str
    label: str
    count: int


class TechnicalDashboardRead(BaseModel):
    tiles: list[TechnicalDashboardTile]


class AircraftUtilisationCreate(BaseModel):
    tail_id: str
    entry_date: date
    hours: float = Field(ge=0)
    cycles: float = Field(ge=0)
    source: str = "Manual"
    correction_reason: Optional[str] = None


class AircraftUtilisationRead(AircraftUtilisationCreate):
    id: int
    conflict_flag: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ExceptionQueueItemRead(BaseModel):
    id: int
    ex_type: str
    object_type: str
    object_id: str
    summary: str
    status: str
    resolution_notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ExceptionResolveRequest(BaseModel):
    resolution_notes: str


class DeferralRead(BaseModel):
    id: int
    tail_id: str
    defect_ref: str
    deferral_type: str
    deferred_at: datetime
    expiry_at: datetime
    status: str
    linked_wo_id: Optional[int] = None
    linked_crs_id: Optional[int] = None

    class Config:
        from_attributes = True


class MaintenanceRecordRead(BaseModel):
    id: int
    tail_id: str
    performed_at: datetime
    description: str
    reference_data_text: str
    certifying_user_id: Optional[str] = None
    outcome: str
    linked_wo_id: Optional[int] = None
    linked_wp_id: Optional[str] = None
    evidence_asset_ids: list[str] = []

    class Config:
        from_attributes = True


class MaintenanceRecordCreate(BaseModel):
    tail_id: str
    performed_at: datetime
    description: str
    reference_data_text: str
    certifying_user_id: Optional[str] = None
    outcome: str
    linked_wo_id: Optional[int] = None
    linked_wp_id: Optional[str] = None
    evidence_asset_ids: list[str] = []


class AirworthinessItemRead(BaseModel):
    id: int
    item_type: str
    reference: str
    applicability_json: dict[str, Any]
    status: str
    next_due_date: Optional[date] = None
    next_due_hours: Optional[float] = None
    next_due_cycles: Optional[float] = None

    class Config:
        from_attributes = True


class AirworthinessItemCreate(BaseModel):
    item_type: str
    reference: str
    applicability_json: dict[str, Any] = {}
    status: str = "Open"
    next_due_date: Optional[date] = None
    next_due_hours: Optional[float] = None
    next_due_cycles: Optional[float] = None


class TechnicalRecordSettingsRead(BaseModel):
    utilisation_manual_only: bool
    ad_sb_use_hours_cycles: bool
    record_retention_years: int
    allow_manual_maintenance_records: bool

    class Config:
        from_attributes = True


class TechnicalRecordSettingsUpdate(TechnicalRecordSettingsRead):
    pass
