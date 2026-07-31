# backend/amodb/apps/foundations/router.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..audit import services as audit_services
from . import airport_catalog, department_schemas, models, schemas, services

router = APIRouter(prefix="/foundations", tags=["foundations"])


def _effective_amo_id(user: account_models.User) -> str:
    return getattr(user, "effective_amo_id", None) or user.amo_id


def _can_manage_foundations(user: account_models.User) -> bool:
    if getattr(user, "is_system_account", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_amo_admin", False):
        return True
    return user.role in {
        account_models.AccountRole.QUALITY_MANAGER,
        account_models.AccountRole.PLANNING_ENGINEER,
        account_models.AccountRole.PRODUCTION_ENGINEER,
    }


def _require_foundation_manager(user: account_models.User) -> None:
    if not _can_manage_foundations(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges for shared foundation changes")


def _require_tenant_admin(user: account_models.User) -> None:
    if getattr(user, "is_system_account", False) or not (
        getattr(user, "is_superuser", False) or getattr(user, "is_amo_admin", False)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AMO administrator privileges are required")


def _department_read(db: Session, department: account_models.Department) -> department_schemas.DepartmentCatalogRead:
    assigned = (
        db.query(func.count(account_models.User.id))
        .filter(account_models.User.department_id == department.id)
        .scalar()
        or 0
    )
    return department_schemas.DepartmentCatalogRead(
        id=str(department.id),
        amo_id=str(department.amo_id),
        code=department.code,
        name=department.name,
        default_route=department.default_route,
        sort_order=int(department.sort_order or 0),
        is_active=bool(department.is_active),
        assigned_user_count=int(assigned),
    )


def _base_read_for_user(item: models.BaseStation, user: account_models.User) -> schemas.BaseStationRead:
    value = schemas.BaseStationRead.model_validate(item)
    if _can_manage_foundations(user):
        return value
    # Ordinary tenant users need the canonical base ID, public aerodrome codes,
    # geofence radius and prompt policy. They do not need the exact approved
    # coordinate, device accuracy or verifier identity.
    return value.model_copy(update={
        "latitude": None,
        "longitude": None,
        "coordinate_accuracy_m": None,
        "location_verified_at": None,
        "location_verified_by_user_id": None,
    })


@router.get("/contracts", response_model=schemas.FoundationContracts)
def get_foundation_contracts() -> schemas.FoundationContracts:
    return services.foundation_contracts()


@router.get("/personnel/identity-health", response_model=schemas.PersonnelIdentityHealth)
def get_personnel_identity_health(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> schemas.PersonnelIdentityHealth:
    return services.personnel_identity_health(db, amo_id=_effective_amo_id(current_user))


# ---------------------------------------------------------------------------
# Tenant-managed department catalog. Unlike the legacy list endpoint, this
# never creates seed data as a side effect of reading an empty tenant.
# ---------------------------------------------------------------------------


@router.get("/departments", response_model=List[department_schemas.DepartmentCatalogRead])
def list_departments(
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _effective_amo_id(current_user)
    query = db.query(account_models.Department).filter(account_models.Department.amo_id == amo_id)
    if not include_inactive:
        query = query.filter(account_models.Department.is_active.is_(True))
    rows = query.order_by(account_models.Department.sort_order.asc(), account_models.Department.name.asc()).all()
    return [_department_read(db, row) for row in rows]


@router.post("/departments", response_model=department_schemas.DepartmentCatalogRead, status_code=status.HTTP_201_CREATED)
def create_department(
    payload: department_schemas.DepartmentCatalogCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_tenant_admin(current_user)
    amo_id = _effective_amo_id(current_user)
    duplicate = db.query(account_models.Department).filter(
        account_models.Department.amo_id == amo_id,
        func.upper(account_models.Department.code) == payload.code.upper(),
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Department code already exists for this AMO.")
    department = account_models.Department(
        amo_id=amo_id,
        code=payload.code,
        name=payload.name,
        default_route=(payload.default_route or "").strip() or None,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )
    db.add(department)
    db.flush()
    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=str(current_user.id),
        entity_type="accounts.department",
        entity_id=str(department.id),
        action="CREATED",
        after=payload.model_dump(),
        metadata={"module": "foundations", "source": "setup_centre"},
    )
    db.commit()
    db.refresh(department)
    return _department_read(db, department)


@router.put("/departments/{department_id}", response_model=department_schemas.DepartmentCatalogRead)
def update_department(
    department_id: str,
    payload: department_schemas.DepartmentCatalogUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_tenant_admin(current_user)
    amo_id = _effective_amo_id(current_user)
    department = db.query(account_models.Department).filter(
        account_models.Department.id == department_id,
        account_models.Department.amo_id == amo_id,
    ).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found.")
    data = payload.model_dump(exclude_unset=True)
    if "code" in data and data["code"]:
        duplicate = db.query(account_models.Department).filter(
            account_models.Department.amo_id == amo_id,
            func.upper(account_models.Department.code) == data["code"].upper(),
            account_models.Department.id != department.id,
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Department code already exists for this AMO.")
    before = {
        "code": department.code,
        "name": department.name,
        "default_route": department.default_route,
        "sort_order": department.sort_order,
        "is_active": department.is_active,
    }
    for field, value in data.items():
        if field == "default_route":
            value = (value or "").strip() or None
        setattr(department, field, value)
    db.add(department)
    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=str(current_user.id),
        entity_type="accounts.department",
        entity_id=str(department.id),
        action="UPDATED",
        before=before,
        after=data,
        metadata={"module": "foundations", "source": "setup_centre"},
    )
    db.commit()
    db.refresh(department)
    return _department_read(db, department)


@router.delete("/departments/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department(
    department_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_tenant_admin(current_user)
    amo_id = _effective_amo_id(current_user)
    department = db.query(account_models.Department).filter(
        account_models.Department.id == department_id,
        account_models.Department.amo_id == amo_id,
    ).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found.")
    assigned = db.query(func.count(account_models.User.id)).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.department_id == department.id,
    ).scalar() or 0
    if assigned:
        raise HTTPException(
            status_code=409,
            detail=f"Department has {int(assigned)} assigned user(s). Reassign them or deactivate the department before deletion.",
        )
    before = {"code": department.code, "name": department.name}
    db.delete(department)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Department is still referenced by operational records and cannot be deleted.") from exc
    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=str(current_user.id),
        entity_type="accounts.department",
        entity_id=str(department_id),
        action="DELETED",
        before=before,
        metadata={"module": "foundations", "source": "setup_centre"},
    )
    db.commit()
    return None


# ---------------------------------------------------------------------------
# Bases, geofence policy, consented observations and transient evaluation.
# ---------------------------------------------------------------------------


@router.get("/airport-catalog/search", response_model=schemas.AirportCatalogSearchRead)
def search_airport_catalog(
    q: str = Query(min_length=2, max_length=120),
    latitude: Optional[float] = Query(default=None, ge=-90, le=90),
    longitude: Optional[float] = Query(default=None, ge=-180, le=180),
    limit: int = Query(default=10, ge=1, le=25),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_foundation_manager(current_user)
    try:
        return airport_catalog.search_airports(query=q, latitude=latitude, longitude=longitude, limit=limit)
    except airport_catalog.AirportCatalogUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/base-stations", response_model=List[schemas.BaseStationRead])
def list_base_stations(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    rows = services.list_base_stations(
        db,
        amo_id=_effective_amo_id(current_user),
        include_inactive=include_inactive,
    )
    return [_base_read_for_user(row, current_user) for row in rows]


@router.post("/base-stations", response_model=schemas.BaseStationRead, status_code=status.HTTP_201_CREATED)
def create_base_station(
    payload: schemas.BaseStationCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_foundation_manager(current_user)
    try:
        item = services.create_base_station(db, amo_id=_effective_amo_id(current_user), actor_user_id=current_user.id, payload=payload)
        db.commit()
        db.refresh(item)
        return item
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Base station code or alias already exists for this AMO") from exc


@router.put("/base-stations/{base_station_id}", response_model=schemas.BaseStationRead)
def update_base_station(
    base_station_id: str,
    payload: schemas.BaseStationUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_foundation_manager(current_user)
    amo_id = _effective_amo_id(current_user)
    item = services.get_base_station(db, amo_id=amo_id, base_station_id=base_station_id)
    if not item:
        raise HTTPException(status_code=404, detail="Base station not found")
    try:
        item = services.update_base_station(db, amo_id=amo_id, base_station=item, actor_user_id=current_user.id, payload=payload)
        db.commit()
        db.refresh(item)
        return item
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Base station code or alias already exists for this AMO") from exc


@router.post(
    "/base-stations/{base_station_id}/location-observations",
    response_model=schemas.BaseLocationConsensusRead,
    status_code=status.HTTP_201_CREATED,
)
def contribute_base_location(
    base_station_id: str,
    payload: schemas.BaseLocationObservationCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _effective_amo_id(current_user)
    item = services.get_base_station(db, amo_id=amo_id, base_station_id=base_station_id)
    if not item:
        raise HTTPException(status_code=404, detail="Base station not found")
    try:
        services.create_location_observation(
            db,
            amo_id=amo_id,
            base_station=item,
            actor_user_id=str(current_user.id),
            payload=payload,
        )
        consensus = services.build_location_consensus(db, amo_id=amo_id, base_station=item)
        db.commit()
        return consensus
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/base-stations/{base_station_id}/location-consensus",
    response_model=schemas.BaseLocationConsensusRead,
)
def get_base_location_consensus(
    base_station_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_foundation_manager(current_user)
    amo_id = _effective_amo_id(current_user)
    item = services.get_base_station(db, amo_id=amo_id, base_station_id=base_station_id)
    if not item:
        raise HTTPException(status_code=404, detail="Base station not found")
    return services.build_location_consensus(db, amo_id=amo_id, base_station=item)


@router.post(
    "/base-stations/{base_station_id}/location-consensus/approve",
    response_model=schemas.BaseStationRead,
)
def approve_base_location_consensus(
    base_station_id: str,
    payload: schemas.BaseLocationConsensusApproval,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_foundation_manager(current_user)
    amo_id = _effective_amo_id(current_user)
    item = services.get_base_station(db, amo_id=amo_id, base_station_id=base_station_id)
    if not item:
        raise HTTPException(status_code=404, detail="Base station not found")
    try:
        consensus = services.approve_location_consensus(
            db,
            amo_id=amo_id,
            base_station=item,
            actor_user_id=str(current_user.id),
            payload=payload,
        )
        audit_services.log_event(
            db,
            amo_id=amo_id,
            actor_user_id=str(current_user.id),
            entity_type="foundations.base_location",
            entity_id=str(item.id),
            action="CONSENSUS_APPROVED",
            after={
                "sample_count": consensus.sample_count,
                "contributor_count": consensus.distinct_contributor_count,
                "max_spread_m": consensus.max_spread_m,
            },
            metadata={"raw_observations_retained": False},
        )
        db.commit()
        db.refresh(item)
        return item
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/base-stations/{base_station_id}/location-observations", status_code=status.HTTP_204_NO_CONTENT)
def clear_base_location_observations(
    base_station_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_foundation_manager(current_user)
    amo_id = _effective_amo_id(current_user)
    item = services.get_base_station(db, amo_id=amo_id, base_station_id=base_station_id)
    if not item:
        raise HTTPException(status_code=404, detail="Base station not found")
    services.clear_location_observations(db, amo_id=amo_id, base_station_id=item.id)
    db.commit()
    return None


@router.post("/location/evaluate", response_model=schemas.LocationEvaluationRead)
def evaluate_location(
    payload: schemas.LocationEvaluationRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _effective_amo_id(current_user)
    result = services.evaluate_location(db, amo_id=amo_id, payload=payload)
    if result.review_signal and result.base_station_id:
        audit_services.log_event(
            db,
            amo_id=amo_id,
            actor_user_id=str(current_user.id),
            entity_type="foundations.location_review_signal",
            entity_id=f"{current_user.id}:{result.base_station_id}",
            action="LOCATION_REVIEW_SIGNAL",
            after={
                "base_station_id": result.base_station_id,
                "distance_m": result.distance_m,
                "geofence_radius_m": result.geofence_radius_m,
                "location_confidence": result.location_confidence,
                "reported_accuracy_m": round(payload.accuracy_m, 1),
                "reason": result.review_reason,
            },
            metadata={
                "module": "foundations",
                "raw_coordinates_persisted": False,
                "human_review_required": True,
            },
        )
        db.commit()
    return result


@router.post("/user-base-assignments", response_model=schemas.UserBaseAssignmentRead, status_code=status.HTTP_201_CREATED)
def create_user_base_assignment(
    payload: schemas.UserBaseAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_foundation_manager(current_user)
    try:
        item = services.create_user_base_assignment(db, amo_id=_effective_amo_id(current_user), actor_user_id=current_user.id, payload=payload)
        db.commit()
        db.refresh(item)
        return item
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/availability", response_model=List[schemas.AvailabilityRead])
def list_availability(
    user_id: Optional[str] = Query(default=None),
    active_at: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    return services.list_availability(db, amo_id=_effective_amo_id(current_user), user_id=user_id, active_at=active_at)


@router.post("/availability", response_model=schemas.AvailabilityRead, status_code=status.HTTP_201_CREATED)
def create_availability(
    payload: schemas.AvailabilityCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_foundation_manager(current_user)
    try:
        item = services.create_availability(db, amo_id=_effective_amo_id(current_user), actor_user_id=current_user.id, payload=payload)
        db.commit()
        db.refresh(item)
        return item
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
