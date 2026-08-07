from __future__ import annotations

from decimal import Decimal

from fastapi import Depends
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import User
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models, schemas, services
from .common import (
    _aircraft,
    _airframe_state,
    _amo_id,
    _component_configuration,
)

def get_context(
    serial_number: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    amo_id = _amo_id(user)
    aircraft = _aircraft(db, amo_id, serial_number)
    airframe_state = _airframe_state(
        db,
        amo_id,
        serial_number,
        required=False,
    )
    current_hours = (
        services.as_hours(airframe_state.total_hours)
        if airframe_state
        else None
    )
    current_cycles = (
        services.as_cycles(airframe_state.total_cycles)
        if airframe_state
        else None
    )
    (
        component_rows,
        component_states,
        role_by_component,
        exact_by_component,
        component_blockers,
    ) = _component_configuration(
        db,
        amo_id,
        serial_number,
    )
    blockers = list(component_blockers)
    if not airframe_state:
        blockers.insert(
            0,
            "Airframe requires an approved exact utilisation baseline",
        )
    zero_exposures = []
    if current_hours is not None and current_cycles is not None:
        zero_exposures = services.build_exposures(
            daily_hours=Decimal("0.00"),
            daily_cycles=0,
            airframe_hours=current_hours,
            airframe_cycles=current_cycles,
            components=component_states,
        )
    latest = (
        db.query(models.DailyUtilisationEntry.operation_date)
        .filter(
            models.DailyUtilisationEntry.amo_id == amo_id,
            models.DailyUtilisationEntry.aircraft_serial_number
            == serial_number,
            models.DailyUtilisationEntry.status == "POSTED",
        )
        .order_by(
            models.DailyUtilisationEntry.operation_date.desc(),
            models.DailyUtilisationEntry.revision_no.desc(),
        )
        .first()
    )
    return schemas.DailyUtilisationContext(
        aircraft_serial_number=serial_number,
        registration=aircraft.registration,
        model=aircraft.model,
        current_hours=current_hours,
        current_cycles=current_cycles,
        last_posted_date=latest[0] if latest else None,
        installed_components=[
            schemas.ExposurePreview(**item.__dict__)
            for item in zero_exposures
            if item.target_type != "AIRFRAME"
        ],
        components=[
            schemas.ComponentRoleRead(
                component_id=row.id,
                position=row.position,
                description=row.description,
                role=(
                    role_by_component[row.id].role
                    if row.id in role_by_component
                    else None
                ),
                current_hours=(
                    services.as_hours(
                        exact_by_component[row.id].total_hours
                    )
                    if row.id in exact_by_component
                    else None
                ),
                current_cycles=(
                    services.as_cycles(
                        exact_by_component[row.id].total_cycles
                    )
                    if row.id in exact_by_component
                    else None
                ),
                classified=(
                    row.id in role_by_component
                    and row.id in exact_by_component
                ),
            )
            for row in component_rows
        ],
        configuration_blockers=blockers,
    )

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
