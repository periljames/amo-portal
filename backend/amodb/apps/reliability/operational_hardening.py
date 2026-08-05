"""Final runtime hardening applied before operational Reliability routes register."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import Depends, HTTPException
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


def apply(operational: Any) -> None:
    if getattr(operational, "_RUNTIME_HARDENED", False):
        return

    operational.ExactAviationCount = ExactAviationCount

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
            payload={"record_number": row.record_number},
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
