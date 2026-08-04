from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import AccountRole, User

from ...database import get_db
from ...entitlements import require_module
from ...security import get_current_active_user, require_roles
from . import package_services
from .package_schemas import (
    WorkPackageAttachOrder,
    WorkPackageCreate,
    WorkPackageRead,
    WorkPackageReadinessRead,
    WorkPackageStatusUpdate,
    WorkPackageUpdate,
)

router = APIRouter(
    prefix="/work-packages",
    tags=["work_packages"],
    dependencies=[Depends(require_module("work"))],
)

PACKAGE_EDITOR_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
    AccountRole.PRODUCTION_ENGINEER,
)


def _refresh_package_links(db: Session, package) -> None:
    db.flush()
    db.expire(package, ["order_links"])
    package_services.calculate_readiness(db, package=package)


@router.get("", response_model=list[WorkPackageRead])
@router.get("/", response_model=list[WorkPackageRead], include_in_schema=False)
def list_work_packages(
    aircraft_serial_number: str | None = Query(None, max_length=50),
    status_filter: str | None = Query(None, max_length=24),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return package_services.list_packages(
        db,
        amo_id=current_user.effective_amo_id,
        aircraft_serial_number=aircraft_serial_number,
        status_filter=status_filter,
    )


@router.get("/{package_id}", response_model=WorkPackageRead)
def get_work_package(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    package = package_services._get_package(
        db,
        amo_id=current_user.effective_amo_id,
        package_id=package_id,
    )
    return package_services.package_read(package)


@router.post(
    "",
    response_model=WorkPackageRead,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/",
    response_model=WorkPackageRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_work_package(
    payload: WorkPackageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*PACKAGE_EDITOR_ROLES)),
):
    effective_payload = payload
    if not payload.package_ref:
        effective_payload = payload.model_copy(
            update={
                "package_ref": f"WP-{datetime.now(UTC):%Y%m%d}-{uuid4().hex[:8].upper()}"
            }
        )
    try:
        package = package_services.create_package(
            db,
            amo_id=current_user.effective_amo_id,
            payload=effective_payload,
            actor=current_user,
        )
        _refresh_package_links(db, package)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(package)
    return package_services.package_read(package)


@router.patch("/{package_id}", response_model=WorkPackageRead)
def update_work_package(
    package_id: int,
    payload: WorkPackageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*PACKAGE_EDITOR_ROLES)),
):
    package = package_services._get_package(
        db,
        amo_id=current_user.effective_amo_id,
        package_id=package_id,
    )
    package_services.update_package(
        db,
        package=package,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(package)
    return package_services.package_read(package)


@router.post("/{package_id}/orders", response_model=WorkPackageRead)
def attach_work_order(
    package_id: int,
    payload: WorkPackageAttachOrder,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*PACKAGE_EDITOR_ROLES)),
):
    package = package_services._get_package(
        db,
        amo_id=current_user.effective_amo_id,
        package_id=package_id,
    )
    if package.status not in {"DRAFT", "REVIEW"}:
        raise HTTPException(status_code=409, detail="Only draft or review packages can accept work orders")
    package_services.attach_order(
        db,
        package=package,
        payload=payload,
        actor=current_user,
    )
    _refresh_package_links(db, package)
    db.commit()
    db.refresh(package)
    return package_services.package_read(package)


@router.get("/{package_id}/readiness", response_model=WorkPackageReadinessRead)
def get_work_package_readiness(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    package = package_services._get_package(
        db,
        amo_id=current_user.effective_amo_id,
        package_id=package_id,
    )
    db.expire(package, ["order_links"])
    readiness = package_services.calculate_readiness(db, package=package)
    db.commit()
    return readiness


@router.post("/{package_id}/status", response_model=WorkPackageRead)
def update_work_package_status(
    package_id: int,
    payload: WorkPackageStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*PACKAGE_EDITOR_ROLES)),
):
    package = package_services._get_package(
        db,
        amo_id=current_user.effective_amo_id,
        package_id=package_id,
    )
    db.expire(package, ["order_links"])
    package_services.change_status(
        db,
        package=package,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(package)
    return package_services.package_read(package)
