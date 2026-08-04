from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class AmpRevisionCreate(BaseModel):
    template_code: str = Field(min_length=2, max_length=50)
    revision_code: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=3, max_length=255)
    effective_date: Optional[date] = None
    source_reference: Optional[str] = Field(default=None, max_length=255)
    notes: Optional[str] = None


class AmpRevisionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    effective_date: Optional[date] = None
    source_reference: Optional[str] = Field(default=None, max_length=255)
    notes: Optional[str] = None


class AmpRevisionRead(BaseModel):
    id: int
    template_code: str
    revision_code: str
    title: str
    status: str
    effective_date: Optional[date] = None
    source_reference: Optional[str] = None
    notes: Optional[str] = None
    approved_by_user_id: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    task_count: int = 0
    active_aircraft_count: int = 0


class AmpRevisionApproval(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=2000)


class AmpBaselineApply(BaseModel):
    aircraft_serial_number: str
    notes: Optional[str] = Field(default=None, max_length=2000)


class AmpBaselineRead(BaseModel):
    id: int
    aircraft_serial_number: str
    revision_id: int
    template_code: str
    revision_code: str
    revision_title: str
    status: str
    applied_by_user_id: Optional[str] = None
    applied_at: datetime
    notes: Optional[str] = None
    requirements_created: int = 0
    requirements_existing: int = 0


class AmpCoverageRow(BaseModel):
    aircraft_serial_number: str
    registration: str
    model: Optional[str] = None
    template_code: Optional[str] = None
    revision_code: Optional[str] = None
    revision_status: Optional[str] = None
    baseline_status: str
    applied_at: Optional[datetime] = None
    active_requirement_count: int = 0
    unbaselined_requirement_count: int = 0


class AmpCoverageRead(BaseModel):
    generated_at: datetime
    summary: dict[str, int]
    rows: list[AmpCoverageRow]
