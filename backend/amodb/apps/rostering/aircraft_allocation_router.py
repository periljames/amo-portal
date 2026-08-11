from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..fleet import models as fleet_models
from ..workforce import permissions as workforce_permissions
from . import common, models
from .aircraft_allocation import RosterAircraftAllocation, RosterAircraftAllocationType

router = APIRouter(prefix="/rostering", tags=["rostering-aircraft-allocation"])


class AircraftAllocationCreate(BaseModel):
    aircraft_serial_number: str = Field(min_length=1, max_length=50)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    allocation_type: RosterAircraftAllocationType = RosterAircraftAllocationType.FLIGHT_ENGINEERING
    notes: Optional[str] = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_window(self):
        if self.starts_at is not None and self.starts_at.tzinfo is None:
            raise ValueError("starts_at must be timezone-aware")
        if self.ends_at is not None and self.ends_at.tzinfo is None:
            raise ValueError("ends_at must be timezone-aware")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class AircraftAllocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    roster_assignment_id: str
    aircraft_serial_number: str
    aircraft_registration: str
    aircraft_display_code: str
    starts_at: datetime
    ends_at: datetime
    allocation_type: RosterAircraftAllocationType
    notes: Optional[str] = None
    can_delete: bool


def _amo(user: account_models.User) -> str:
    return common.effective_amo_id(user)


def _assignment_or_404(db: Session, *, amo_id: str, assignment_id: str) -> models.RosterAssignment:
    row = common.get_assignment(db, amo_id=amo_id, assignment_id=assignment_id)
    if not row:
        raise HTTPException(status_code=404, detail="Roster assignment not found")
    return row


def _require_view(db: Session, user: account_models.User, assignment: models.RosterAssignment) -> None:
    workforce_permissions.require_permission(
        db,
        user=user,
        permission=workforce_permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT,
        department_id=assignment.department_id,
        base_station_id=assignment.base_station_id,
    )


def _require_edit(db: Session, user: account_models.User, assignment: models.RosterAssignment) -> None:
    workforce_permissions.require_permission(
        db,
        user=user,
        permission=workforce_permissions.PermissionCode.ROSTER_EDIT,
        department_id=assignment.department_id,
        base_station_id=assignment.base_station_id,
    )
    version = assignment.version
    if not version or version.status != models.RosterVersionStatus.DRAFT:
        raise HTTPException(
            status_code=409,
            detail="Aircraft allocations can only be changed on a draft roster version. Amend the published roster instead of mutating history.",
        )


def _aircraft_or_404(
    db: Session,
    *,
    amo_id: str,
    serial_number: str,
    active_only: bool,
) -> fleet_models.Aircraft:
    query = db.query(fleet_models.Aircraft).filter(
        fleet_models.Aircraft.amo_id == amo_id,
        fleet_models.Aircraft.serial_number == serial_number,
    )
    if active_only:
        query = query.filter(fleet_models.Aircraft.is_active.is_(True))
    row = query.first()
    if not row:
        raise HTTPException(status_code=404, detail="Aircraft not found in AMO fleet scope")
    return row


def _serialize(
    row: RosterAircraftAllocation,
    aircraft: fleet_models.Aircraft,
    *,
    can_delete: bool,
) -> AircraftAllocationRead:
    display_code = str(aircraft.internal_aircraft_identifier or aircraft.registration)
    return AircraftAllocationRead(
        id=row.id,
        roster_assignment_id=row.roster_assignment_id,
        aircraft_serial_number=row.aircraft_serial_number,
        aircraft_registration=aircraft.registration,
        aircraft_display_code=display_code,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        allocation_type=row.allocation_type,
        notes=row.notes,
        can_delete=can_delete,
    )


@router.get(
    "/assignments/{assignment_id}/aircraft-allocations",
    response_model=list[AircraftAllocationRead],
)
def list_aircraft_allocations(
    assignment_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _amo(current_user)
    assignment = _assignment_or_404(db, amo_id=amo_id, assignment_id=assignment_id)
    _require_view(db, current_user, assignment)
    rows = (
        db.query(RosterAircraftAllocation)
        .filter(
            RosterAircraftAllocation.amo_id == amo_id,
            RosterAircraftAllocation.roster_assignment_id == assignment.id,
        )
        .order_by(RosterAircraftAllocation.starts_at.asc(), RosterAircraftAllocation.id.asc())
        .all()
    )
    aircraft_by_serial = {
        serial: _aircraft_or_404(db, amo_id=amo_id, serial_number=serial, active_only=False)
        for serial in sorted({row.aircraft_serial_number for row in rows})
    }
    can_delete = bool(assignment.version and assignment.version.status == models.RosterVersionStatus.DRAFT)
    return [_serialize(row, aircraft_by_serial[row.aircraft_serial_number], can_delete=can_delete) for row in rows]


@router.post(
    "/assignments/{assignment_id}/aircraft-allocations",
    response_model=AircraftAllocationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_aircraft_allocation(
    assignment_id: str,
    payload: AircraftAllocationCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _amo(current_user)
    assignment = _assignment_or_404(db, amo_id=amo_id, assignment_id=assignment_id)
    _require_edit(db, current_user, assignment)
    aircraft = _aircraft_or_404(
        db,
        amo_id=amo_id,
        serial_number=payload.aircraft_serial_number,
        active_only=True,
    )
    starts_at = payload.starts_at or assignment.starts_at
    ends_at = payload.ends_at or assignment.ends_at
    if starts_at < assignment.starts_at or ends_at > assignment.ends_at or ends_at <= starts_at:
        raise HTTPException(
            status_code=400,
            detail="Aircraft allocation must remain inside the roster assignment time window.",
        )
    duplicate = (
        db.query(RosterAircraftAllocation.id)
        .filter(
            RosterAircraftAllocation.amo_id == amo_id,
            RosterAircraftAllocation.roster_assignment_id == assignment.id,
            RosterAircraftAllocation.aircraft_serial_number == aircraft.serial_number,
            RosterAircraftAllocation.starts_at == starts_at,
            RosterAircraftAllocation.ends_at == ends_at,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="This aircraft allocation already exists")
    row = RosterAircraftAllocation(
        amo_id=amo_id,
        roster_assignment_id=assignment.id,
        aircraft_serial_number=aircraft.serial_number,
        starts_at=starts_at,
        ends_at=ends_at,
        allocation_type=payload.allocation_type,
        notes=payload.notes,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=current_user.id,
        entity_type="RosterAircraftAllocation",
        entity_id=row.id,
        action="create",
        after={
            "roster_assignment_id": assignment.id,
            "aircraft_serial_number": aircraft.serial_number,
            "aircraft_registration": aircraft.registration,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "allocation_type": payload.allocation_type.value,
        },
        critical=True,
    )
    db.commit()
    db.refresh(row)
    return _serialize(row, aircraft, can_delete=True)


@router.delete(
    "/assignments/{assignment_id}/aircraft-allocations/{allocation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_aircraft_allocation(
    assignment_id: str,
    allocation_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _amo(current_user)
    assignment = _assignment_or_404(db, amo_id=amo_id, assignment_id=assignment_id)
    _require_edit(db, current_user, assignment)
    row = (
        db.query(RosterAircraftAllocation)
        .filter(
            RosterAircraftAllocation.amo_id == amo_id,
            RosterAircraftAllocation.id == allocation_id,
            RosterAircraftAllocation.roster_assignment_id == assignment.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Aircraft allocation not found")
    before = {
        "aircraft_serial_number": row.aircraft_serial_number,
        "starts_at": row.starts_at.isoformat(),
        "ends_at": row.ends_at.isoformat(),
        "allocation_type": str(getattr(row.allocation_type, "value", row.allocation_type)),
    }
    db.delete(row)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=current_user.id,
        entity_type="RosterAircraftAllocation",
        entity_id=allocation_id,
        action="delete_draft",
        before=before,
        critical=True,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
