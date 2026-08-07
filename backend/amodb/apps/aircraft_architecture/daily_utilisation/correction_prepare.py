from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import User

from . import models, schemas, services
from .common import (
    POST_ROLES,
    _aircraft,
    _airframe_state,
    _amo_id,
    _component_configuration,
    _entry_read,
    _require_authority,
)


@dataclass
class CorrectionPlan:
    amo_id: str
    original: models.DailyUtilisationEntry
    replacement: schemas.DailyUtilisationInput
    reason: str
    digest: str
    aircraft: object
    airframe_state: models.AircraftExactUtilisationState
    exact_by_component: dict
    components_by_id: dict
    replacement_exposures: list[services.Exposure]
    completed_response: schemas.DailyUtilisationPostRead | None = None


def prepare_correction(
    *,
    entry_id: str,
    payload: schemas.CorrectionRequest,
    db: Session,
    user: User,
) -> CorrectionPlan:
    _require_authority(user, POST_ROLES, "Daily utilisation correction")
    amo_id = _amo_id(user)
    original = (
        db.query(models.DailyUtilisationEntry)
        .filter(
            models.DailyUtilisationEntry.id == entry_id,
            models.DailyUtilisationEntry.amo_id == amo_id,
        )
        .with_for_update()
        .first()
    )
    if not original:
        raise HTTPException(status_code=404, detail="Daily utilisation entry not found")
    if original.status != "POSTED":
        raise HTTPException(status_code=409, detail="Only a posted entry can be corrected")

    latest = (
        db.query(models.DailyUtilisationEntry)
        .filter(
            models.DailyUtilisationEntry.amo_id == amo_id,
            models.DailyUtilisationEntry.aircraft_serial_number
            == original.aircraft_serial_number,
            models.DailyUtilisationEntry.status == "POSTED",
        )
        .order_by(
            models.DailyUtilisationEntry.operation_date.desc(),
            models.DailyUtilisationEntry.revision_no.desc(),
            models.DailyUtilisationEntry.created_at.desc(),
        )
        .with_for_update()
        .first()
    )
    if not latest or latest.id != original.id:
        raise HTTPException(
            status_code=409,
            detail=(
                "Only the latest posted operating day may be corrected directly. "
                "Use controlled reconciliation for older days."
            ),
        )

    replacement = payload.replacement
    if replacement.operation_date != original.operation_date:
        raise HTTPException(
            status_code=422,
            detail="A correction must retain the original operating date",
        )
    if replacement.operation_date > date.today():
        raise HTTPException(status_code=422, detail="Future operating dates are not allowed")

    request_payload = replacement.model_dump(mode="json")
    request_payload.update(
        {
            "aircraft_serial_number": original.aircraft_serial_number,
            "supersedes_entry_id": original.id,
            "correction_reason": payload.reason,
        }
    )
    digest = services.content_hash(request_payload)
    duplicate = (
        db.query(models.DailyUtilisationEntry)
        .filter(
            models.DailyUtilisationEntry.amo_id == amo_id,
            models.DailyUtilisationEntry.idempotency_key
            == replacement.idempotency_key,
        )
        .first()
    )
    if duplicate:
        if duplicate.content_hash != digest:
            raise HTTPException(
                status_code=409,
                detail="Idempotency key was reused with different content",
            )
        state = _airframe_state(db, amo_id, original.aircraft_serial_number)
        response = schemas.DailyUtilisationPostRead(
            entry=_entry_read(duplicate),
            aircraft_total_hours=services.as_hours(state.total_hours)
            or Decimal("0.00"),
            aircraft_total_cycles=services.as_cycles(state.total_cycles) or 0,
            component_updates=0,
        )
        return CorrectionPlan(
            amo_id=amo_id,
            original=original,
            replacement=replacement,
            reason=payload.reason,
            digest=digest,
            aircraft=None,
            airframe_state=state,
            exact_by_component={},
            components_by_id={},
            replacement_exposures=[],
            completed_response=response,
        )

    aircraft = _aircraft(
        db,
        amo_id,
        original.aircraft_serial_number,
        lock=True,
    )
    airframe_state = _airframe_state(
        db,
        amo_id,
        original.aircraft_serial_number,
        lock=True,
    )
    (
        component_rows,
        _current_component_states,
        role_by_component,
        exact_by_component,
        blockers,
    ) = _component_configuration(
        db,
        amo_id,
        original.aircraft_serial_number,
        lock=True,
    )
    if blockers:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Aircraft configuration changed after the original posting",
                "blockers": blockers,
            },
        )
    components_by_id = {row.id: row for row in component_rows}

    original_exposures = (
        db.query(models.DailyUtilisationExposure)
        .filter(models.DailyUtilisationExposure.entry_id == original.id)
        .order_by(models.DailyUtilisationExposure.component_position.asc())
        .with_for_update()
        .all()
    )
    original_airframe = next(
        (row for row in original_exposures if row.target_type == "AIRFRAME"),
        None,
    )
    if not original_airframe:
        raise HTTPException(status_code=409, detail="Original airframe exposure is missing")
    if (
        services.as_hours(airframe_state.total_hours)
        != services.as_hours(original_airframe.after_hours)
        or services.as_cycles(airframe_state.total_cycles)
        != original_airframe.after_cycles
    ):
        raise HTTPException(
            status_code=409,
            detail="Exact airframe state no longer matches the entry being corrected",
        )

    base_components = []
    for row in original_exposures:
        if row.component_id is None:
            continue
        exact_state = exact_by_component.get(row.component_id)
        role_row = role_by_component.get(row.component_id)
        component = components_by_id.get(row.component_id)
        if not exact_state or not role_row or not component:
            raise HTTPException(
                status_code=409,
                detail=f"{row.component_position} configuration changed after posting",
            )
        if (
            services.as_hours(exact_state.total_hours)
            != services.as_hours(row.after_hours)
            or services.as_cycles(exact_state.total_cycles)
            != row.after_cycles
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{row.component_position} exact state no longer matches "
                    "the entry being corrected"
                ),
            )
        base_components.append(
            services.ComponentState(
                component_id=row.component_id,
                position=component.position,
                description=component.description,
                role=role_row.role,
                current_hours=services.as_hours(row.before_hours),
                current_cycles=row.before_cycles,
            )
        )

    overrides = [
        services.Override(
            component_id=item.component_id,
            hours_delta=item.hours_delta,
            cycles_delta=item.cycles_delta,
            reason=item.reason,
        )
        for item in replacement.component_overrides
    ]
    try:
        replacement_exposures = services.build_exposures(
            daily_hours=replacement.flight_hours,
            daily_cycles=replacement.cycles,
            airframe_hours=services.as_hours(original_airframe.before_hours),
            airframe_cycles=original_airframe.before_cycles,
            components=base_components,
            overrides=overrides,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    replacement_blockers = services.blockers_for(replacement_exposures)
    if replacement_blockers:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Corrected posting requires approved baselines",
                "blockers": replacement_blockers,
            },
        )
    return CorrectionPlan(
        amo_id=amo_id,
        original=original,
        replacement=replacement,
        reason=payload.reason,
        digest=digest,
        aircraft=aircraft,
        airframe_state=airframe_state,
        exact_by_component=exact_by_component,
        components_by_id=components_by_id,
        replacement_exposures=replacement_exposures,
    )
