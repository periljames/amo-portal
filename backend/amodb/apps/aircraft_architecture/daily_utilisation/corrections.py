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
from .common import POST_ROLES, _entry_read
from .correction_prepare import CorrectionPlan, prepare_correction


def _apply_downstream_projections(
    db: Session,
    *,
    plan: CorrectionPlan,
    corrected: models.DailyUtilisationEntry,
    user: User,
) -> int:
    original = plan.original
    replacement = plan.replacement
    exposures = plan.replacement_exposures

    original.status = "SUPERSEDED"
    airframe = next(row for row in exposures if row.target_type == "AIRFRAME")
    plan.airframe_state.total_hours = airframe.after_hours
    plan.airframe_state.total_cycles = airframe.after_cycles
    plan.airframe_state.last_entry_id = corrected.id
    plan.airframe_state.version_no += 1
    plan.aircraft.total_hours = float(airframe.after_hours)
    plan.aircraft.total_cycles = float(airframe.after_cycles)
    plan.aircraft.last_log_date = replacement.operation_date

    engines = []
    props = []
    component_updates = 0
    for exposure in exposures:
        if exposure.component_id is None:
            continue
        exact_state = plan.exact_by_component[exposure.component_id]
        component = plan.components_by_id[exposure.component_id]
        exact_state.total_hours = exposure.after_hours
        exact_state.total_cycles = exposure.after_cycles
        exact_state.last_entry_id = corrected.id
        exact_state.version_no += 1
        component.current_hours = (
            float(exposure.after_hours) if exposure.after_hours is not None else None
        )
        component.current_cycles = (
            float(exposure.after_cycles) if exposure.after_cycles is not None else None
        )
        if exposure.hours_delta != 0 or exposure.cycles_delta != 0:
            component_updates += 1
        if exposure.target_type == "ENGINE":
            engines.append(exposure)
        elif exposure.target_type == "PROPELLER":
            props.append(exposure)

    first_engine = engines[0] if engines else None
    first_prop = props[0] if props else None
    legacy = (
        db.query(fleet_models.AircraftUsage)
        .filter(
            fleet_models.AircraftUsage.amo_id == plan.amo_id,
            fleet_models.AircraftUsage.aircraft_serial_number
            == original.aircraft_serial_number,
            fleet_models.AircraftUsage.date == original.operation_date,
        )
        .with_for_update()
        .first()
    )
    if not legacy:
        raise HTTPException(
            status_code=409,
            detail="Fleet projection for the original entry is missing",
        )
    legacy.techlog_no = replacement.techlog_no
    legacy.station = replacement.station
    legacy.block_hours = float(replacement.flight_hours)
    legacy.cycles = float(replacement.cycles)
    legacy.ttaf_after = float(airframe.after_hours)
    legacy.tca_after = float(airframe.after_cycles)
    legacy.ttesn_after = float(first_engine.after_hours) if first_engine else None
    legacy.tcesn_after = float(first_engine.after_cycles) if first_engine else None
    legacy.pttsn_after = float(first_prop.after_hours) if first_prop else None
    legacy.remarks = replacement.remarks
    legacy.note = (
        "Compatibility projection from corrected immutable daily "
        f"utilisation entry {corrected.id}"
    )
    legacy.updated_by_user_id = user.id

    technical = (
        db.query(technical_models.AircraftUtilisation)
        .filter(
            technical_models.AircraftUtilisation.amo_id == plan.amo_id,
            technical_models.AircraftUtilisation.tail_id
            == original.aircraft_serial_number,
            technical_models.AircraftUtilisation.entry_date
            == original.operation_date,
        )
        .with_for_update()
        .first()
    )
    if not technical:
        raise HTTPException(
            status_code=409,
            detail="Technical Records projection for the original entry is missing",
        )
    technical.hours = float(replacement.flight_hours)
    technical.cycles = float(replacement.cycles)
    technical.source = "DailyLedger"
    technical.correction_reason = plan.reason

    reliability = (
        db.query(reliability_models.AircraftUtilizationDaily)
        .filter(
            reliability_models.AircraftUtilizationDaily.amo_id == plan.amo_id,
            reliability_models.AircraftUtilizationDaily.aircraft_serial_number
            == original.aircraft_serial_number,
            reliability_models.AircraftUtilizationDaily.date
            == original.operation_date,
        )
        .with_for_update()
        .first()
    )
    if not reliability:
        raise HTTPException(
            status_code=409,
            detail="Reliability projection for the original entry is missing",
        )
    reliability.flight_hours = float(replacement.flight_hours)
    reliability.cycles = float(replacement.cycles)
    reliability.source = f"DailyLedger:{corrected.id}"

    (
        db.query(reliability_models.EngineUtilizationDaily)
        .filter(
            reliability_models.EngineUtilizationDaily.amo_id == plan.amo_id,
            reliability_models.EngineUtilizationDaily.aircraft_serial_number
            == original.aircraft_serial_number,
            reliability_models.EngineUtilizationDaily.date
            == original.operation_date,
        )
        .delete(synchronize_session=False)
    )
    for exposure in engines:
        db.add(
            reliability_models.EngineUtilizationDaily(
                amo_id=plan.amo_id,
                aircraft_serial_number=original.aircraft_serial_number,
                engine_position=exposure.component_position,
                date=original.operation_date,
                flight_hours=float(exposure.hours_delta),
                cycles=float(exposure.cycles_delta),
                source=f"DailyLedger:{corrected.id}",
            )
        )

    fleet_services.update_maintenance_remaining(
        db,
        aircraft_serial_number=original.aircraft_serial_number,
        current_hours=float(airframe.after_hours),
        current_cycles=float(airframe.after_cycles),
        current_date=original.operation_date,
    )
    return component_updates


def correct_latest_entry(
    entry_id: str,
    payload: schemas.CorrectionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*POST_ROLES)),
):
    plan = prepare_correction(
        entry_id=entry_id,
        payload=payload,
        db=db,
        user=user,
    )
    if plan.completed_response:
        return plan.completed_response

    db.execute(text("SET LOCAL amo.controlled_utilisation_correction = 'on'"))
    db.execute(text("SET LOCAL amo.controlled_utilisation_projection = 'on'"))
    corrected = models.DailyUtilisationEntry(
        amo_id=plan.amo_id,
        aircraft_serial_number=plan.original.aircraft_serial_number,
        operation_date=plan.replacement.operation_date,
        techlog_no=plan.replacement.techlog_no,
        station=plan.replacement.station,
        flight_hours=plan.replacement.flight_hours,
        cycles=plan.replacement.cycles,
        nil_operation=plan.replacement.nil_operation,
        source_type="MANUAL",
        source_reference=plan.replacement.source_reference,
        status="POSTED",
        revision_no=plan.original.revision_no + 1,
        supersedes_entry_id=plan.original.id,
        idempotency_key=plan.replacement.idempotency_key,
        content_hash=plan.digest,
        remarks=plan.replacement.remarks,
        correction_reason=plan.reason,
        created_by_user_id=user.id,
        posted_by_user_id=user.id,
        posted_at=datetime.now(timezone.utc),
    )
    db.add(corrected)
    db.flush()
    for exposure in plan.replacement_exposures:
        db.add(
            models.DailyUtilisationExposure(
                entry_id=corrected.id,
                **exposure.__dict__,
            )
        )

    component_updates = _apply_downstream_projections(
        db,
        plan=plan,
        corrected=corrected,
        user=user,
    )
    db.add(
        AuditEvent(
            amo_id=plan.amo_id,
            entity_type="DailyUtilisationEntry",
            entity_id=plan.original.id,
            action="SUPERSEDE",
            actor_user_id=user.id,
            before={
                "flight_hours": str(plan.original.flight_hours),
                "cycles": plan.original.cycles,
                "status": "POSTED",
            },
            after={
                "status": "SUPERSEDED",
                "replacement_entry_id": corrected.id,
                "reason": plan.reason,
            },
        )
    )
    db.add(
        AuditEvent(
            amo_id=plan.amo_id,
            entity_type="DailyUtilisationEntry",
            entity_id=corrected.id,
            action="CORRECT",
            actor_user_id=user.id,
            before={
                "superseded_entry_id": plan.original.id,
                "flight_hours": str(plan.original.flight_hours),
                "cycles": plan.original.cycles,
            },
            after={
                "flight_hours": str(plan.replacement.flight_hours),
                "cycles": plan.replacement.cycles,
                "reason": plan.reason,
            },
        )
    )
    db.commit()
    db.refresh(corrected)
    return schemas.DailyUtilisationPostRead(
        entry=_entry_read(corrected),
        aircraft_total_hours=services.as_hours(plan.airframe_state.total_hours)
        or Decimal("0.00"),
        aircraft_total_cycles=services.as_cycles(plan.airframe_state.total_cycles)
        or 0,
        component_updates=component_updates,
    )
