# backend/amodb/apps/fleet/schemas.py
from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel


# ---------------- AIRCRAFT ----------------

class AircraftBase(BaseModel):
    serial_number: str
    registration: str
    template: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    home_base: Optional[str] = None
    owner: Optional[str] = None
    status: Optional[str] = "OPEN"
    is_active: bool = True

    last_log_date: Optional[date] = None
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
    status: Optional[str] = None
    is_active: Optional[bool] = None

    last_log_date: Optional[date] = None
    total_hours: Optional[float] = None
    total_cycles: Optional[float] = None


class AircraftRead(AircraftBase):
    created_at: datetime
    updated_at: datetime

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

    installed_date: Optional[date] = None
    installed_hours: Optional[float] = None
    installed_cycles: Optional[float] = None

    current_hours: Optional[float] = None
    current_cycles: Optional[float] = None

    notes: Optional[str] = None


class AircraftComponentCreate(AircraftComponentBase):
    pass


class AircraftComponentUpdate(BaseModel):
    position: Optional[str] = None
    ata: Optional[str] = None
    part_number: Optional[str] = None
    serial_number: Optional[str] = None
    description: Optional[str] = None
    installed_date: Optional[date] = None
    installed_hours: Optional[float] = None
    installed_cycles: Optional[float] = None
    current_hours: Optional[float] = None
    current_cycles: Optional[float] = None
    notes: Optional[str] = None


class AircraftComponentRead(AircraftComponentBase):
    id: int

    class Config:
        from_attributes = True


# For responses that show one aircraft with its components:
class AircraftWithComponents(AircraftRead):
    components: List[AircraftComponentRead] = []
