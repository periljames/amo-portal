from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import User
from amodb.apps.audit.models import AuditEvent
from amodb.apps.fleet import models as fleet_models
from amodb.database import get_db
from amodb.security import require_roles

from ..aircraft_induction import models as induction_models
from . import models, schemas
from .common import (
    CONFIG_ROLES,
    _aircraft,
    _airframe_state,
    _amo_id,
    _require_authority,
)
from .context import get_context

def approve_exact_configuration(
    serial_number: str,
    payload: schemas.ExactBaselineApproval,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*CONFIG_ROLES)),
):
    _require_authority(
        user,
        CONFIG_ROLES,
        "Aircraft utilisation configuration",
    )
    amo_id = _amo_id(user)
    aircraft = _aircraft(
        db,
        amo_id,
        serial_number,
        lock=True,
    )
    component_rows = (
        db.query(fleet_models.AircraftComponent)
        .filter(
            fleet_models.AircraftComponent.amo_id == amo_id,
            fleet_models.AircraftComponent.aircraft_serial_number
            == serial_number,
            fleet_models.AircraftComponent.is_installed.is_(True),
        )
        .with_for_update()
        .all()
    )
    by_id = {row.id: row for row in component_rows}
    supplied = {row.component_id: row for row in payload.components}
    if set(supplied) != set(by_id):
        missing = sorted(set(by_id) - set(supplied))
        unknown = sorted(set(supplied) - set(by_id))
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Every installed component must receive an explicit "
                    "role and exact baseline approval"
                ),
                "missing_component_ids": missing,
                "unknown_component_ids": unknown,
            },
        )

    db.execute(
        text(
            "SET LOCAL amo.controlled_utilisation_projection = 'on'"
        )
    )
    airframe_state = _airframe_state(
        db,
        amo_id,
        serial_number,
        lock=True,
        required=False,
    )
    if airframe_state:
        airframe_state.total_hours = payload.aircraft_total_hours
        airframe_state.total_cycles = payload.aircraft_total_cycles
        airframe_state.version_no += 1
        airframe_state.approved_source_reference = (
            payload.aircraft_source_reference
        )
        airframe_state.approved_by_user_id = user.id
    else:
        airframe_state = models.AircraftExactUtilisationState(
            amo_id=amo_id,
            aircraft_serial_number=serial_number,
            total_hours=payload.aircraft_total_hours,
            total_cycles=payload.aircraft_total_cycles,
            approved_source_reference=(
                payload.aircraft_source_reference
            ),
            approved_by_user_id=user.id,
        )
        db.add(airframe_state)

    for component_id, approval in supplied.items():
        role_row = (
            db.query(
                induction_models.AircraftComponentUtilisationRole
            )
            .filter(
                induction_models.AircraftComponentUtilisationRole.amo_id
                == amo_id,
                induction_models.AircraftComponentUtilisationRole.aircraft_component_id
                == component_id,
            )
            .with_for_update()
            .first()
        )
        if role_row:
            role_row.role = approval.role
            role_row.assignment_source = "MANUAL_APPROVED"
            role_row.source_definition_id = None
            role_row.source_reference = approval.source_reference
            role_row.assigned_by_user_id = user.id
        else:
            db.add(
                induction_models.AircraftComponentUtilisationRole(
                    amo_id=amo_id,
                    aircraft_component_id=component_id,
                    role=approval.role,
                    assignment_source="MANUAL_APPROVED",
                    source_definition_id=None,
                    source_reference=approval.source_reference,
                    assigned_by_user_id=user.id,
                )
            )

        exact_state = (
            db.query(models.ComponentExactUtilisationState)
            .filter(
                models.ComponentExactUtilisationState.amo_id
                == amo_id,
                models.ComponentExactUtilisationState.aircraft_component_id
                == component_id,
            )
            .with_for_update()
            .first()
        )
        if exact_state:
            exact_state.total_hours = approval.total_hours
            exact_state.total_cycles = approval.total_cycles
            exact_state.version_no += 1
            exact_state.approved_source_reference = (
                approval.source_reference
            )
            exact_state.approved_by_user_id = user.id
        else:
            db.add(
                models.ComponentExactUtilisationState(
                    amo_id=amo_id,
                    aircraft_component_id=component_id,
                    total_hours=approval.total_hours,
                    total_cycles=approval.total_cycles,
                    approved_source_reference=(
                        approval.source_reference
                    ),
                    approved_by_user_id=user.id,
                )
            )

        component = by_id[component_id]
        component.current_hours = (
            float(approval.total_hours)
            if approval.total_hours is not None
            else None
        )
        component.current_cycles = (
            float(approval.total_cycles)
            if approval.total_cycles is not None
            else None
        )
        component.verification_status = "EXACT_BASELINE_APPROVED"

    aircraft.total_hours = float(payload.aircraft_total_hours)
    aircraft.total_cycles = float(payload.aircraft_total_cycles)
    aircraft.verification_status = "EXACT_BASELINE_APPROVED"
    db.add(
        AuditEvent(
            amo_id=amo_id,
            entity_type="AircraftExactUtilisationConfiguration",
            entity_id=serial_number,
            action="APPROVE_EXACT_BASELINE_AND_ROLES",
            actor_user_id=user.id,
            after={
                "aircraft_hours": str(
                    payload.aircraft_total_hours
                ),
                "aircraft_cycles": payload.aircraft_total_cycles,
                "components": [
                    {
                        "component_id": row.component_id,
                        "role": row.role,
                        "hours": (
                            str(row.total_hours)
                            if row.total_hours is not None
                            else None
                        ),
                        "cycles": row.total_cycles,
                        "source_reference": row.source_reference,
                    }
                    for row in payload.components
                ],
            },
        )
    )
    db.commit()
    return get_context(
        serial_number=serial_number,
        db=db,
        user=user,
    )
