from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import User
from amodb.apps.audit.models import AuditEvent
from amodb.apps.fleet import models as fleet_models
from amodb.apps.fleet import services as fleet_services
from amodb.apps.reliability import models as reliability_models
from amodb.apps.technical_records import models as technical_models
from amodb.database import get_db
from amodb.security import require_roles

from . import models, schemas, services
from .common import (
    POST_ROLES,
    _aircraft,
    _airframe_state,
    _amo_id,
    _component_states,
    _entry_read,
    _require_authority,
)

def post_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*POST_ROLES)),
):
    _require_authority(user, POST_ROLES, "Daily utilisation posting")
    amo_id = _amo_id(user)
    entry = (
        db.query(models.DailyUtilisationEntry)
        .filter(
            models.DailyUtilisationEntry.id == entry_id,
            models.DailyUtilisationEntry.amo_id == amo_id,
        )
        .with_for_update()
        .first()
    )
    if not entry:
        raise HTTPException(
            status_code=404,
            detail="Daily utilisation entry not found",
        )
    if entry.status == "POSTED":
        state = _airframe_state(
            db,
            amo_id,
            entry.aircraft_serial_number,
        )
        return schemas.DailyUtilisationPostRead(
            entry=_entry_read(entry),
            aircraft_total_hours=(
                services.as_hours(state.total_hours)
                or Decimal("0.00")
            ),
            aircraft_total_cycles=(
                services.as_cycles(state.total_cycles)
                or 0
            ),
            component_updates=0,
        )
    if entry.status != "DRAFT":
        raise HTTPException(
            status_code=409,
            detail=(
                "Only DRAFT entries may be posted; "
                f"current status is {entry.status}"
            ),
        )

    aircraft = _aircraft(
        db,
        amo_id,
        entry.aircraft_serial_number,
        lock=True,
    )
    component_rows, _, exact_by_component = _component_states(
        db,
        amo_id,
        entry.aircraft_serial_number,
        lock=True,
    )
    components_by_id = {
        row.id: row
        for row in component_rows
    }
    exposures = (
        db.query(models.DailyUtilisationExposure)
        .filter(
            models.DailyUtilisationExposure.entry_id == entry.id,
        )
        .order_by(
            models.DailyUtilisationExposure.component_position.asc(),
        )
        .with_for_update()
        .all()
    )
    blockers = []
    airframe_exposure = None
    for exposure in exposures:
        if exposure.target_type == "AIRFRAME":
            airframe_exposure = exposure
            locked_airframe_state = _airframe_state(
                db,
                amo_id,
                aircraft.serial_number,
                lock=True,
            )
            current_hours = services.as_hours(
                locked_airframe_state.total_hours
            )
            current_cycles = services.as_cycles(
                locked_airframe_state.total_cycles
            )
        else:
            component = components_by_id.get(exposure.component_id)
            exact_state = exact_by_component.get(exposure.component_id)
            if not component:
                blockers.append(
                    f"{exposure.component_position} is no longer installed"
                )
                continue
            if not exact_state:
                blockers.append(
                    f"{exposure.component_position} has no approved exact baseline"
                )
                continue
            current_hours = services.as_hours(exact_state.total_hours)
            current_cycles = services.as_cycles(exact_state.total_cycles)
        if (
            current_hours != services.as_hours(exposure.before_hours)
            or current_cycles != exposure.before_cycles
        ):
            blockers.append(
                f"{exposure.component_position} baseline changed after "
                "the draft was prepared"
            )
        if exposure.baseline_missing:
            blockers.append(
                f"{exposure.component_position} has no approved "
                "utilisation baseline"
            )
    if blockers:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Daily posting requires refreshed baselines",
                "blockers": blockers,
            },
        )
    if airframe_exposure is None:
        raise HTTPException(
            status_code=409,
            detail="Airframe exposure is missing",
        )

    db.execute(
        text(
            "SET LOCAL amo.controlled_utilisation_projection = 'on'"
        )
    )
    airframe_state = locked_airframe_state
    airframe_state.total_hours = airframe_exposure.after_hours
    airframe_state.total_cycles = airframe_exposure.after_cycles
    airframe_state.last_entry_id = entry.id
    airframe_state.version_no += 1

    # Legacy floating-point fields remain compatibility projections only.
    # Future ledger baselines are always read from the exact Numeric states.
    aircraft.total_hours = float(airframe_exposure.after_hours)
    aircraft.total_cycles = float(airframe_exposure.after_cycles)
    aircraft.last_log_date = entry.operation_date

    component_updates = 0
    engine_exposures = []
    prop_exposures = []
    for exposure in exposures:
        if exposure.component_id is None:
            continue
        component = components_by_id[exposure.component_id]
        exact_state = exact_by_component[exposure.component_id]
        changed = False
        if exposure.after_hours is not None:
            exact_state.total_hours = exposure.after_hours
            component.current_hours = float(exposure.after_hours)
            changed = changed or exposure.hours_delta != 0
        if exposure.after_cycles is not None:
            exact_state.total_cycles = exposure.after_cycles
            component.current_cycles = float(exposure.after_cycles)
            changed = changed or exposure.cycles_delta != 0
        exact_state.last_entry_id = entry.id
        exact_state.version_no += 1
        if changed:
            component_updates += 1
        if exposure.target_type == "ENGINE":
            engine_exposures.append(exposure)
        elif exposure.target_type == "PROPELLER":
            prop_exposures.append(exposure)

    first_engine = engine_exposures[0] if engine_exposures else None
    first_prop = prop_exposures[0] if prop_exposures else None
    legacy_usage = fleet_models.AircraftUsage(
        amo_id=amo_id,
        aircraft_serial_number=entry.aircraft_serial_number,
        date=entry.operation_date,
        techlog_no=entry.techlog_no,
        station=entry.station,
        block_hours=float(entry.flight_hours),
        cycles=float(entry.cycles),
        ttaf_after=float(airframe_exposure.after_hours),
        tca_after=float(airframe_exposure.after_cycles),
        ttesn_after=(
            float(first_engine.after_hours)
            if first_engine
            else None
        ),
        tcesn_after=(
            float(first_engine.after_cycles)
            if first_engine
            else None
        ),
        pttsn_after=(
            float(first_prop.after_hours)
            if first_prop
            else None
        ),
        remarks=entry.remarks,
        note=(
            "Projected from immutable daily utilisation entry "
            f"{entry.id}"
        ),
        verification_status="VERIFIED",
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
    )
    db.add(legacy_usage)
    db.add(
        technical_models.AircraftUtilisation(
            amo_id=amo_id,
            tail_id=entry.aircraft_serial_number,
            entry_date=entry.operation_date,
            hours=float(entry.flight_hours),
            cycles=float(entry.cycles),
            source="DailyLedger",
            conflict_flag=False,
            correction_reason=None,
            created_by_user_id=user.id,
        )
    )

    existing_reliability = (
        db.query(reliability_models.AircraftUtilizationDaily)
        .filter(
            reliability_models.AircraftUtilizationDaily.amo_id == amo_id,
            reliability_models.AircraftUtilizationDaily.aircraft_serial_number
            == entry.aircraft_serial_number,
            reliability_models.AircraftUtilizationDaily.date
            == entry.operation_date,
        )
        .first()
    )
    if existing_reliability:
        raise HTTPException(
            status_code=409,
            detail=(
                "Reliability already contains a utilization record for this "
                "aircraft and date"
            ),
        )
    db.add(
        reliability_models.AircraftUtilizationDaily(
            amo_id=amo_id,
            aircraft_serial_number=entry.aircraft_serial_number,
            date=entry.operation_date,
            flight_hours=float(entry.flight_hours),
            cycles=float(entry.cycles),
            source=f"DailyLedger:{entry.id}",
        )
    )
    for exposure in engine_exposures:
        db.add(
            reliability_models.EngineUtilizationDaily(
                amo_id=amo_id,
                aircraft_serial_number=entry.aircraft_serial_number,
                engine_position=exposure.component_position,
                date=entry.operation_date,
                flight_hours=float(exposure.hours_delta),
                cycles=float(exposure.cycles_delta),
                source=f"DailyLedger:{entry.id}",
            )
        )

    fleet_services.update_maintenance_remaining(
        db,
        aircraft_serial_number=entry.aircraft_serial_number,
        current_hours=float(airframe_exposure.after_hours),
        current_cycles=float(airframe_exposure.after_cycles),
        current_date=entry.operation_date,
    )
    entry.status = "POSTED"
    entry.posted_by_user_id = user.id
    entry.posted_at = datetime.now(timezone.utc)
    db.add(
        AuditEvent(
            amo_id=amo_id,
            entity_type="DailyUtilisationEntry",
            entity_id=entry.id,
            action="POST",
            actor_user_id=user.id,
            after={
                "aircraft": entry.aircraft_serial_number,
                "date": entry.operation_date.isoformat(),
                "flight_hours": str(entry.flight_hours),
                "cycles": entry.cycles,
                "components_updated": component_updates,
            },
        )
    )
    db.commit()
    db.refresh(entry)
    return schemas.DailyUtilisationPostRead(
        entry=_entry_read(entry),
        aircraft_total_hours=(
            services.as_hours(airframe_state.total_hours)
            or Decimal("0.00")
        ),
        aircraft_total_cycles=(
            services.as_cycles(airframe_state.total_cycles)
            or 0
        ),
        component_updates=component_updates,
    )
