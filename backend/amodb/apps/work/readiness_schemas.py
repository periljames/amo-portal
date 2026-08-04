from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ForecastScenarioCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    start_date: date
    horizon_days: int = Field(default=180, ge=1, le=1095)
    default_daily_hours: float = Field(default=5, ge=0, le=24)
    default_daily_cycles: float = Field(default=3, ge=0, le=100)
    aircraft_assumptions_json: dict[str, dict[str, float]] = Field(default_factory=dict)


class ForecastScenarioUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=160)
    start_date: Optional[date] = None
    horizon_days: Optional[int] = Field(default=None, ge=1, le=1095)
    default_daily_hours: Optional[float] = Field(default=None, ge=0, le=24)
    default_daily_cycles: Optional[float] = Field(default=None, ge=0, le=100)
    aircraft_assumptions_json: Optional[dict[str, dict[str, float]]] = None


class ForecastScenarioItemRead(BaseModel):
    id: str
    scenario_id: str
    aircraft_serial_number: str
    registration: str
    program_item_id: int
    aircraft_program_item_id: int
    task_code: Optional[str] = None
    task_title: str
    status: str
    projected_due_date: Optional[date] = None
    projected_trigger: Optional[str] = None
    projected_days: Optional[float] = None
    remaining_hours: Optional[float] = None
    remaining_cycles: Optional[float] = None
    remaining_days: Optional[float] = None
    daily_hours: float
    daily_cycles: float
    source_snapshot_json: dict[str, Any]

    class Config:
        from_attributes = True


class ForecastScenarioRead(BaseModel):
    id: str
    name: str
    status: str
    start_date: date
    horizon_days: int
    default_daily_hours: float
    default_daily_cycles: float
    aircraft_assumptions_json: dict[str, Any]
    summary_json: dict[str, Any]
    generated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    items: list[ForecastScenarioItemRead] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ReadinessRequirementCreate(BaseModel):
    category: Literal["MANPOWER", "AUTHORIZATION", "MATERIAL", "TOOL", "FACILITY", "DOCUMENT", "SLOT"]
    reference: Optional[str] = Field(default=None, max_length=128)
    description: str = Field(min_length=3, max_length=255)
    quantity_required: float = Field(default=1, ge=0)
    quantity_confirmed: float = Field(default=0, ge=0)
    status: Literal["REQUIRED", "CONFIRMED", "SHORTAGE", "WAIVED"] = "REQUIRED"
    required_by: Optional[datetime] = None
    owner_user_id: Optional[str] = None
    evidence_json: list[str] = Field(default_factory=list)
    notes: Optional[str] = Field(default=None, max_length=2000)


class ReadinessRequirementUpdate(BaseModel):
    reference: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = Field(default=None, min_length=3, max_length=255)
    quantity_required: Optional[float] = Field(default=None, ge=0)
    quantity_confirmed: Optional[float] = Field(default=None, ge=0)
    status: Optional[Literal["REQUIRED", "CONFIRMED", "SHORTAGE", "WAIVED"]] = None
    required_by: Optional[datetime] = None
    owner_user_id: Optional[str] = None
    evidence_json: Optional[list[str]] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class ReadinessRequirementRead(BaseModel):
    id: str
    work_package_id: int
    category: str
    reference: Optional[str] = None
    description: str
    quantity_required: float
    quantity_confirmed: float
    status: str
    required_by: Optional[datetime] = None
    owner_user_id: Optional[str] = None
    evidence_json: list[str]
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReadinessAssessmentRead(BaseModel):
    id: str
    work_package_id: int
    version: int
    status: str
    blockers_json: list[str]
    warnings_json: list[str]
    metrics_json: dict[str, Any]
    assessed_at: datetime

    class Config:
        from_attributes = True


class PackageFreezeCreate(BaseModel):
    reason: str = Field(min_length=8, max_length=2000)


class PackageFreezeRead(BaseModel):
    id: str
    work_package_id: int
    version: int
    status: str
    manifest_hash: str
    manifest_json: dict[str, Any]
    reason: str
    frozen_at: datetime

    class Config:
        from_attributes = True


class ReadinessDashboardRead(BaseModel):
    scenarios: int
    completed_scenarios: int
    packages_assessed: int
    ready_packages: int
    blocked_packages: int
    shortages: int
    active_freezes: int
