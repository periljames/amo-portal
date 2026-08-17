from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..workforce import permissions as workforce_permissions
from . import common, exemption_service
from .consent_models import RosterRegulatoryExemption

router = APIRouter(prefix="/rostering/regulatory-exemptions", tags=["rostering-regulatory-exemptions"])


class ExemptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    authority: str
    exemption_reference: str
    regulation_provision: str
    scope: str
    personnel_id: str | None = None
    role_applicability: str | None = None
    conditions_json: dict
    effective_date: date
    expiry_date: date
    supporting_document_id: str
    verified_by_user_id: str | None = None
    verified_at: datetime | None = None
    is_revoked: bool
    revoked_at: datetime | None = None
    revocation_reason: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ExemptionCreate(BaseModel):
    authority: str = Field(min_length=2, max_length=255)
    exemption_reference: str = Field(min_length=2, max_length=128)
    regulation_provision: str = Field(min_length=2, max_length=255)
    scope: str = Field(min_length=2, max_length=4000)
    personnel_id: str | None = None
    role_applicability: str | None = Field(default=None, max_length=128)
    conditions: dict = Field(default_factory=dict)
    effective_date: date
    expiry_date: date
    supporting_document_id: str = Field(min_length=1, max_length=36)


class ExemptionRevoke(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


def _amo(user: account_models.User) -> str:
    return common.effective_amo_id(user)


def _require_manage(db: Session, user: account_models.User) -> None:
    workforce_permissions.require_permission(
        db,
        user=user,
        permission=workforce_permissions.PermissionCode.ROSTER_MANAGE_RULES,
    )


def _row_or_404(db: Session, *, amo_id: str, exemption_id: str, lock: bool = False) -> RosterRegulatoryExemption:
    query = db.query(RosterRegulatoryExemption).filter(
        RosterRegulatoryExemption.amo_id == amo_id,
        RosterRegulatoryExemption.id == exemption_id,
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "ROSTER_REGULATORY_EXEMPTION_NOT_FOUND"})
    return row


@router.get("", response_model=list[ExemptionRead])
def list_exemptions(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manage(db, current_user)
    amo_id = _amo(current_user)
    return db.query(RosterRegulatoryExemption).filter(
        RosterRegulatoryExemption.amo_id == amo_id,
    ).order_by(RosterRegulatoryExemption.created_at.desc()).all()


@router.post("", response_model=ExemptionRead, status_code=201)
def create_exemption(
    payload: ExemptionCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manage(db, current_user)
    try:
        row = exemption_service.create_exemption(
            db,
            amo_id=_amo(current_user),
            actor_user_id=current_user.id,
            authority=payload.authority,
            exemption_reference=payload.exemption_reference,
            regulation_provision=payload.regulation_provision,
            scope=payload.scope,
            effective_date=payload.effective_date,
            expiry_date=payload.expiry_date,
            supporting_document_id=payload.supporting_document_id,
            personnel_id=payload.personnel_id,
            role_applicability=payload.role_applicability,
            conditions=payload.conditions,
        )
        db.commit()
        db.refresh(row)
        return row
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "ROSTER_REGULATORY_EXEMPTION_INVALID", "message": str(exc)},
        ) from exc


@router.post("/{exemption_id}/verify", response_model=ExemptionRead)
def verify_exemption(
    exemption_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manage(db, current_user)
    row = _row_or_404(db, amo_id=_amo(current_user), exemption_id=exemption_id, lock=True)
    try:
        row = exemption_service.verify_exemption(db, row=row, actor_user_id=current_user.id)
        db.commit()
        db.refresh(row)
        return row
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "ROSTER_REGULATORY_EXEMPTION_INVALID", "message": str(exc)}) from exc


@router.post("/{exemption_id}/revoke", response_model=ExemptionRead)
def revoke_exemption(
    exemption_id: str,
    payload: ExemptionRevoke,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manage(db, current_user)
    row = _row_or_404(db, amo_id=_amo(current_user), exemption_id=exemption_id, lock=True)
    row = exemption_service.revoke_exemption(
        db,
        row=row,
        actor_user_id=current_user.id,
        reason=payload.reason,
    )
    db.commit()
    db.refresh(row)
    return row
