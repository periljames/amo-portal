from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _exact_decimal(value):
    if isinstance(value, float):
        raise ValueError("hours must be sent as a decimal string, not binary floating point")
    return value


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ComponentOverride(BaseModel):
    component_id: int
    hours_delta: Decimal | None = Field(default=None, ge=0)
    cycles_delta: int | None = Field(default=None, ge=0)
    reason: str = Field(min_length=3, max_length=500)

    _hours_exact = field_validator("hours_delta", mode="before")(_exact_decimal)


class DailyUtilisationInput(BaseModel):
    operation_date: date
    techlog_no: str = Field(min_length=1, max_length=64)
    station: str | None = Field(default=None, max_length=16)
    flight_hours: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    cycles: int = Field(ge=0)
    nil_operation: bool = False
    source_reference: str | None = Field(default=None, max_length=255)
    remarks: str | None = Field(default=None, max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=96)
    component_overrides: list[ComponentOverride] = Field(default_factory=list, max_length=100)

    _hours_exact = field_validator("flight_hours", mode="before")(_exact_decimal)

    @field_validator("techlog_no", "station", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_day(self):
        if self.nil_operation and (self.flight_hours != 0 or self.cycles != 0):
            raise ValueError("nil-operation entries must contain zero hours and zero cycles")
        if not self.nil_operation and self.flight_hours == 0 and self.cycles == 0:
            raise ValueError("record a nil operation or enter positive daily hours/cycles")
        component_ids = [item.component_id for item in self.component_overrides]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("a component may only be overridden once")
        return self


class ExposurePreview(BaseModel):
    target_type: Literal["AIRFRAME", "ENGINE", "PROPELLER", "APU", "COMPONENT"]
    component_id: int | None = None
    component_position: str
    component_description: str | None = None
    derivation: Literal["SHARED_DAILY", "ZERO_DEFAULT", "OVERRIDE"]
    hours_delta: Decimal
    cycles_delta: int
    before_hours: Decimal | None
    before_cycles: int | None
    after_hours: Decimal | None
    after_cycles: int | None
    baseline_missing: bool
    override_reason: str | None = None


class DailyUtilisationPreview(BaseModel):
    aircraft_serial_number: str
    registration: str
    operation_date: date
    flight_hours: Decimal
    cycles: int
    can_post: bool
    blockers: list[str]
    exposures: list[ExposurePreview]


class DailyUtilisationEntryRead(ORMModel):
    id: str
    amo_id: str
    aircraft_serial_number: str
    operation_date: date
    techlog_no: str
    station: str | None
    flight_hours: Decimal
    cycles: int
    nil_operation: bool
    source_type: str
    source_reference: str | None
    status: str
    revision_no: int
    idempotency_key: str
    content_hash: str
    remarks: str | None
    created_by_user_id: str | None
    posted_by_user_id: str | None
    created_at: datetime
    posted_at: datetime | None


class DailyUtilisationDraftRead(BaseModel):
    entry: DailyUtilisationEntryRead
    preview: DailyUtilisationPreview


class DailyUtilisationPostRead(BaseModel):
    entry: DailyUtilisationEntryRead
    aircraft_total_hours: Decimal
    aircraft_total_cycles: int
    component_updates: int


class DailyUtilisationContext(BaseModel):
    aircraft_serial_number: str
    registration: str
    model: str | None
    current_hours: Decimal | None
    current_cycles: int | None
    last_posted_date: date | None
    installed_components: list[ExposurePreview]
