from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import AccountRole, User
from amodb.apps.fleet import models as fleet_models

from ..aircraft_induction import models as induction_models
from . import models, schemas, services

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
CONFIG_ROLES = POST_ROLES + (AccountRole.QUALITY_MANAGER,)

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

def _require_human(user: User) -> None:
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Active user account is required",
        )
    if user.is_system_account:
        raise HTTPException(
            status_code=403,
            detail=(
                "System or AI accounts cannot approve or post "
                "controlled aircraft utilisation"
            ),
        )

def _require_authority(
    user: User,
    allowed_roles: tuple[AccountRole, ...],
    action: str,
) -> None:
    _require_human(user)
    if (
        user.is_superuser
        or user.is_amo_admin
        or user.role in allowed_roles
    ):
        return
    raise HTTPException(
        status_code=403,
        detail=f"{action} authority is required",
    )

def _airframe_state(
    db: Session,
    amo_id: str,
    serial_number: str,
    *,
    lock: bool = False,
    required: bool = True,
):
    query = db.query(models.AircraftExactUtilisationState).filter(
        models.AircraftExactUtilisationState.amo_id == amo_id,
        models.AircraftExactUtilisationState.aircraft_serial_number
        == serial_number,
    )
    if lock:
        query = query.with_for_update()
    state = query.first()
    if required and not state:
        raise HTTPException(
            status_code=409,
            detail=(
                "This aircraft has no approved exact utilisation baseline. "
                "An authorized user must approve its configuration first."
            ),
        )
    return state

def _airframe_baseline(
    db: Session,
    amo_id: str,
    aircraft,
    *,
    lock: bool = False,
) -> tuple[Decimal | None, int | None]:
    state = _airframe_state(
        db,
        amo_id,
        aircraft.serial_number,
        lock=lock,
        required=False,
    )
    if not state:
        return None, None
    return (
        services.as_hours(state.total_hours),
        services.as_cycles(state.total_cycles),
    )

def _component_configuration(
    db: Session,
    amo_id: str,
    serial_number: str,
    *,
    lock: bool = False,
):
    query = db.query(fleet_models.AircraftComponent).filter(
        fleet_models.AircraftComponent.amo_id == amo_id,
        fleet_models.AircraftComponent.aircraft_serial_number == serial_number,
        fleet_models.AircraftComponent.is_installed.is_(True),
    )
    if lock:
        query = query.with_for_update()
    rows = query.order_by(
        fleet_models.AircraftComponent.position.asc(),
    ).all()
    component_ids = [row.id for row in rows]

    role_rows = []
    exact_rows = []
    if component_ids:
        role_rows = (
            db.query(
                induction_models.AircraftComponentUtilisationRole
            )
            .filter(
                induction_models.AircraftComponentUtilisationRole.amo_id
                == amo_id,
                induction_models.AircraftComponentUtilisationRole.aircraft_component_id.in_(
                    component_ids
                ),
            )
            .all()
        )
        exact_query = db.query(
            models.ComponentExactUtilisationState
        ).filter(
            models.ComponentExactUtilisationState.amo_id == amo_id,
            models.ComponentExactUtilisationState.aircraft_component_id.in_(
                component_ids
            ),
        )
        if lock:
            exact_query = exact_query.with_for_update()
        exact_rows = exact_query.all()

    role_by_component = {
        row.aircraft_component_id: row
        for row in role_rows
    }
    exact_by_component = {
        row.aircraft_component_id: row
        for row in exact_rows
    }
    blockers = []
    states = []
    for row in rows:
        role_row = role_by_component.get(row.id)
        exact_row = exact_by_component.get(row.id)
        if not role_row:
            blockers.append(
                f"{row.position} requires an approved utilisation role"
            )
        if not exact_row:
            blockers.append(
                f"{row.position} requires an approved exact baseline"
            )
        if role_row and exact_row:
            states.append(
                services.ComponentState(
                    component_id=row.id,
                    position=row.position,
                    description=row.description,
                    role=role_row.role,
                    current_hours=services.as_hours(
                        exact_row.total_hours
                    ),
                    current_cycles=services.as_cycles(
                        exact_row.total_cycles
                    ),
                )
            )
    return (
        rows,
        states,
        role_by_component,
        exact_by_component,
        blockers,
    )

def _component_states(
    db: Session,
    amo_id: str,
    serial_number: str,
    *,
    lock: bool = False,
):
    (
        rows,
        states,
        _role_by_component,
        exact_by_component,
        blockers,
    ) = _component_configuration(
        db,
        amo_id,
        serial_number,
        lock=lock,
    )
    if blockers:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Aircraft configuration must be approved before "
                    "daily utilisation can be prepared"
                ),
                "blockers": blockers,
            },
        )
    return rows, states, exact_by_component

def _build_preview(
    db: Session,
    amo_id: str,
    aircraft,
    payload: schemas.DailyUtilisationInput,
):
    airframe_hours, airframe_cycles = _airframe_baseline(db, amo_id, aircraft)
    _, components, _ = _component_states(db, amo_id, aircraft.serial_number)
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
        exposures=[
            schemas.ExposurePreview(**item.__dict__)
            for item in exposures
        ],
    )

def _entry_read(entry):
    return schemas.DailyUtilisationEntryRead.model_validate(entry)
