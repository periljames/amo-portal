from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import schemas as account_schemas
from amodb.apps.accounts import services as account_services
from amodb.security import require_roles
from amodb.apps.audit import services as audit_services
from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.fleet import models as fleet_models
from amodb.apps.reliability import models as reliability_models

from . import schemas

router = APIRouter(prefix="/bootstrap", tags=["bootstrap"])


def _resolve_amo(
    db: Session,
    *,
    amo_id: Optional[str] = None,
    amo_code: Optional[str] = None,
) -> account_models.AMO:
    if amo_id:
        amo = db.query(account_models.AMO).filter(account_models.AMO.id == amo_id).first()
        if not amo:
            raise HTTPException(status_code=404, detail="AMO not found.")
        return amo
    if amo_code:
        amo = db.query(account_models.AMO).filter(account_models.AMO.amo_code == amo_code).first()
        if not amo:
            raise HTTPException(status_code=404, detail="AMO not found.")
        return amo
    amos = db.query(account_models.AMO).order_by(account_models.AMO.created_at.asc()).all()
    if not amos:
        raise HTTPException(status_code=400, detail="No AMO exists; create an AMO first.")
    if len(amos) > 1:
        raise HTTPException(status_code=400, detail="Multiple AMOs exist; specify amo_id or amo_code.")
    return amos[0]


@router.post(
    "/amo",
    response_model=schemas.BootstrapAMORead,
    status_code=status.HTTP_201_CREATED,
)
def bootstrap_amo(
    payload: schemas.BootstrapAMOCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(account_models.AccountRole.SUPERUSER)
    ),
):
    existing = (
        db.query(account_models.AMO)
        .filter(account_models.AMO.amo_code == payload.amo_code)
        .first()
    )
    if existing:
        audit_services.create_audit_event(
            db,
            amo_id=existing.id,
            data=audit_schemas.AuditEventCreate(
                entity_type="AMO",
                entity_id=existing.id,
                action="bootstrap_exists",
                actor_user_id=None,
                after_json={"amo_code": existing.amo_code},
            ),
        )
        db.commit()
        return existing

    if db.query(account_models.AMO).first():
        raise HTTPException(status_code=409, detail="AMO already exists; bootstrap is idempotent.")

    amo = account_models.AMO(
        amo_code=payload.amo_code,
        name=payload.name,
        login_slug=payload.login_slug,
        icao_code=payload.icao_code,
        country=payload.country,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        time_zone=payload.time_zone,
        is_active=True,
    )
    db.add(amo)
    db.flush()

    audit_services.create_audit_event(
        db,
        amo_id=amo.id,
        data=audit_schemas.AuditEventCreate(
            entity_type="AMO",
            entity_id=amo.id,
            action="bootstrap_create",
            actor_user_id=None,
            after_json={"amo_code": amo.amo_code, "name": amo.name},
        ),
    )
    db.commit()
    db.refresh(amo)
    return amo


@router.post(
    "/aircraft",
    response_model=schemas.BootstrapAircraftRead,
    status_code=status.HTTP_201_CREATED,
)
def bootstrap_aircraft(
    payload: schemas.BootstrapAircraftCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(
            account_models.AccountRole.SUPERUSER,
            account_models.AccountRole.AMO_ADMIN,
            account_models.AccountRole.PLANNING_ENGINEER,
            account_models.AccountRole.PRODUCTION_ENGINEER,
        )
    ),
):
    if current_user.is_superuser:
        amo = _resolve_amo(db, amo_id=payload.amo_id, amo_code=payload.amo_code)
    else:
        if payload.amo_id and payload.amo_id != current_user.amo_id:
            raise HTTPException(status_code=403, detail="Cross-tenant bootstrap not allowed.")
        amo = _resolve_amo(db, amo_id=current_user.amo_id)
    existing = (
        db.query(fleet_models.Aircraft)
        .filter(
            fleet_models.Aircraft.amo_id == amo.id,
            fleet_models.Aircraft.serial_number == payload.serial_number,
        )
        .first()
    )
    if existing:
        audit_services.create_audit_event(
            db,
            amo_id=amo.id,
            data=audit_schemas.AuditEventCreate(
                entity_type="Aircraft",
                entity_id=existing.serial_number,
                action="bootstrap_exists",
                actor_user_id=None,
                after_json={"serial_number": existing.serial_number},
            ),
        )
        db.commit()
        return existing

    duplicate_registration = (
        db.query(fleet_models.Aircraft)
        .filter(
            fleet_models.Aircraft.amo_id == amo.id,
            fleet_models.Aircraft.registration == payload.registration,
        )
        .first()
    )
    if duplicate_registration:
        raise HTTPException(
            status_code=409,
            detail="Registration already exists for this AMO.",
        )

    last_log_date = payload.last_log_date
    if last_log_date is None and (payload.starting_hours or payload.starting_cycles):
        last_log_date = date.today()

    aircraft = fleet_models.Aircraft(
        serial_number=payload.serial_number,
        registration=payload.registration,
        amo_id=amo.id,
        aircraft_model_code=payload.aircraft_model_code,
        template=payload.template,
        make=payload.make,
        model=payload.model,
        total_hours=payload.starting_hours,
        total_cycles=payload.starting_cycles,
        last_log_date=last_log_date,
        status="OPEN",
        is_active=True,
    )
    db.add(aircraft)
    db.flush()

    audit_services.create_audit_event(
        db,
        amo_id=amo.id,
        data=audit_schemas.AuditEventCreate(
            entity_type="Aircraft",
            entity_id=aircraft.serial_number,
            action="bootstrap_create",
            actor_user_id=None,
            after_json={
                "serial_number": aircraft.serial_number,
                "registration": aircraft.registration,
            },
        ),
    )
    db.commit()
    db.refresh(aircraft)
    return aircraft


@router.post(
    "/aircraft/{serial_number}/baseline-components",
    response_model=schemas.BootstrapComponentResult,
    status_code=status.HTTP_201_CREATED,
)
def bootstrap_baseline_components(
    serial_number: str,
    payload: List[schemas.BootstrapComponentCreate],
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(
            account_models.AccountRole.SUPERUSER,
            account_models.AccountRole.AMO_ADMIN,
            account_models.AccountRole.PLANNING_ENGINEER,
            account_models.AccountRole.PRODUCTION_ENGINEER,
        )
    ),
):
    aircraft = (
        db.query(fleet_models.Aircraft)
        .filter(fleet_models.Aircraft.serial_number == serial_number)
        .first()
    )
    if not aircraft:
        raise HTTPException(status_code=404, detail="Aircraft not found.")
    if not current_user.is_superuser and aircraft.amo_id != current_user.amo_id:
        raise HTTPException(status_code=403, detail="Cross-tenant bootstrap not allowed.")

    created_ids: List[int] = []
    skipped_ids: List[int] = []
    for component in payload:
        existing = (
            db.query(fleet_models.AircraftComponent)
            .filter(
                fleet_models.AircraftComponent.amo_id == aircraft.amo_id,
                fleet_models.AircraftComponent.aircraft_serial_number == serial_number,
                fleet_models.AircraftComponent.position == component.position,
            )
            .first()
        )
        if existing:
            skipped_ids.append(existing.id)
            continue

        record = fleet_models.AircraftComponent(
            amo_id=aircraft.amo_id,
            aircraft_serial_number=serial_number,
            position=component.position,
            part_number=component.part_number,
            serial_number=component.serial_number,
            ata=component.ata,
            description=component.description,
            installed_date=component.install_date or date.today(),
            installed_hours=component.installed_hours,
            installed_cycles=component.installed_cycles,
            current_hours=component.current_hours,
            current_cycles=component.current_cycles,
            is_installed=True,
        )
        db.add(record)
        db.flush()
        created_ids.append(record.id)

        component_instance_id = None
        if component.part_number and component.serial_number:
            instance = (
                db.query(reliability_models.ComponentInstance)
                .filter(
                    reliability_models.ComponentInstance.amo_id == aircraft.amo_id,
                    reliability_models.ComponentInstance.part_number == component.part_number,
                    reliability_models.ComponentInstance.serial_number == component.serial_number,
                )
                .first()
            )
            if not instance:
                instance = reliability_models.ComponentInstance(
                    amo_id=aircraft.amo_id,
                    part_number=component.part_number,
                    serial_number=component.serial_number,
                    description=component.description,
                    ata=component.ata,
                )
                db.add(instance)
                db.flush()
            component_instance_id = instance.id

        occurred_at = datetime.combine(record.installed_date, datetime.min.time(), tzinfo=timezone.utc)
        config_event = fleet_models.AircraftConfigurationEvent(
            amo_id=aircraft.amo_id,
            aircraft_serial_number=serial_number,
            component_instance_id=component_instance_id,
            occurred_at=occurred_at,
            event_type=fleet_models.ConfigurationEventTypeEnum.INSTALL,
            position=record.position,
            part_number=record.part_number,
            serial_number=record.serial_number,
        )
        db.add(config_event)

        audit_services.create_audit_event(
            db,
            amo_id=aircraft.amo_id,
            data=audit_schemas.AuditEventCreate(
                entity_type="AircraftComponent",
                entity_id=str(record.id),
                action="bootstrap_create",
                actor_user_id=None,
                after_json={"position": record.position, "serial_number": record.serial_number},
            ),
        )

    audit_services.create_audit_event(
        db,
        amo_id=aircraft.amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type="Aircraft",
            entity_id=aircraft.serial_number,
            action="bootstrap_baseline_components",
            actor_user_id=None,
            after_json={"created": len(created_ids), "skipped": len(skipped_ids)},
        ),
    )
    db.commit()
    return schemas.BootstrapComponentResult(created=created_ids, skipped=skipped_ids)


@router.post(
    "/users",
    response_model=schemas.BootstrapUsersResult,
    status_code=status.HTTP_201_CREATED,
)
def bootstrap_users(
    payload: List[schemas.BootstrapUserCreate],
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(account_models.AccountRole.SUPERUSER, account_models.AccountRole.AMO_ADMIN)
    ),
):
    if not payload:
        raise HTTPException(status_code=400, detail="At least one user is required.")
    created: List[str] = []
    skipped: List[str] = []
    touched_amos: set[str] = set()
    for user in payload:
        if current_user.is_superuser:
            amo = _resolve_amo(db, amo_id=user.amo_id, amo_code=user.amo_code)
        else:
            if user.amo_id and user.amo_id != current_user.amo_id:
                raise HTTPException(status_code=403, detail="Cross-tenant bootstrap not allowed.")
            amo = _resolve_amo(db, amo_id=current_user.amo_id)
        touched_amos.add(amo.id)
        existing = (
            db.query(account_models.User)
            .filter(
                account_models.User.amo_id == amo.id,
                account_models.User.email == user.email,
            )
            .first()
        )
        if existing:
            skipped.append(existing.email)
            continue
        try:
            created_user = account_services.create_user(
                db,
                account_schemas.UserCreate(
                    amo_id=amo.id,
                    department_id=user.department_id,
                    staff_code=user.staff_code,
                    email=user.email,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    full_name=user.full_name,
                    role=user.role,
                    position_title=user.position_title,
                    phone=user.phone,
                    regulatory_authority=None,
                    licence_number=None,
                    licence_state_or_country=None,
                    licence_expires_on=None,
                    password=user.password,
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        created.append(created_user.email)

    for amo_id in touched_amos:
        audit_services.create_audit_event(
            db,
            amo_id=amo_id,
            data=audit_schemas.AuditEventCreate(
                entity_type="User",
                entity_id="bootstrap",
                action="bootstrap_users",
                actor_user_id=None,
                after_json={"created": len(created), "skipped": len(skipped)},
            ),
        )
    db.commit()
    return schemas.BootstrapUsersResult(created=created, skipped=skipped)
