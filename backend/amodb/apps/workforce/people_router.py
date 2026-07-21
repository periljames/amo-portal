# backend/amodb/apps/workforce/people_router.py
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..foundations import models as foundation_models
from . import models, permissions, services

router = APIRouter(prefix="/workforce", tags=["workforce"])


class WorkforcePersonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    staff_code: str
    full_name: str
    email: str
    role: str
    position_title: Optional[str] = None
    department_id: Optional[str] = None
    department_code: Optional[str] = None
    department_name: Optional[str] = None
    primary_base_station_id: Optional[str] = None
    primary_base_code: Optional[str] = None
    employment_status: Optional[str] = None
    contract_type: Optional[str] = None
    standard_daily_minutes: Optional[int] = None
    standard_weekly_minutes: Optional[int] = None
    overtime_eligible: bool = False
    night_shift_eligible: bool = False
    standby_eligible: bool = False
    licence_number: Optional[str] = None
    licence_expires_on: Optional[date] = None
    authorisation_count: int = 0
    active_authorisation_count: int = 0
    has_active_contract: bool = False
    is_active: bool


def _value(value) -> Optional[str]:
    if value is None:
        return None
    return str(getattr(value, "value", value))


@router.get("/people", response_model=list[WorkforcePersonRead])
def list_workforce_people(
    search: Optional[str] = Query(default=None, max_length=255),
    department_id: Optional[str] = Query(default=None),
    base_station_id: Optional[str] = Query(default=None),
    active_only: bool = Query(default=True),
    roster_eligible_only: bool = Query(default=True),
    limit: int = Query(default=500, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    permissions.require_permission(
        db,
        user=current_user,
        permission=permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT,
        department_id=department_id,
        base_station_id=base_station_id,
    )
    amo_id = services.effective_amo_id(current_user)
    today = date.today()

    query = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.is_system_account.is_(False),
    )
    if active_only:
        query = query.filter(account_models.User.is_active.is_(True))
    if department_id:
        query = query.filter(account_models.User.department_id == department_id)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(
            account_models.User.full_name.ilike(term),
            account_models.User.staff_code.ilike(term),
            account_models.User.email.ilike(term),
            account_models.User.position_title.ilike(term),
        ))
    users = query.order_by(account_models.User.full_name.asc(), account_models.User.staff_code.asc()).limit(limit).all()
    user_ids = [user.id for user in users]

    contracts = db.query(models.EmploymentContract).filter(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.user_id.in_(user_ids or ["__none__"]),
        models.EmploymentContract.employment_status == models.EmploymentStatus.ACTIVE,
        models.EmploymentContract.effective_from <= today,
        or_(models.EmploymentContract.effective_to.is_(None), models.EmploymentContract.effective_to >= today),
    ).order_by(models.EmploymentContract.effective_from.desc()).all()
    contract_by_user: dict[str, models.EmploymentContract] = {}
    for contract in contracts:
        contract_by_user.setdefault(contract.user_id, contract)

    if roster_eligible_only:
        users = [user for user in users if user.id in contract_by_user]
        user_ids = [user.id for user in users]

    base_ids = {contract.primary_base_station_id for contract in contract_by_user.values() if contract.primary_base_station_id}
    bases = {
        row.id: row
        for row in db.query(foundation_models.BaseStation).filter(
            foundation_models.BaseStation.amo_id == amo_id,
            foundation_models.BaseStation.id.in_(base_ids or ["__none__"]),
        ).all()
    }
    if base_station_id:
        users = [user for user in users if getattr(contract_by_user.get(user.id), "primary_base_station_id", None) == base_station_id]
        user_ids = [user.id for user in users]

    authorisations = db.query(account_models.UserAuthorisation).filter(
        account_models.UserAuthorisation.user_id.in_(user_ids or ["__none__"]),
    ).all()
    auth_counts: dict[str, tuple[int, int]] = {}
    grouped: dict[str, list[account_models.UserAuthorisation]] = {}
    for authorisation in authorisations:
        grouped.setdefault(authorisation.user_id, []).append(authorisation)
    for user_id, rows in grouped.items():
        auth_counts[user_id] = (len(rows), sum(1 for row in rows if row.is_currently_valid(today)))

    output: list[WorkforcePersonRead] = []
    for user in users:
        contract = contract_by_user.get(user.id)
        base = bases.get(getattr(contract, "primary_base_station_id", None))
        total_auth, active_auth = auth_counts.get(user.id, (0, 0))
        output.append(WorkforcePersonRead(
            user_id=user.id,
            staff_code=user.staff_code,
            full_name=user.full_name,
            email=user.email,
            role=_value(user.role) or "",
            position_title=user.position_title,
            department_id=user.department_id,
            department_code=getattr(user.department, "code", None),
            department_name=getattr(user.department, "name", None),
            primary_base_station_id=getattr(contract, "primary_base_station_id", None),
            primary_base_code=getattr(base, "code", None),
            employment_status=_value(getattr(contract, "employment_status", None)),
            contract_type=_value(getattr(contract, "contract_type", None)),
            standard_daily_minutes=getattr(contract, "standard_daily_minutes", None),
            standard_weekly_minutes=getattr(contract, "standard_weekly_minutes", None),
            overtime_eligible=bool(getattr(contract, "overtime_eligible", False)),
            night_shift_eligible=bool(getattr(contract, "night_shift_eligible", False)),
            standby_eligible=bool(getattr(contract, "standby_eligible", False)),
            licence_number=user.licence_number,
            licence_expires_on=user.licence_expires_on,
            authorisation_count=total_auth,
            active_authorisation_count=active_auth,
            has_active_contract=contract is not None,
            is_active=user.is_active,
        ))
    return output
