# backend/amodb/apps/maintenance_program/schemas.py
#
# Typed contracts for the maintenance-program planning domain.

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from .models import AircraftProgramStatusEnum, ProgramItemStatusEnum


class MaintenanceProgramItemBase(BaseModel):
    template_code: str
    task_number: Optional[str] = None
    task_code: Optional[str] = None
    ata_chapter: Optional[str] = None
    title: str
    description: Optional[str] = None
    default_zone: Optional[str] = None
    default_position_path: Optional[str] = None
    check_group: Optional[str] = None
    interval_hours: Optional[float] = None
    interval_cycles: Optional[float] = None
    interval_days: Optional[float] = None
    threshold_hours: Optional[float] = None
    threshold_cycles: Optional[float] = None
    threshold_days: Optional[float] = None
    tolerance_hours: Optional[float] = None
    tolerance_cycles: Optional[float] = None
    tolerance_days: Optional[float] = None
    status: ProgramItemStatusEnum = ProgramItemStatusEnum.ACTIVE
    notes: Optional[str] = None


class MaintenanceProgramItemCreate(MaintenanceProgramItemBase):
    pass


class MaintenanceProgramItemUpdate(BaseModel):
    template_code: Optional[str] = None
    task_number: Optional[str] = None
    task_code: Optional[str] = None
    ata_chapter: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    default_zone: Optional[str] = None
    default_position_path: Optional[str] = None
    check_group: Optional[str] = None
    interval_hours: Optional[float] = None
    interval_cycles: Optional[float] = None
    interval_days: Optional[float] = None
    threshold_hours: Optional[float] = None
    threshold_cycles: Optional[float] = None
    threshold_days: Optional[float] = None
    tolerance_hours: Optional[float] = None
    tolerance_cycles: Optional[float] = None
    tolerance_days: Optional[float] = None
    status: Optional[ProgramItemStatusEnum] = None
    notes: Optional[str] = None


class MaintenanceProgramItemRead(MaintenanceProgramItemBase):
    id: int
    created_at: datetime
    updated_at: datetime
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None

    class Config:
        from_attributes = True


class MaintenanceProgramItemSummary(BaseModel):
    id: int
    template_code: str
    task_number: Optional[str] = None
    task_code: Optional[str] = None
    ata_chapter: Optional[str] = None
    title: str
    check_group: Optional[str] = None
    is_mandatory: bool = True

    class Config:
        from_attributes = True


class AircraftProgramItemCreate(BaseModel):
    """Create one aircraft-specific requirement.

    Aircraft identity comes from the route. Next-due and remaining values are
    never accepted from clients; they are calculated from the approved master
    requirement and last-accomplishment baseline.
    """

    program_item_id: int
    aircraft_component_id: Optional[int] = None
    override_task_code: Optional[str] = None
    override_title: Optional[str] = None
    last_done_date: Optional[date] = None
    last_done_hours: Optional[float] = None
    last_done_cycles: Optional[float] = None
    notes: Optional[str] = None


class AircraftProgramItemUpdate(BaseModel):
    """Mutable accomplishment and display fields for one aircraft requirement.

    Aircraft identity, programme identity, component linkage, and derived due
    values are deliberately excluded from the generic PATCH contract.
    """

    override_task_code: Optional[str] = None
    override_title: Optional[str] = None
    last_done_date: Optional[date] = None
    last_done_hours: Optional[float] = None
    last_done_cycles: Optional[float] = None
    status: Optional[AircraftProgramStatusEnum] = None
    notes: Optional[str] = None


class AircraftProgramItemRead(BaseModel):
    id: int
    aircraft_serial_number: str
    program_item_id: int
    aircraft_component_id: Optional[int] = None
    override_task_code: Optional[str] = None
    override_title: Optional[str] = None
    last_done_date: Optional[date] = None
    last_done_hours: Optional[float] = None
    last_done_cycles: Optional[float] = None
    next_due_date: Optional[date] = None
    next_due_hours: Optional[float] = None
    next_due_cycles: Optional[float] = None
    remaining_days: Optional[float] = None
    remaining_hours: Optional[float] = None
    remaining_cycles: Optional[float] = None
    status: AircraftProgramStatusEnum = AircraftProgramStatusEnum.PLANNED
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    program_item: Optional[MaintenanceProgramItemSummary] = None

    class Config:
        from_attributes = True


class AircraftProgramItemDueList(BaseModel):
    aircraft_serial_number: str
    generated_at: datetime
    due_now_count: int = 0
    due_soon_count: int = 0
    overdue_count: int = 0
    items: List[AircraftProgramItemRead]


class FleetPlanningSummary(BaseModel):
    fleet_aircraft: int = 0
    utilisation_current: int = 0
    utilisation_stale: int = 0
    utilisation_missing: int = 0
    overdue: int = 0
    due_soon: int = 0
    planned: int = 0
    unbaselined: int = 0
    due_within_horizon: int = 0


class FleetUtilisationRead(BaseModel):
    aircraft_serial_number: str
    registration: str
    model: Optional[str] = None
    current_hours: Optional[float] = None
    current_cycles: Optional[float] = None
    last_log_date: Optional[date] = None
    days_since_log: Optional[int] = None
    freshness_status: str
    seven_day_daily_average_hours: Optional[float] = None
    overdue_count: int = 0
    due_soon_count: int = 0
    next_due_date: Optional[date] = None
    next_due_hours: Optional[float] = None
    next_due_cycles: Optional[float] = None


class FleetDueItemRead(BaseModel):
    api_id: int
    aircraft_serial_number: str
    registration: str
    model: Optional[str] = None
    program_item_id: int
    task_code: Optional[str] = None
    task_title: str
    ata_chapter: Optional[str] = None
    status: AircraftProgramStatusEnum
    current_hours: float = 0
    current_cycles: float = 0
    last_log_date: Optional[date] = None
    next_due_date: Optional[date] = None
    next_due_hours: Optional[float] = None
    next_due_cycles: Optional[float] = None
    remaining_days: Optional[float] = None
    remaining_hours: Optional[float] = None
    remaining_cycles: Optional[float] = None
    overdue_by_days: Optional[float] = None
    overdue_by_hours: Optional[float] = None
    overdue_by_cycles: Optional[float] = None
    baseline_status: str = "BASELINED"


class FleetPlanningOverview(BaseModel):
    generated_at: datetime
    horizon_days: int = Field(ge=1, le=730)
    summary: FleetPlanningSummary
    utilisation: List[FleetUtilisationRead]
    due_items: List[FleetDueItemRead]
