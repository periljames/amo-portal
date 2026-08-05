from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import AccountRole, User
from amodb.apps.audit.models import AuditEvent
from amodb.apps.fleet import models as fleet_models
from amodb.apps.fleet import services as fleet_services
from amodb.apps.reliability import models as reliability_models
from amodb.apps.technical_records import models as technical_models
from amodb.database import get_db
from amodb.security import get_current_active_user, require_roles

from . import models, schemas, services

router = APIRouter(prefix="/daily-utilisation", tags=["daily aircraft utilisation"])

ENTRY_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
    AccountRole.PRODUCTION_ENGINEER,
    AccountRole.CERTIFYING_ENGINEER,
    AccountRole.CERTIFYING_TECHNICIAN,
)
POST_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
)


def _amo_id(user: User) -> str:
    value = getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None)
    if not value:
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return str(value)


def _aircraft(db: Session, amo_id: str, serial_number: str, *, lock: bool = False):
    query = db.query(fleet_models.Aircraft).filter(
        fleet_models.Aircraft.amo_id == amo_id,
        fleet_models.Aircraft.serial_number == serial_number,
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if not row:
        raise HTTPException(status_code=404, detail="Aircraft not found")
    return row


def _airframe_baseline(db: Session, amo_id: str, aircraft) -> tuple[Decimal | None, int | None]:
    hours = services.as_hours(aircraft.total_hours)
    cycles = services.as_cycles(aircraft.total_cycles)
    if hours is not None and cycles is not None:
        return hours, cycles
    latest = (
        db.query(fleet_models.AircraftUsage)
        .filter(
            fleet_models.AircraftUsage.amo_id == amo_id,
            fleet_models.AircraftUsage.aircraft_serial_number == aircraft.serial_number,
        )
        .order_by(fleet_models.AircraftUsage.date.desc(), fleet_models.AircraftUsage.id.desc())
        .first()
    )
    if latest:
        hours = hours if hours is not None else services.as_hours(latest.ttaf_after)
        cycles = cycles if cycles is not None else services.as_cycles(latest.tca_after)
    return hours, cycles


def _component_states(db: Session, amo_id: str, serial_number: str, *, lock: bool = False):
    query = db.query(fleet_models.AircraftComponent).filter(
        fleet_models.AircraftComponent.amo_id == amo_id,
        fleet_models.AircraftComponent.aircraft_serial_number == serial_number,
        fleet_models.AircraftComponent.is_installed.is_(True),
    )
    if lock:
        query = query.with_for_update()
    rows = query.order_by(fleet_models.AircraftComponent.position.asc()).all()
    return rows, [
        services.ComponentState(
            component_id=row.id,
            position=row.position,
            description=row.description,
            current_hours=services.as_hours(row.current_hours),
            current_cycles=services.as_cycles(row.current_cycles),
        )
        for row in rows
    ]


def _build_preview(db: Session, amo_id: str, aircraft, payload: schemas.DailyUtilisationInput):
    airframe_hours, airframe_cycles = _airframe_baseline(db, amo_id, aircraft)
    _, components = _component_states(db, amo_id, aircraft.serial_number)
    overrides = [
        services.Override(
            component_id=item.component_id,
            hours_delta=item.hours_delta,
            cycles_delta=item.cycles_delta,
            reason=item.reason,
        )
        for item in payload.component_overrides
    ]
    try:
        exposures = services.build_exposures(
            daily_hours=payload.flight_hours,
            daily_cycles=payload.cycles,
            airframe_hours=airframe_hours,
            airframe_cycles=airframe_cycles,
            components=components,
            overrides=overrides,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    blockers = services.blockers_for(exposures)
    return schemas.DailyUtilisationPreview(
        aircraft_serial_number=aircraft.serial_number,
        registration=aircraft.registration,
        operation_date=payload.operation_date,
        flight_hours=payload.flight_hours,
        cycles=payload.cycles,
        can_post=not blockers,
        blockers=blockers,
        exposures=[schemas.ExposurePreview(**item.__dict__) for item in exposures],
    )


def _entry_read(entry):
    return schemas.DailyUtilisationEntryRead.model_validate(entry)


@router.get("/aircraft/{serial_number}/context", response_model=schemas.DailyUtilisationContext)
def get_context(
    serial_number: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    amo_id = _amo_id(user)
    aircraft = _aircraft(db, amo_id, serial_number)
    airframe_hours, airframe_cycles = _airframe_baseline(db, amo_id, aircraft)
    _, component_states = _component_states(db, amo_id, serial_number)
    zero_exposures = services.build_exposures(
        daily_hours=Decimal("0.00"),
        daily_cycles=0,
        airframe_hours=airframe_hours,
        airframe_cycles=airframe_cycles,
        components=component_states,
    )
    latest = (
        db.query(models.DailyUtilisationEntry.operation_date)
        .filter(
            models.DailyUtilisationEntry.amo_id == amo_id,
            models.DailyUtilisationEntry.aircraft_serial_number == serial_number,
            models.DailyUtilisationEntry.status == "POSTED",
        )
        .order_by(models.DailyUtilisationEntry.operation_date.desc())
        .first()
    )
    return schemas.DailyUtilisationContext(
        aircraft_serial_number=serial_number,
        registration=aircraft.registration,
        model=aircraft.model,
        current_hours=airframe_hours,
        current_cycles=airframe_cycles,
        last_posted_date=latest[0] if latest else None,
        installed_components=[
            schemas.ExposurePreview(**item.__dict__)
            for item in zero_exposures
            if item.target_type != "AIRFRAME"
        ],
    )


@router.get("/aircraft/{serial_number}/entries", response_model=list[schemas.DailyUtilisationEntryRead])
def list_entries(
    serial_number: str,
    limit: int = 60,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    amo_id = _amo_id(user)
    _aircraft(db, amo_id, serial_number)
    return (
        db.query(models.DailyUtilisationEntry)
        .filter(
            models.DailyUtilisationEntry.amo_id == amo_id,
            models.DailyUtilisationEntry.aircraft_serial_number == serial_number,
        )
        .order_by(
            models.DailyUtilisationEntry.operation_date.desc(),
            models.DailyUtilisationEntry.created_at.desc(),
        )
        .limit(min(max(limit, 1), 366))
        .all()
    )


@router.post("/aircraft/{serial_number}/preview", response_model=schemas.DailyUtilisationPreview)
def preview_entry(
    serial_number: str,
    payload: schemas.DailyUtilisationInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    if payload.operation_date > date.today():
        raise HTTPException(status_code=422, detail="Future operating dates are not allowed")
    amo_id = _amo_id(user)
    aircraft = _aircraft(db, amo_id, serial_number)
    return _build_preview(db, amo_id, aircraft, payload)


@router.post(
    "/aircraft/{serial_number}/entries",
    response_model=schemas.DailyUtilisationDraftRead,
    status_code=status.HTTP_201_CREATED,
)
def create_draft(
    serial_number: str,
    payload: schemas.DailyUtilisationInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ENTRY_ROLES)),
):
    if payload.operation_date > date.today():
        raise HTTPException(status_code=422, detail="Future operating dates are not allowed")
    amo_id = _amo_id(user)
    aircraft = _aircraft(db, amo_id, serial_number)
    preview = _build_preview(db, amo_id, aircraft, payload)

    hash_payload = payload.model_dump(mode="json")
    hash_payload["aircraft_serial_number"] = serial_number
    digest = services.content_hash(hash_payload)
    existing = (
        db.query(models.DailyUtilisationEntry)
        .filter(
            models.DailyUtilisationEntry.amo_id == amo_id,
            models.DailyUtilisationEntry.idempotency_key == payload.idempotency_key,
        )
        .first()
    )
    if existing:
        if existing.content_hash != digest:
            raise HTTPException(status_code=409, detail="Idempotency key was reused with different content")
        return schemas.DailyUtilisationDraftRead(entry=_entry_read(existing), preview=preview)

    legacy_usage = (
        db.query(fleet_models.AircraftUsage.id)
        .filter(
            fleet_models.AircraftUsage.amo_id == amo_id,
            fleet_models.AircraftUsage.aircraft_serial_number == serial_number,
            fleet_models.AircraftUsage.date == payload.operation_date,
        )
        .first()
    )
    technical_usage = (
        db.query(technical_models.AircraftUtilisation.id)
        .filter(
            technical_models.AircraftUtilisation.amo_id == amo_id,
            technical_models.AircraftUtilisation.tail_id == serial_number,
            technical_models.AircraftUtilisation.entry_date == payload.operation_date,
        )
        .first()
    )
    if legacy_usage or technical_usage:
        raise HTTPException(
            status_code=409,
            detail="Existing utilisation data for this aircraft/date must be reconciled before using the daily ledger",
        )

    active = (
        db.query(models.DailyUtilisationEntry.id)
        .filter(
            models.DailyUtilisationEntry.amo_id == amo_id,
            models.DailyUtilisationEntry.aircraft_serial_number == serial_number,
            models.DailyUtilisationEntry.operation_date == payload.operation_date,
            models.DailyUtilisationEntry.status.in_(["DRAFT", "POSTED"]),
        )
        .first()
    )
    if active:
        raise HTTPException(status_code=409, detail="An active daily utilisation entry already exists for this aircraft and date")

    entry = models.DailyUtilisationEntry(
        amo_id=amo_id,
        aircraft_serial_number=serial_number,
        operation_date=payload.operation_date,
        techlog_no=payload.techlog_no,
        station=payload.station,
        flight_hours=payload.flight_hours,
        cycles=payload.cycles,
        nil_operation=payload.nil_operation,
        source_type="MANUAL",
        source_reference=payload.source_reference,
        idempotency_key=payload.idempotency_key,
        content_hash=digest,
        remarks=payload.remarks,
        created_by_user_id=user.id,
    )
    db.add(entry)
    db.flush()
    for item in preview.exposures:
        db.add(
            models.DailyUtilisationExposure(
                entry_id=entry.id,
                **item.model_dump(),
            )
        )
    db.add(
        AuditEvent(
            amo_id=amo_id,
            entity_type="DailyUtilisationEntry",
            entity_id=entry.id,
            action="CREATE_DRAFT",
            actor_user_id=user.id,
            after={"aircraft": serial_number, "date": payload.operation_date.isoformat()},
        )
    )
    db.commit()
    db.refresh(entry)
    return schemas.DailyUtilisationDraftRead(entry=_entry_read(entry), preview=preview)


@router.post("/entries/{entry_id}/post", response_model=schemas.DailyUtilisationPostRead)
def post_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*POST_ROLES)),
):
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
        raise HTTPException(status_code=404, detail="Daily utilisation entry not found")
    if entry.status == "POSTED":
        aircraft = _aircraft(db, amo_id, entry.aircraft_serial_number)
        return schemas.DailyUtilisationPostRead(
            entry=_entry_read(entry),
            aircraft_total_hours=services.as_hours(aircraft.total_hours) or Decimal("0.00"),
            aircraft_total_cycles=services.as_cycles(aircraft.total_cycles) or 0,
            component_updates=0,
        )
    if entry.status != "DRAFT":
        raise HTTPException(status_code=409, detail=f"Only DRAFT entries may be posted; current status is {entry.status}")

    aircraft = _aircraft(db, amo_id, entry.aircraft_serial_number, lock=True)
    component_rows, _ = _component_states(db, amo_id, entry.aircraft_serial_number, lock=True)
    components_by_id = {row.id: row for row in component_rows}
    exposures = (
        db.query(models.DailyUtilisationExposure)
        .filter(models.DailyUtilisationExposure.entry_id == entry.id)
        .order_by(models.DailyUtilisationExposure.component_position.asc())
        .with_for_update()
        .all()
    )
    blockers = []
    airframe_exposure = None
    for exposure in exposures:
        if exposure.target_type == "AIRFRAME":
            airframe_exposure = exposure
            current_hours, current_cycles = _airframe_baseline(db, amo_id, aircraft)
        else:
            component = components_by_id.get(exposure.component_id)
            if not component:
                blockers.append(f"{exposure.component_position} is no longer installed")
                continue
            current_hours = services.as_hours(component.current_hours)
            current_cycles = services.as_cycles(component.current_cycles)
        if current_hours != services.as_hours(exposure.before_hours) or current_cycles != exposure.before_cycles:
            blockers.append(f"{exposure.component_position} baseline changed after the draft was prepared")
        if exposure.baseline_missing:
            blockers.append(f"{exposure.component_position} has no approved utilisation baseline")
    if blockers:
        raise HTTPException(status_code=409, detail={"message": "Daily posting requires refreshed baselines", "blockers": blockers})
    if airframe_exposure is None:
        raise HTTPException(status_code=409, detail="Airframe exposure is missing")

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
        changed = False
        if exposure.after_hours is not None:
            component.current_hours = float(exposure.after_hours)
            changed = changed or exposure.hours_delta != 0
        if exposure.after_cycles is not None:
            component.current_cycles = float(exposure.after_cycles)
            changed = changed or exposure.cycles_delta != 0
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
        ttesn_after=float(first_engine.after_hours) if first_engine else None,
        tcesn_after=float(first_engine.after_cycles) if first_engine else None,
        pttsn_after=float(first_prop.after_hours) if first_prop else None,
        remarks=entry.remarks,
        note=f"Projected from immutable daily utilisation entry {entry.id}",
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
            reliability_models.AircraftUtilizationDaily.aircraft_serial_number == entry.aircraft_serial_number,
            reliability_models.AircraftUtilizationDaily.date == entry.operation_date,
        )
        .first()
    )
    if existing_reliability:
        raise HTTPException(status_code=409, detail="Reliability already contains a utilization record for this aircraft and date")
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
        aircraft_total_hours=services.as_hours(aircraft.total_hours) or Decimal("0.00"),
        aircraft_total_cycles=services.as_cycles(aircraft.total_cycles) or 0,
        component_updates=component_updates,
    )
