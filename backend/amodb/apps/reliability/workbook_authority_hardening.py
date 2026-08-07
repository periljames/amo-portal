"""Protect authoritative Reliability sources during workbook approval."""
from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException

from . import models as reliability_models
from . import workbook_parity as wp


def apply() -> None:
    original = wp._approve_to_canonical

    def approve_to_canonical(db, record, user_id):
        if record.dataset_code == wp.WorkbookDatasetCode.AU.value:
            existing = (
                db.query(reliability_models.AircraftUtilizationDaily)
                .filter(
                    reliability_models.AircraftUtilizationDaily.amo_id == record.amo_id,
                    reliability_models.AircraftUtilizationDaily.aircraft_serial_number == record.aircraft_serial_number,
                    reliability_models.AircraftUtilizationDaily.date == record.event_date,
                )
                .one_or_none()
            )
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Authoritative aircraft utilisation already exists for this aircraft and date. "
                        "Workbook approval cannot overwrite it; reconcile the source evidence first."
                    ),
                )

            flight_hours = Decimal(str(record.payload["flight_hours"])).quantize(Decimal("0.001"))
            flight_cycles = int(record.payload["flight_cycles"])
            db.add(
                reliability_models.AircraftUtilizationDaily(
                    amo_id=record.amo_id,
                    aircraft_serial_number=record.aircraft_serial_number,
                    date=record.event_date,
                    flight_hours=flight_hours,
                    cycles=flight_cycles,
                    source=record.reference_code or record.payload.get("source_reference") or record.record_number,
                )
            )
            return

        return original(db, record, user_id)

    wp._approve_to_canonical = approve_to_canonical


apply()
