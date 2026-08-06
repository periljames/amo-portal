"""Runtime hardening applied before operational Reliability routes register."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import BigInteger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.types import TypeDecorator


class ExactAviationCount(TypeDecorator):
    """Bind cycle and landing counts as exact signed 64-bit integers."""

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value: Any, dialect):
        if value is None:
            return None
        try:
            parsed = Decimal(str(value))
        except Exception as exc:
            raise ValueError("Cycle value must be numeric.") from exc
        if not parsed.is_finite() or parsed != parsed.to_integral_value():
            raise ValueError("Cycle value must be a whole number.")
        return int(parsed)

    def process_result_value(self, value: Any, dialect):
        return None if value is None else int(value)


def _whole_minutes(start: datetime, end: datetime, utc) -> int:
    seconds = (utc(end) - utc(start)).total_seconds()
    return int((Decimal(str(seconds)) / Decimal("60")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def apply(operational: Any) -> None:
    if getattr(operational, "_RUNTIME_HARDENED", False):
        return

    operational.ExactAviationCount = ExactAviationCount

    class FlightOperationCreate(BaseModel):
        """User-facing flight occurrence contract with derived operational values."""

        record_number: str = Field(min_length=1, max_length=80)
        event_type: str
        occurred_at: Optional[datetime] = None
        aircraft_serial_number: str = Field(min_length=1, max_length=50)
        flight_number: str = Field(min_length=1, max_length=24)
        origin_station: Optional[str] = Field(default=None, max_length=8)
        destination_station: Optional[str] = Field(default=None, max_length=8)
        scheduled_departure_at: Optional[datetime] = None
        actual_departure_at: Optional[datetime] = None
        delay_minutes: Optional[int] = Field(default=None, ge=0)
        dispatch_impact: Optional[str] = Field(default=None, max_length=40)
        severity: str = "MEDIUM"
        ata_chapter: Optional[str] = Field(default=None, max_length=20)
        description: str = Field(min_length=3, max_length=12000)

        @field_validator("event_type")
        @classmethod
        def event_type_valid(cls, value: str) -> str:
            resolved = value.strip().upper()
            if resolved not in operational.FLIGHT_TYPES:
                raise ValueError("Unsupported Flight Operations interruption type.")
            return resolved

        @field_validator("severity")
        @classmethod
        def severity_valid(cls, value: str) -> str:
            resolved = value.strip().upper()
            if resolved not in operational.SEVERITIES:
                raise ValueError("Unsupported severity.")
            return resolved

        @model_validator(mode="after")
        def timing_valid(self):
            scheduled = self.scheduled_departure_at
            actual = self.actual_departure_at
            impact_by_event = {
                "TECHNICAL_DELAY": "DELAYED_DEPARTURE",
                "TECHNICAL_CANCELLATION": "CANCELLED",
                "RETURN_TO_GATE": "RETURN_TO_GATE",
                "AIR_TURNBACK": "AIR_TURNBACK",
                "DIVERSION": "DIVERTED",
                "IN_FLIGHT_SHUTDOWN": "IN_FLIGHT_SHUTDOWN",
                "ABORTED_TAKEOFF": "ABORTED_TAKEOFF",
            }
            derived_impact = impact_by_event[self.event_type]

            if self.dispatch_impact is not None and self.dispatch_impact != derived_impact:
                raise ValueError("dispatch_impact conflicts with the selected occurrence type.")

            if scheduled and actual and operational._utc(actual) < operational._utc(scheduled):
                raise ValueError("Actual departure cannot precede scheduled departure.")

            if self.event_type == "TECHNICAL_DELAY":
                if scheduled is None or actual is None:
                    raise ValueError("Technical delay records require scheduled and actual departure times.")
                derived_delay = _whole_minutes(scheduled, actual, operational._utc)
                if derived_delay <= 0:
                    raise ValueError("Technical delay requires actual departure after scheduled departure.")
                if self.delay_minutes is not None and self.delay_minutes != derived_delay:
                    raise ValueError("delay_minutes must match the scheduled-to-actual departure calculation.")
                self.occurred_at = actual
                self.delay_minutes = derived_delay
                self.dispatch_impact = derived_impact
                return self

            if self.event_type == "TECHNICAL_CANCELLATION":
                if scheduled is None:
                    raise ValueError("Technical cancellation records require the scheduled departure time.")
                if actual is not None:
                    raise ValueError("A cancelled flight cannot contain an actual departure time.")

            if self.occurred_at is None:
                raise ValueError("This Flight Operations occurrence requires an occurrence time.")

            self.delay_minutes = None
            self.dispatch_impact = derived_impact
            return self

    class FlightOperationRead(operational.TenantModel):
        id: str
        record_number: str
        revision: int
        event_type: str
        occurred_at: datetime
        aircraft_serial_number: str
        flight_number: str
        origin_station: Optional[str]
        destination_station: Optional[str]
        scheduled_departure_at: Optional[datetime]
        actual_departure_at: Optional[datetime]
        delay_minutes: Optional[int]
        dispatch_impact: Optional[str]
        severity: str
        ata_chapter: Optional[str]
        description: str
        status: str
        canonical_event_id: Optional[int]
        approved_at: Optional[datetime]
        closed_at: Optional[datetime]
        closure_note: Optional[str]

    operational.FlightOperationCreate = FlightOperationCreate
    operational.FlightOperationRead = FlightOperationRead

    original_deferral = operational.create_deferral
    original_shop = operational.create_shop_finding
    original_sms = operational.create_sms

    def _severity(payload: Any) -> Any:
        resolved = str(payload.severity or "").strip().upper()
        if resolved not in operational.SEVERITIES:
            raise HTTPException(status_code=422, detail="Unsupported Reliability severity.")
        return payload.model_copy(update={"severity": resolved})

    def create_flight_operation(payload, context=Depends(operational._context)):
        current_user, db, amo_id = context
        operational._require(db, current_user, "reliability.ingest")
        payload = _severity(payload)
        operational._aircraft(db, amo_id, payload.aircraft_serial_number)
        values = payload.model_dump()
        values["origin_station"] = payload.origin_station.upper() if payload.origin_station else None
        values["destination_station"] = payload.destination_station.upper() if payload.destination_station else None
        row = operational.ReliabilityFlightOperation(
            amo_id=amo_id,
            **values,
            created_by_user_id=str(current_user.id),
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise operational._duplicate_error(exc, "Flight Operations record") from exc
        operational._revision_event(
            db,
            amo_id=amo_id,
            source_type="FLIGHT_OPERATION",
            source_id=row.id,
            revision=1,
            action="CREATED",
            payload={
                "record_number": row.record_number,
                "scheduled_departure_at": row.scheduled_departure_at,
                "actual_departure_at": row.actual_departure_at,
                "delay_minutes": row.delay_minutes,
            },
            actor_user_id=str(current_user.id),
        )
        db.commit()
        db.refresh(row)
        return row

    def create_deferral(payload, context=Depends(operational._context)):
        return original_deferral(_severity(payload), context)

    def create_shop_finding(payload, context=Depends(operational._context)):
        return original_shop(_severity(payload), context)

    def create_sms(payload, context=Depends(operational._context)):
        return original_sms(_severity(payload), context)

    create_flight_operation.__annotations__ = {"payload": operational.FlightOperationCreate}
    create_deferral.__annotations__ = {"payload": operational.DeferralCreate}
    create_shop_finding.__annotations__ = {"payload": operational.ShopFindingCreate}
    create_sms.__annotations__ = {"payload": operational.SmsOccurrenceCreate}

    operational.create_flight_operation = create_flight_operation
    operational.create_deferral = create_deferral
    operational.create_shop_finding = create_shop_finding
    operational.create_sms = create_sms
    operational._RUNTIME_HARDENED = True


def finalize(operational: Any) -> None:
    """Ensure system scheduler cycles also execute operational expiry/recovery."""
    current = operational.services.harvest_internal_sources
    if getattr(current, "_system_operational_wrapper", False):
        return

    def harvest_with_system_operational(db, *, amo_id: str, actor_user_id):
        results = list(current(db, amo_id=amo_id, actor_user_id=actor_user_id))
        if actor_user_id is None:
            results.extend(
                operational._harvest_operational(
                    db,
                    amo_id=amo_id,
                    actor_user_id=None,
                )
            )
        return results

    setattr(harvest_with_system_operational, "_system_operational_wrapper", True)
    operational.services.harvest_internal_sources = harvest_with_system_operational
