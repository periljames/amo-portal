from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class RolloutGroupCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    description: Optional[str] = Field(default=None, max_length=4000)
    selection_json: dict[str, Any] = Field(default_factory=dict)


class RolloutWaveCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    sequence_no: int = Field(ge=1)
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    aircraft_serial_numbers: list[str] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.planned_start and self.planned_end and self.planned_end < self.planned_start:
            raise ValueError("planned_end must not be before planned_start")
        return self


class RolloutChecklistUpdate(BaseModel):
    status: Literal["PENDING", "COMPLETE", "BLOCKED", "NOT_APPLICABLE"]
    notes: Optional[str] = Field(default=None, max_length=4000)
    evidence_json: list[str] = Field(default_factory=list, max_length=100)


class RolloutAircraftTransition(BaseModel):
    status: Literal["PLANNED", "DUAL_RUN", "CUTOVER", "VERIFIED", "COMPLETE", "HOLD"]
    notes: Optional[str] = Field(default=None, max_length=4000)
    migration_batch_id: Optional[str] = None


class RolloutWaveTransition(BaseModel):
    status: Literal["PLANNED", "READY", "IN_PROGRESS", "HOLD", "COMPLETE", "CANCELLED"]
    decision_notes: str = Field(min_length=3, max_length=4000)


class RolloutChecklistRead(BaseModel):
    id: str
    wave_id: str
    aircraft_serial_number: Optional[str] = None
    check_key: str
    category: str
    label: str
    status: str
    owner_user_id: Optional[str] = None
    evidence_json: list[str]
    notes: Optional[str] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RolloutWaveAircraftRead(BaseModel):
    id: str
    wave_id: str
    aircraft_serial_number: str
    registration: str
    status: str
    migration_batch_id: Optional[str] = None
    dual_run_started_at: Optional[datetime] = None
    cutover_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    hold_reason: Optional[str] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class RolloutWaveRead(BaseModel):
    id: str
    group_id: str
    name: str
    sequence_no: int
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    status: str
    readiness_json: dict[str, Any]
    decision_notes: Optional[str] = None
    approved_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    aircraft: list[RolloutWaveAircraftRead] = Field(default_factory=list)
    checklist_items: list[RolloutChecklistRead] = Field(default_factory=list)

    class Config:
        from_attributes = True


class RolloutGroupRead(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    status: str
    selection_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    waves: list[RolloutWaveRead] = Field(default_factory=list)

    class Config:
        from_attributes = True


class SpreadsheetCreate(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    owner: Optional[str] = Field(default=None, max_length=255)
    location: Optional[str] = Field(default=None, max_length=512)
    purpose: str = Field(min_length=3, max_length=4000)
    data_domain: Literal[
        "AIRCRAFT_MASTER",
        "UTILISATION",
        "MAINTENANCE_PROGRAM",
        "FORECAST",
        "WORK_PACKAGE",
        "DEFERRAL",
        "COMPONENT",
        "TECHNICAL_RECORDS",
        "OTHER",
    ]
    replacement_route: Optional[str] = Field(default=None, max_length=255)
    retirement_criteria_json: list[str] = Field(default_factory=list, max_length=100)


class SpreadsheetTransition(BaseModel):
    status: Literal["LIVE", "DUAL_RUN", "READ_ONLY", "RETIRED", "ARCHIVED"]
    notes: str = Field(min_length=3, max_length=4000)
    evidence_json: list[str] = Field(default_factory=list, max_length=100)


class SpreadsheetEventRead(BaseModel):
    id: str
    spreadsheet_id: str
    event_type: str
    from_status: Optional[str] = None
    to_status: str
    notes: Optional[str] = None
    evidence_json: list[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SpreadsheetRead(BaseModel):
    id: str
    name: str
    owner: Optional[str] = None
    location: Optional[str] = None
    purpose: str
    data_domain: str
    status: str
    replacement_route: Optional[str] = None
    retirement_criteria_json: list[str]
    retirement_evidence_json: list[str]
    retired_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    events: list[SpreadsheetEventRead] = Field(default_factory=list)

    class Config:
        from_attributes = True


class RolloutDashboardRead(BaseModel):
    groups: int
    waves: int
    active_waves: int
    aircraft_planned: int
    aircraft_dual_run: int
    aircraft_cutover: int
    aircraft_verified: int
    aircraft_complete: int
    aircraft_hold: int
    spreadsheet_live: int
    spreadsheet_dual_run: int
    spreadsheet_read_only: int
    spreadsheet_retired: int
    spreadsheet_archived: int
