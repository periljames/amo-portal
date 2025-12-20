"""
Pydantic schemas for the fleet app.

Scope:
- Aircraft master data.
- Aircraft components (engines, props, APU, etc.) with life limits.
- Aircraft utilisation entries (per techlog / flight).
- Maintenance programme items and aircraft-level status.
"""

from __future__ import annotations

from datetime import date as DateType, datetime as DateTimeType
from typing import Optional, List

from pydantic import BaseModel, Field

from .models import MaintenanceProgramCategoryEnum


# ---------------- AIRCRAFT ----------------


class AircraftBase(BaseModel):
    """
    Aircraft master record.

    `serial_number` is your AIN-style identifier.
    `registration` is the aircraft REG.
    Additional optional fields align with ATA Spec 2000-style codes
    (model code, operator code, supplier code, etc.).
    """

    # Core identifiers
    serial_number: str
    registration: str

    # Configuration / description
    template: Optional[str] = None          # e.g. 'DHC8-315', 'C208B'
    make: Optional[str] = None              # manufacturer
    model: Optional[str] = None             # subtype / series
    home_base: Optional[str] = None         # ICAO/IATA/base code
    owner: Optional[str] = None             # free text owner/operator

    # ATA Spec 2000-style coding (all optional, for standardisation)
    aircraft_model_code: Optional[str] = None          # model code used in manuals/IPC
    operator_code: Optional[str] = None                # OPR
    supplier_code: Optional[str] = None                # SPL / lessor
    company_name: Optional[str] = None                 # WHO
    internal_aircraft_identifier: Optional[str] = None # internal fleet ID / hangar ID

    status: Optional[str] = "OPEN"
    is_active: bool = True

    # Utilisation snapshot (as of last_log_date)
    last_log_date: Optional[DateType] = None
    total_hours: Optional[float] = None
    total_cycles: Optional[float] = None


class AircraftCreate(AircraftBase):
    """
    Used when initially loading / creating aircraft.
    All fields from AircraftBase are allowed.
    """
    pass


class AircraftUpdate(BaseModel):
    """
    Partial update – all fields optional.
    serial_number is taken from the path, not from the body.
    """

    registration: Optional[str] = None

    template: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    home_base: Optional[str] = None
    owner: Optional[str] = None

    # ATA Spec 2000-style coding
    aircraft_model_code: Optional[str] = None
    operator_code: Optional[str] = None
    supplier_code: Optional[str] = None
    company_name: Optional[str] = None
    internal_aircraft_identifier: Optional[str] = None

    status: Optional[str] = None
    is_active: Optional[bool] = None

    last_log_date: Optional[DateType] = None
    total_hours: Optional[float] = None
    total_cycles: Optional[float] = None


class AircraftRead(AircraftBase):
    created_at: DateTimeType
    updated_at: DateTimeType

    class Config:
        from_attributes = True


# ---------------- COMPONENTS ----------------


class AircraftComponentBase(BaseModel):
    aircraft_serial_number: str
    position: str

    ata: Optional[str] = None
    part_number: Optional[str] = None
    serial_number: Optional[str] = None
    description: Optional[str] = None

    installed_date: Optional[DateType] = None
    installed_hours: Optional[float] = None
    installed_cycles: Optional[float] = None

    current_hours: Optional[float] = None
    current_cycles: Optional[float] = None

    notes: Optional[str] = None

    # Life limit configuration
    tbo_hours: Optional[float] = None
    tbo_cycles: Optional[float] = None
    tbo_calendar_months: Optional[int] = None

    hsi_hours: Optional[float] = None
    hsi_cycles: Optional[float] = None
    hsi_calendar_months: Optional[int] = None

    # Overhaul reference
    last_overhaul_date: Optional[DateType] = None
    last_overhaul_hours: Optional[float] = None
    last_overhaul_cycles: Optional[float] = None

    # Standardisation for reliability
    manufacturer_code: Optional[str] = None
    operator_code: Optional[str] = None
    unit_of_measure_hours: Optional[str] = "H"
    unit_of_measure_cycles: Optional[str] = "C"


class AircraftComponentCreate(AircraftComponentBase):
    pass


class AircraftComponentUpdate(BaseModel):
    aircraft_serial_number: Optional[str] = None
    position: Optional[str] = None

    ata: Optional[str] = None
    part_number: Optional[str] = None
    serial_number: Optional[str] = None
    description: Optional[str] = None

    installed_date: Optional[DateType] = None
    installed_hours: Optional[float] = None
    installed_cycles: Optional[float] = None

    current_hours: Optional[float] = None
    current_cycles: Optional[float] = None

    notes: Optional[str] = None

    tbo_hours: Optional[float] = None
    tbo_cycles: Optional[float] = None
    tbo_calendar_months: Optional[int] = None

    hsi_hours: Optional[float] = None
    hsi_cycles: Optional[float] = None
    hsi_calendar_months: Optional[int] = None

    last_overhaul_date: Optional[DateType] = None
    last_overhaul_hours: Optional[float] = None
    last_overhaul_cycles: Optional[float] = None

    manufacturer_code: Optional[str] = None
    operator_code: Optional[str] = None
    unit_of_measure_hours: Optional[str] = None
    unit_of_measure_cycles: Optional[str] = None


class AircraftComponentRead(AircraftComponentBase):
    id: int

    class Config:
        from_attributes = True


# For responses that show one aircraft with its components:
class AircraftWithComponents(AircraftRead):
    components: List["AircraftComponentRead"] = []


# ---------------- AIRCRAFT USAGE ----------------


class AircraftUsageBase(BaseModel):
    """
    Core utilisation fields, excluding aircraft_serial_number which
    comes from the path when creating entries.
    """

    date: DateType
    techlog_no: str = Field(..., min_length=1)
    station: Optional[str] = None

    block_hours: float = Field(..., ge=0)
    cycles: float = Field(..., ge=0)

    ttaf_after: Optional[float] = None
    tca_after: Optional[float] = None
    ttesn_after: Optional[float] = None
    tcesn_after: Optional[float] = None
    ttsoh_after: Optional[float] = None
    ttshsi_after: Optional[float] = None
    tcsoh_after: Optional[float] = None
    pttsn_after: Optional[float] = None
    pttso_after: Optional[float] = None
    tscoa_after: Optional[float] = None

    hours_to_mx: Optional[float] = None
    days_to_mx: Optional[int] = None

    remarks: Optional[str] = None
    note: Optional[str] = None


class AircraftUsageCreate(AircraftUsageBase):
    """
    Create payload – aircraft_serial_number is taken from the path,
    not from the body.
    """
    pass


class AircraftUsageUpdate(BaseModel):
    """
    Partial update for an AircraftUsage entry.

    `last_seen_updated_at` is required for optimistic concurrency:
    the client must send the last `updated_at` value it saw. If it
    does not match the current DB value, the update will be rejected.
    """

    date: Optional[DateType] = None
    techlog_no: Optional[str] = None
    station: Optional[str] = None

    block_hours: Optional[float] = Field(default=None, ge=0)
    cycles: Optional[float] = Field(default=None, ge=0)

    ttaf_after: Optional[float] = None
    tca_after: Optional[float] = None
    ttesn_after: Optional[float] = None
    tcesn_after: Optional[float] = None
    ttsoh_after: Optional[float] = None
    ttshsi_after: Optional[float] = None
    tcsoh_after: Optional[float] = None
    pttsn_after: Optional[float] = None
    pttso_after: Optional[float] = None
    tscoa_after: Optional[float] = None

    hours_to_mx: Optional[float] = None
    days_to_mx: Optional[int] = None

    remarks: Optional[str] = None
    note: Optional[str] = None

    last_seen_updated_at: DateTimeType


class AircraftUsageRead(AircraftUsageBase):
    id: int
    aircraft_serial_number: str

    created_at: DateTimeType
    updated_at: DateTimeType
    created_by_user_id: Optional[int] = None
    updated_by_user_id: Optional[int] = None

    class Config:
        from_attributes = True


class AircraftUsageSummary(BaseModel):
    aircraft_serial_number: str
    total_hours: Optional[float] = None
    total_cycles: Optional[float] = None
    seven_day_daily_average_hours: Optional[float] = None

    next_due_program_item_id: Optional[int] = None
    next_due_task_code: Optional[str] = None
    next_due_date: Optional[DateType] = None
    next_due_hours: Optional[float] = None
    next_due_cycles: Optional[float] = None


# ---------------- MAINTENANCE PROGRAMME ----------------


class MaintenanceProgramItemBase(BaseModel):
    aircraft_template: str
    ata_chapter: str
    task_code: str
    category: MaintenanceProgramCategoryEnum = MaintenanceProgramCategoryEnum.AIRFRAME
    description: str

    interval_hours: Optional[float] = None
    interval_cycles: Optional[float] = None
    interval_days: Optional[int] = None

    is_mandatory: bool = True


class MaintenanceProgramItemCreate(MaintenanceProgramItemBase):
    pass


class MaintenanceProgramItemUpdate(BaseModel):
    aircraft_template: Optional[str] = None
    ata_chapter: Optional[str] = None
    task_code: Optional[str] = None
    category: Optional[MaintenanceProgramCategoryEnum] = None
    description: Optional[str] = None

    interval_hours: Optional[float] = None
    interval_cycles: Optional[float] = None
    interval_days: Optional[int] = None

    is_mandatory: Optional[bool] = None


class MaintenanceProgramItemRead(MaintenanceProgramItemBase):
    id: int

    class Config:
        from_attributes = True


class MaintenanceStatusRead(BaseModel):
    """
    Read-only view of maintenance status for a given aircraft/program item.
    """

    id: int
    aircraft_serial_number: str
    program_item_id: int

    last_done_date: Optional[DateType] = None
    last_done_hours: Optional[float] = None
    last_done_cycles: Optional[float] = None

    next_due_date: Optional[DateType] = None
    next_due_hours: Optional[float] = None
    next_due_cycles: Optional[float] = None

    remaining_days: Optional[int] = None
    remaining_hours: Optional[float] = None
    remaining_cycles: Optional[float] = None

    # Optional embedded programme item if you want richer responses
    program_item: Optional[MaintenanceProgramItemRead] = None

    class Config:
        from_attributes = True
