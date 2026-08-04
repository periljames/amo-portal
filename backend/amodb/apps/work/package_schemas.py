from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class WorkPackageCreate(BaseModel):
    package_ref: Optional[str] = Field(default=None, max_length=64)
    aircraft_serial_number: str
    title: str = Field(min_length=3, max_length=255)
    description: Optional[str] = None
    check_type: Optional[str] = Field(default=None, max_length=32)
    due_date: Optional[date] = None
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None
    source_horizon_days: int = Field(default=90, ge=1, le=730)
    program_item_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.planned_start and self.planned_end and self.planned_end < self.planned_start:
            raise ValueError("planned_end must not be before planned_start")
        return self


class WorkPackageUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    description: Optional[str] = None
    check_type: Optional[str] = Field(default=None, max_length=32)
    due_date: Optional[date] = None
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.planned_start and self.planned_end and self.planned_end < self.planned_start:
            raise ValueError("planned_end must not be before planned_start")
        return self


class WorkPackageOrderRead(BaseModel):
    link_id: int
    work_order_id: int
    wo_number: str
    status: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    sequence_no: int
    source_type: str
    source_ref: Optional[str] = None
    task_count: int = 0
    completed_task_count: int = 0
    estimated_manhours: float = 0


class WorkPackageRead(BaseModel):
    id: int
    package_ref: str
    aircraft_serial_number: str
    title: str
    description: Optional[str] = None
    check_type: Optional[str] = None
    status: str
    due_date: Optional[date] = None
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None
    source_horizon_days: int
    baseline_generated_at: Optional[datetime] = None
    readiness_status: str
    readiness_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    orders: list[WorkPackageOrderRead] = Field(default_factory=list)


class WorkPackageAttachOrder(BaseModel):
    work_order_id: int
    source_type: str = Field(default="MANUAL", max_length=32)
    source_ref: Optional[str] = Field(default=None, max_length=128)


class WorkPackageReadinessRead(BaseModel):
    work_package_id: int
    readiness_status: str
    blockers: list[str]
    warnings: list[str]
    metrics: dict[str, Any]
    generated_at: datetime


class WorkPackageStatusUpdate(BaseModel):
    status: Literal["DRAFT", "REVIEW", "READY", "RELEASED", "IN_PROGRESS", "CLOSED", "CANCELLED"]
    notes: Optional[str] = Field(default=None, max_length=2000)
