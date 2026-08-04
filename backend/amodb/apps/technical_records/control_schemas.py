from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class CanonicalUtilisationCreate(BaseModel):
    tail_id: str
    entry_date: date
    techlog_no: str = Field(min_length=1, max_length=64)
    station: Optional[str] = Field(default=None, max_length=16)
    hours: float = Field(ge=0, description="Cumulative airframe hours after this entry")
    cycles: float = Field(ge=0, description="Cumulative airframe cycles after this entry")
    block_hours: Optional[float] = Field(default=None, ge=0)
    entry_cycles: Optional[float] = Field(default=None, ge=0)
    source: str = "Manual"
    remarks: Optional[str] = None
    note: Optional[str] = None


class CanonicalUtilisationRead(BaseModel):
    id: int
    tail_id: str
    entry_date: date
    techlog_no: str
    station: Optional[str] = None
    block_hours: float
    entry_cycles: float
    hours: float
    cycles: float
    source: str = "AircraftUsage"
    conflict_flag: bool = False
    correction_reason: Optional[str] = None
    verification_status: str
    created_at: datetime
    updated_at: datetime


class UsageCorrectionCreate(BaseModel):
    reason: str = Field(min_length=8, max_length=2000)
    expected_usage_updated_at: datetime
    entry_date: Optional[date] = None
    techlog_no: Optional[str] = Field(default=None, min_length=1, max_length=64)
    station: Optional[str] = Field(default=None, max_length=16)
    block_hours: Optional[float] = Field(default=None, ge=0)
    cycles: Optional[float] = Field(default=None, ge=0)
    remarks: Optional[str] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def require_change(self):
        fields = ("entry_date", "techlog_no", "station", "block_hours", "cycles", "remarks", "note")
        if not any(getattr(self, field) is not None for field in fields):
            raise ValueError("At least one corrected value is required.")
        return self


class UsageCorrectionRead(BaseModel):
    id: int
    usage_id: int
    aircraft_serial_number: str
    reason: str
    proposed_values_json: dict[str, Any]
    status: str
    expected_usage_updated_at: datetime
    requested_by_user_id: Optional[str] = None
    reviewed_by_user_id: Optional[str] = None
    review_notes: Optional[str] = None
    requested_at: datetime
    reviewed_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UsageCorrectionDecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    review_notes: str = Field(min_length=3, max_length=2000)


class ReconciliationSummary(BaseModel):
    generated_at: datetime
    open_total: int
    by_type: dict[str, int]
    affected_aircraft: int


class ReconciliationScanResult(BaseModel):
    generated_at: datetime
    created: int
    existing: int
    checked_aircraft: int
    checks: dict[str, int]
