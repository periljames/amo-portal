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


class PlanningDashboardRead(BaseModel):
    summary: dict[str, int]
    priority_items: list[dict[str, Any]]


class ProductionDashboardRead(BaseModel):
    summary: dict[str, int]
    bottlenecks: list[dict[str, Any]]


class WatchlistCreate(BaseModel):
    name: str
    status: str = "Active"
    criteria_json: dict[str, Any] = {}
    next_run_at: Optional[datetime] = None


class WatchlistRead(WatchlistCreate):
    id: int
    run_count: int
    last_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WatchlistRunResult(BaseModel):
    watchlist_id: int
    publications_ingested: int
    matches_created: int


class PublicationReviewRead(BaseModel):
    match_id: int
    watchlist_id: int
    publication_id: int
    authority: str
    source: str
    document_type: str
    doc_number: str
    title: str
    effectivity_summary: Optional[str] = None
    classification: str
    review_status: str
    matched_fleet: list[str] = []
    ageing_days: int
    assigned_reviewer_user_id: Optional[str] = None
    published_date: Optional[date] = None


class PublicationReviewDecisionRequest(BaseModel):
    review_status: str
    classification: str
    assigned_reviewer_user_id: Optional[str] = None


class ComplianceActionCreate(BaseModel):
    publication_match_id: int
    decision: str
    status: str = "Under Review"
    due_date: Optional[date] = None
    due_hours: Optional[float] = None
    due_cycles: Optional[float] = None
    recurring_interval_days: Optional[int] = None
    owner_user_id: Optional[str] = None
    package_ref: Optional[str] = None
    work_order_ref: Optional[str] = None
    evidence_json: list[str] = []
    decision_notes: Optional[str] = None


class ComplianceActionRead(ComplianceActionCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ComplianceActionStatusUpdate(BaseModel):
    status: str
    event_notes: Optional[str] = None
