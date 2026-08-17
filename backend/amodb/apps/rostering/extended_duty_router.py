from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..workforce import permissions as workforce_permissions
from . import common, consent_service, extended_duty_service
from .extended_duty_models import RosterDutyExtension, RosterDutyExtensionStatus, RosterDutyExtensionType

router = APIRouter(prefix="/rostering/duty-extensions", tags=["rostering-duty-extensions"])


class DutyExtensionCreate(BaseModel):
    assignment_id: str = Field(min_length=1, max_length=36)
    proposed_extended_end: datetime
    aircraft_registration: str = Field(min_length=2, max_length=32)
    operational_reference: str = Field(min_length=2, max_length=255)
    work_order_reference: str | None = Field(default=None, max_length=255)
    reason: str = Field(min_length=5, max_length=4000)


class DutyExtensionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version_id: str
    assignment_id: str
    consent_id: str | None = None
    extension_type: RosterDutyExtensionType
    aircraft_registration: str
    operational_reference: str
    work_order_reference: str | None = None
    reason: str
    normal_duty_start: datetime
    original_planned_end: datetime
    proposed_extended_end: datetime
    continuous_duty_minutes: int
    required_recovery_rest_minutes: int
    recovery_rest_basis: str | None = None
    compliance_snapshot_json: dict
    fatigue_risk_json: dict
    status: RosterDutyExtensionStatus
    proposed_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


def _amo(user: account_models.User) -> str:
    return common.effective_amo_id(user)


def _workflow_error(exc: consent_service.RosterWorkflowError) -> HTTPException:
    status_code = 404 if exc.code == "ROSTER_ASSIGNMENT_NOT_FOUND" else 409
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.message, "details": exc.details},
    )


@router.get("", response_model=list[DutyExtensionRead])
def list_duty_extensions(
    version_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    workforce_permissions.require_permission(
        db,
        user=current_user,
        permission=workforce_permissions.PermissionCode.ROSTER_VIEW,
    )
    query = db.query(RosterDutyExtension).filter(RosterDutyExtension.amo_id == _amo(current_user))
    if version_id:
        version = common.get_version(db, amo_id=_amo(current_user), version_id=version_id)
        if version is None:
            raise HTTPException(status_code=404, detail={"code": "ROSTER_VERSION_NOT_FOUND"})
        query = query.filter(RosterDutyExtension.version_id == version_id)
    return query.order_by(RosterDutyExtension.created_at.desc()).all()


@router.post("", response_model=DutyExtensionRead, status_code=201)
def propose_duty_extension(
    payload: DutyExtensionCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _amo(current_user)
    assignment = common.get_assignment(db, amo_id=amo_id, assignment_id=payload.assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail={"code": "ROSTER_ASSIGNMENT_NOT_FOUND"})
    workforce_permissions.require_permission(
        db,
        user=current_user,
        permission=workforce_permissions.PermissionCode.ROSTER_EDIT,
        department_id=assignment.department_id,
        base_station_id=assignment.base_station_id,
    )
    try:
        row = extended_duty_service.propose_extension(
            db,
            amo_id=amo_id,
            assignment_id=payload.assignment_id,
            actor_user_id=current_user.id,
            proposed_extended_end=payload.proposed_extended_end,
            aircraft_registration=payload.aircraft_registration,
            operational_reference=payload.operational_reference,
            work_order_reference=payload.work_order_reference,
            reason=payload.reason,
        )
        db.commit()
        db.refresh(row)
        return row
    except consent_service.RosterWorkflowError as exc:
        db.rollback()
        raise _workflow_error(exc) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "ROSTER_DUTY_EXTENSION_INVALID", "message": str(exc)},
        ) from exc
