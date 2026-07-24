from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..workforce import permissions as workforce_permissions
from . import models, schemas, services

router = APIRouter(prefix="/foundations", tags=["foundations"])


def _effective_amo_id(user: account_models.User) -> str:
    return getattr(user, "effective_amo_id", None) or user.amo_id


def _has(
    db: Session,
    user: account_models.User,
    permission: workforce_permissions.PermissionCode,
    *,
    base_station_id: Optional[str] = None,
) -> bool:
    return workforce_permissions.has_permission(
        db,
        user=user,
        permission=permission,
        base_station_id=base_station_id,
    )


def _require(
    db: Session,
    user: account_models.User,
    permission: workforce_permissions.PermissionCode,
    *,
    base_station_id: Optional[str] = None,
) -> None:
    workforce_permissions.require_permission(
        db,
        user=user,
        permission=permission,
        base_station_id=base_station_id,
    )


def _conflict_detail(message: str, *, error_code: str, conflicts: Optional[list[dict]] = None) -> dict:
    return {
        "detail": message,
        "error_code": error_code,
        "field_errors": {},
        "conflicts": conflicts or [],
        "retryable": False,
    }


@router.get("/contracts", response_model=schemas.FoundationContracts)
def get_foundation_contracts() -> schemas.FoundationContracts:
    return services.foundation_contracts()


@router.get("/personnel/identity-health", response_model=schemas.PersonnelIdentityHealth)
def get_personnel_identity_health(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> schemas.PersonnelIdentityHealth:
    _require(db, current_user, workforce_permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE)
    return services.personnel_identity_health(db, amo_id=_effective_amo_id(current_user))


@router.get("/base-stations", response_model=List[schemas.BaseStationRead])
def list_base_stations(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ORGANISATION_BASES_VIEW)
    if include_inactive:
        _require(db, current_user, workforce_permissions.PermissionCode.ORGANISATION_BASES_MANAGE)
    return services.list_base_stations(db, amo_id=_effective_amo_id(current_user), include_inactive=include_inactive)


@router.post("/base-stations", response_model=schemas.BaseStationRead, status_code=status.HTTP_201_CREATED)
def create_base_station(
    payload: schemas.BaseStationCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ORGANISATION_BASES_MANAGE)
    try:
        item = services.create_base_station(
            db,
            amo_id=_effective_amo_id(current_user),
            actor_user_id=current_user.id,
            payload=payload,
        )
        db.commit()
        db.refresh(item)
        return item
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=_conflict_detail(
                "Base station code or alias already exists for this AMO.",
                error_code="BASE_STATION_IDENTITY_CONFLICT",
            ),
        ) from exc


@router.get("/base-stations/{base_station_id}/impact", response_model=schemas.BaseStationImpactRead)
def base_station_impact(
    base_station_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(
        db,
        current_user,
        workforce_permissions.PermissionCode.ORGANISATION_BASES_MANAGE,
        base_station_id=base_station_id,
    )
    amo_id = _effective_amo_id(current_user)
    item = db.query(models.BaseStation).filter(
        models.BaseStation.id == base_station_id,
        models.BaseStation.amo_id == amo_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Base station not found")
    return services.base_station_dependency_impact(db, amo_id=amo_id, base_station_id=base_station_id)


@router.put("/base-stations/{base_station_id}", response_model=schemas.BaseStationRead)
def update_base_station(
    base_station_id: str,
    payload: schemas.BaseStationUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(
        db,
        current_user,
        workforce_permissions.PermissionCode.ORGANISATION_BASES_MANAGE,
        base_station_id=base_station_id,
    )
    amo_id = _effective_amo_id(current_user)
    item = db.query(models.BaseStation).filter(
        models.BaseStation.id == base_station_id,
        models.BaseStation.amo_id == amo_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Base station not found")
    if payload.is_active is False and item.is_active:
        impact = services.base_station_dependency_impact(db, amo_id=amo_id, base_station_id=base_station_id)
        if not impact.can_deactivate:
            raise HTTPException(
                status_code=409,
                detail=_conflict_detail(
                    "This base still has active operational dependencies. Reassign or end them before deactivation.",
                    error_code="BASE_DEACTIVATION_BLOCKED",
                    conflicts=[dependency.model_dump() for dependency in impact.dependencies],
                ),
            )
    try:
        item = services.update_base_station(
            db,
            amo_id=amo_id,
            base_station=item,
            actor_user_id=current_user.id,
            payload=payload,
        )
        db.commit()
        db.refresh(item)
        return item
    except RuntimeError as exc:
        db.rollback()
        if str(exc).startswith("BASE_STATION_REVISION_CONFLICT"):
            raise HTTPException(
                status_code=409,
                detail=_conflict_detail(
                    "This base was changed by another user. Reload before saving.",
                    error_code="BASE_STATION_REVISION_CONFLICT",
                    conflicts=[{"current_updated_at": str(exc).partition(":")[2]}],
                ),
            ) from exc
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=_conflict_detail(
                "Base station code or alias already exists for this AMO.",
                error_code="BASE_STATION_IDENTITY_CONFLICT",
            ),
        ) from exc


@router.get("/user-base-assignments", response_model=List[schemas.UserBaseAssignmentRead])
def list_user_base_assignments(
    user_id: Optional[str] = Query(default=None),
    active_on: Optional[date] = Query(default=None),
    include_expired: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    can_view_all = _has(db, current_user, workforce_permissions.PermissionCode.WORKFORCE_DEPLOYMENTS_VIEW)
    if user_id and user_id != current_user.id and not can_view_all:
        _require(db, current_user, workforce_permissions.PermissionCode.WORKFORCE_DEPLOYMENTS_VIEW)
    if not can_view_all:
        user_id = current_user.id
    return services.list_user_base_assignments(
        db,
        amo_id=_effective_amo_id(current_user),
        user_id=user_id,
        active_on=active_on,
        include_expired=include_expired,
    )


@router.post("/user-base-assignments", response_model=schemas.UserBaseAssignmentRead, status_code=status.HTTP_201_CREATED)
def create_user_base_assignment(
    payload: schemas.UserBaseAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(
        db,
        current_user,
        workforce_permissions.PermissionCode.WORKFORCE_DEPLOYMENTS_MANAGE,
        base_station_id=payload.base_station_id,
    )
    try:
        item = services.create_user_base_assignment(
            db,
            amo_id=_effective_amo_id(current_user),
            actor_user_id=current_user.id,
            payload=payload,
        )
        db.commit()
        db.refresh(item)
        return item
    except ValueError as exc:
        db.rollback()
        detail = str(exc)
        conflict = "already covers" in detail or "Another temporary" in detail
        raise HTTPException(
            status_code=409 if conflict else 400,
            detail=_conflict_detail(
                detail,
                error_code="BASE_DEPLOYMENT_CONFLICT" if conflict else "BASE_DEPLOYMENT_INVALID",
            ),
        ) from exc


@router.put("/user-base-assignments/{assignment_id}", response_model=schemas.UserBaseAssignmentRead)
def update_user_base_assignment(
    assignment_id: str,
    payload: schemas.UserBaseAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _effective_amo_id(current_user)
    item = db.query(models.UserBaseAssignment).filter(
        models.UserBaseAssignment.id == assignment_id,
        models.UserBaseAssignment.amo_id == amo_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Base assignment not found")
    _require(
        db,
        current_user,
        workforce_permissions.PermissionCode.WORKFORCE_DEPLOYMENTS_MANAGE,
        base_station_id=payload.base_station_id or item.base_station_id,
    )
    try:
        item = services.update_user_base_assignment(
            db,
            amo_id=amo_id,
            assignment=item,
            actor_user_id=current_user.id,
            payload=payload,
        )
        db.commit()
        db.refresh(item)
        return item
    except RuntimeError as exc:
        db.rollback()
        if str(exc).startswith("USER_BASE_ASSIGNMENT_REVISION_CONFLICT"):
            raise HTTPException(
                status_code=409,
                detail=_conflict_detail(
                    "This deployment was changed by another user. Reload before saving.",
                    error_code="BASE_DEPLOYMENT_REVISION_CONFLICT",
                    conflicts=[{"current_updated_at": str(exc).partition(":")[2]}],
                ),
            ) from exc
        raise
    except ValueError as exc:
        db.rollback()
        detail = str(exc)
        conflict = "already covers" in detail or "Another temporary" in detail
        raise HTTPException(
            status_code=409 if conflict else 400,
            detail=_conflict_detail(
                detail,
                error_code="BASE_DEPLOYMENT_CONFLICT" if conflict else "BASE_DEPLOYMENT_INVALID",
            ),
        ) from exc


@router.delete("/user-base-assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_user_base_assignment(
    assignment_id: str,
    payload: schemas.UserBaseAssignmentCancel,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _effective_amo_id(current_user)
    item = db.query(models.UserBaseAssignment).filter(
        models.UserBaseAssignment.id == assignment_id,
        models.UserBaseAssignment.amo_id == amo_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Base assignment not found")
    _require(
        db,
        current_user,
        workforce_permissions.PermissionCode.WORKFORCE_DEPLOYMENTS_MANAGE,
        base_station_id=item.base_station_id,
    )
    try:
        services.cancel_future_user_base_assignment(
            db,
            amo_id=amo_id,
            assignment=item,
            actor_user_id=current_user.id,
            payload=payload,
        )
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except RuntimeError as exc:
        db.rollback()
        if str(exc).startswith("USER_BASE_ASSIGNMENT_REVISION_CONFLICT"):
            raise HTTPException(
                status_code=409,
                detail=_conflict_detail(
                    "This deployment was changed by another user. Reload before cancelling.",
                    error_code="BASE_DEPLOYMENT_REVISION_CONFLICT",
                ),
            ) from exc
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=_conflict_detail(str(exc), error_code="BASE_DEPLOYMENT_CANCEL_INVALID"),
        ) from exc


@router.get("/availability", response_model=List[schemas.AvailabilityRead])
def list_availability(
    user_id: Optional[str] = Query(default=None),
    active_at: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    can_view_all = _has(db, current_user, workforce_permissions.PermissionCode.WORKFORCE_DEPLOYMENTS_VIEW)
    if user_id and user_id != current_user.id and not can_view_all:
        _require(db, current_user, workforce_permissions.PermissionCode.WORKFORCE_DEPLOYMENTS_VIEW)
    if not can_view_all:
        user_id = current_user.id
    return services.list_availability(db, amo_id=_effective_amo_id(current_user), user_id=user_id, active_at=active_at)


@router.post("/availability", response_model=schemas.AvailabilityRead, status_code=status.HTTP_201_CREATED)
def create_availability(
    payload: schemas.AvailabilityCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.WORKFORCE_DEPLOYMENTS_MANAGE)
    try:
        item = services.create_availability(
            db,
            amo_id=_effective_amo_id(current_user),
            actor_user_id=current_user.id,
            payload=payload,
        )
        db.commit()
        db.refresh(item)
        return item
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
