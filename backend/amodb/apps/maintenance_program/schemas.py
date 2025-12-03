# backend/amodb/apps/maintenance_program/schemas.py
#
# Schemas for the maintenance_program module:
# - MaintenanceProgramItem* : master AMP task definitions per template/type.
# - AircraftProgramItem*   : per-aircraft instances with last-done / next-due.
#
# These are the “planning layer” objects that feed apps.work
# (WorkOrder / TaskCard) via TaskCard.program_item_id.

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel

from .models import (
    ProgramItemStatusEnum,
    AircraftProgramStatusEnum,
)


# ---------------------------------------------------------------------------
# Maintenance program items (master AMP tasks)
# ---------------------------------------------------------------------------


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
    """
    Create a new AMP task definition for a given template / type.
    """
    pass


class MaintenanceProgramItemUpdate(BaseModel):
    """
    Partial update of an AMP task definition.
    """

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
    created_by_user_id: Optional[int] = None
    updated_by_user_id: Optional[int] = None

    class Config:
        from_attributes = True


# A lightweight summary, useful when nesting inside AircraftProgramItemRead
class MaintenanceProgramItemSummary(BaseModel):
    id: int
    template_code: str
    task_number: Optional[str] = None
    task_code: Optional[str] = None
    ata_chapter: Optional[str] = None
    title: str
    check_group: Optional[str] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Aircraft program items (per-aircraft due records)
# ---------------------------------------------------------------------------


class AircraftProgramItemBase(BaseModel):
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
    is_mandatory: bool = True

    notes: Optional[str] = None


class AircraftProgramItemCreate(AircraftProgramItemBase):
    """
    Create a per-aircraft instance of a program item.

    In a typical flow, these are seeded when you:
    - add an aircraft to the fleet and apply a template AMP, or
    - add a new MaintenanceProgramItem and roll it out to applicable aircraft.
    """
    pass


class AircraftProgramItemUpdate(BaseModel):
    """
    Partial update of the per-aircraft AMP record.
    Typically used by the scheduling service when:
      - recalculating next-due values, or
      - updating last-done values after task completion.
    """

    aircraft_serial_number: Optional[str] = None
    program_item_id: Optional[int] = None
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

    status: Optional[AircraftProgramStatusEnum] = None
    is_mandatory: Optional[bool] = None

    notes: Optional[str] = None


class AircraftProgramItemRead(AircraftProgramItemBase):
    id: int

    created_at: datetime
    updated_at: datetime
    created_by_user_id: Optional[int] = None
    updated_by_user_id: Optional[int] = None

    # Optional nested summary of the master program item
    program_item: Optional[MaintenanceProgramItemSummary] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Convenience list responses
# ---------------------------------------------------------------------------


class AircraftProgramItemDueList(BaseModel):
    """
    High-level response for "show me what's due on this aircraft".

    You can adapt / expand this later once the scheduling logic is in place.
    """

    aircraft_serial_number: str
    generated_at: datetime
    items: List[AircraftProgramItemRead]
