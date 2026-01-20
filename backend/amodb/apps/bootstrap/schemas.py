from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from ..accounts.models import AccountRole


class BootstrapAMOCreate(BaseModel):
    amo_code: str = Field(..., min_length=2, max_length=32)
    name: str
    login_slug: str = Field(..., min_length=2, max_length=64)
    icao_code: Optional[str] = None
    country: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    time_zone: Optional[str] = "UTC"

    @field_validator("amo_code", mode="before")
    @classmethod
    def normalize_amo_code(cls, value: str) -> str:
        if value is None:
            raise ValueError("amo_code is required.")
        return str(value).strip().upper()

    @field_validator("login_slug", mode="before")
    @classmethod
    def normalize_login_slug(cls, value: str) -> str:
        if value is None:
            raise ValueError("login_slug is required.")
        return str(value).strip().lower()


class BootstrapAMORead(BootstrapAMOCreate):
    id: str
    is_active: bool

    class Config:
        from_attributes = True


class BootstrapAircraftCreate(BaseModel):
    amo_id: Optional[str] = None
    amo_code: Optional[str] = None
    serial_number: str
    registration: str
    aircraft_model_code: Optional[str] = None
    template: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    starting_hours: float = Field(default=0.0, ge=0)
    starting_cycles: float = Field(default=0.0, ge=0)
    last_log_date: Optional[date] = None


class BootstrapAircraftRead(BaseModel):
    serial_number: str
    registration: str
    amo_id: str
    aircraft_model_code: Optional[str] = None
    template: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    total_hours: Optional[float] = None
    total_cycles: Optional[float] = None
    last_log_date: Optional[date] = None

    class Config:
        from_attributes = True


class BootstrapComponentCreate(BaseModel):
    position: str
    part_number: Optional[str] = None
    serial_number: Optional[str] = None
    ata: Optional[str] = None
    install_date: Optional[date] = None
    installed_hours: Optional[float] = None
    installed_cycles: Optional[float] = None
    current_hours: Optional[float] = None
    current_cycles: Optional[float] = None
    description: Optional[str] = None


class BootstrapComponentResult(BaseModel):
    created: List[int] = Field(default_factory=list)
    skipped: List[int] = Field(default_factory=list)


class BootstrapUserCreate(BaseModel):
    amo_id: Optional[str] = None
    amo_code: Optional[str] = None
    department_id: Optional[int] = None
    staff_code: Optional[str] = None
    email: str
    first_name: str
    last_name: str
    full_name: Optional[str] = None
    role: AccountRole = AccountRole.AMO_ADMIN
    position_title: Optional[str] = None
    phone: Optional[str] = None
    password: str


class BootstrapUsersResult(BaseModel):
    created: List[str] = Field(default_factory=list)
    skipped: List[str] = Field(default_factory=list)
