# backend/amodb/apps/foundations/router.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import models, schemas, services

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


@router.get("/contracts", response_model=schemas.FoundationContracts)
def get_foundation_contracts() -> schemas.FoundationContracts:
    return services.foundation_contracts()


@router.get("/personnel/identity-health", response_model=schemas.PersonnelIdentityHealth)
def get_personnel_identity_health(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> schemas.PersonnelIdentityHealth:
    return services.personnel_identity_health(db, amo_id=_effective_amo_id(current_user))


@router.get("/base-stations", response_model=List[schemas.BaseStationRead])
def list_base_stations(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    return services.list_base_stations(db, amo_id=_effective_amo_id(current_user), include_inactive=include_inactive)


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
    item = db.query(models.BaseStation).filter(models.BaseStation.id == base_station_id, models.BaseStation.amo_id == amo_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Base station not found")
    try:
        item = services.update_base_station(db, amo_id=amo_id, base_station=item, actor_user_id=current_user.id, payload=payload)
        db.commit()
        db.refresh(item)
        return item
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Base station code or alias already exists for this AMO") from exc


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
