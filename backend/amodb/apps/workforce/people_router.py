# backend/amodb/apps/workforce/people_router.py
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, case, func, or_
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


class WorkforceRosterPersonRead(BaseModel):
    user_id: str
    staff_code: str
    full_name: str
    role: str
    position_title: Optional[str] = None
    department_id: Optional[str] = None
    department_code: Optional[str] = None
    department_name: Optional[str] = None
    primary_base_station_id: Optional[str] = None
    primary_base_code: Optional[str] = None
    standard_daily_minutes: Optional[int] = None
    standard_weekly_minutes: Optional[int] = None
    overtime_eligible: bool = False
    night_shift_eligible: bool = False
    standby_eligible: bool = False
    active_authorisation_count: int = 0
    has_active_contract: bool = False
    is_active: bool


class WorkforceDepartmentOption(BaseModel):
    id: str
    code: str
    name: str


class WorkforceRosterPeoplePage(BaseModel):
    items: list[WorkforceRosterPersonRead] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 100
    pages: int = 0
    has_more: bool = False
    departments: list[WorkforceDepartmentOption] = Field(default_factory=list)


def _value(value) -> Optional[str]:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _require_people_access(
    db: Session,
    *,
    current_user: account_models.User,
    department_id: Optional[str],
    base_station_id: Optional[str],
) -> str:
    permissions.require_permission(
        db,
        user=current_user,
        permission=permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT,
        department_id=department_id,
        base_station_id=base_station_id,
    )
    return services.effective_amo_id(current_user)


def _people_query(
    db: Session,
    *,
    amo_id: str,
    today: date,
    search: Optional[str],
    department_id: Optional[str],
    base_station_id: Optional[str],
    active_only: bool,
    roster_eligible_only: bool,
):
    contract_dates = (
        db.query(
            models.EmploymentContract.user_id.label("user_id"),
            func.max(models.EmploymentContract.effective_from).label("effective_from"),
        )
        .filter(
            models.EmploymentContract.amo_id == amo_id,
            models.EmploymentContract.employment_status == models.EmploymentStatus.ACTIVE,
            models.EmploymentContract.effective_from <= today,
            or_(
                models.EmploymentContract.effective_to.is_(None),
                models.EmploymentContract.effective_to >= today,
            ),
        )
        .group_by(models.EmploymentContract.user_id)
        .subquery()
    )

    query = (
        db.query(
            account_models.User,
            models.EmploymentContract,
            account_models.Department,
            foundation_models.BaseStation,
        )
        .select_from(account_models.User)
        .outerjoin(contract_dates, contract_dates.c.user_id == account_models.User.id)
        .outerjoin(
            models.EmploymentContract,
            and_(
                models.EmploymentContract.amo_id == amo_id,
                models.EmploymentContract.user_id == account_models.User.id,
                models.EmploymentContract.effective_from == contract_dates.c.effective_from,
            ),
        )
        .outerjoin(
            account_models.Department,
            and_(
                account_models.Department.id == account_models.User.department_id,
                account_models.Department.amo_id == amo_id,
            ),
        )
        .outerjoin(
            foundation_models.BaseStation,
            and_(
                foundation_models.BaseStation.id == models.EmploymentContract.primary_base_station_id,
                foundation_models.BaseStation.amo_id == amo_id,
            ),
        )
        .filter(
            account_models.User.amo_id == amo_id,
            account_models.User.is_system_account.is_(False),
        )
    )

    if active_only:
        query = query.filter(account_models.User.is_active.is_(True))
    if roster_eligible_only:
        query = query.filter(models.EmploymentContract.id.isnot(None))
    if department_id:
        query = query.filter(account_models.User.department_id == department_id)
    if base_station_id:
        query = query.filter(models.EmploymentContract.primary_base_station_id == base_station_id)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                account_models.User.full_name.ilike(term),
                account_models.User.staff_code.ilike(term),
                account_models.User.email.ilike(term),
                account_models.User.position_title.ilike(term),
            )
        )
    return query


def _authorisation_counts(
    db: Session,
    *,
    user_ids: list[str],
    today: date,
) -> dict[str, tuple[int, int]]:
    if not user_ids:
        return {}
    valid_condition = and_(
        account_models.UserAuthorisation.revoked_at.is_(None),
        account_models.UserAuthorisation.effective_from <= today,
        or_(
            account_models.UserAuthorisation.expires_at.is_(None),
            account_models.UserAuthorisation.expires_at >= today,
        ),
    )
    rows = (
        db.query(
            account_models.UserAuthorisation.user_id,
            func.count(account_models.UserAuthorisation.id),
            func.coalesce(
                func.sum(case((valid_condition, 1), else_=0)),
                0,
            ),
        )
        .filter(account_models.UserAuthorisation.user_id.in_(user_ids))
        .group_by(account_models.UserAuthorisation.user_id)
        .all()
    )
    return {
        str(user_id): (int(total or 0), int(active or 0))
        for user_id, total, active in rows
    }


def _department_options(db: Session, *, amo_id: str) -> list[WorkforceDepartmentOption]:
    rows = (
        db.query(account_models.Department)
        .filter(
            account_models.Department.amo_id == amo_id,
            account_models.Department.is_active.is_(True),
        )
        .order_by(account_models.Department.sort_order.asc(), account_models.Department.name.asc())
        .all()
    )
    return [
        WorkforceDepartmentOption(id=str(row.id), code=row.code, name=row.name)
        for row in rows
    ]


def _roster_person(
    *,
    user: account_models.User,
    contract: Optional[models.EmploymentContract],
    department: Optional[account_models.Department],
    base: Optional[foundation_models.BaseStation],
    active_authorisations: int,
) -> WorkforceRosterPersonRead:
    return WorkforceRosterPersonRead(
        user_id=str(user.id),
        staff_code=user.staff_code,
        full_name=user.full_name,
        role=_value(user.role) or "",
        position_title=user.position_title,
        department_id=str(user.department_id) if user.department_id else None,
        department_code=getattr(department, "code", None),
        department_name=getattr(department, "name", None),
        primary_base_station_id=getattr(contract, "primary_base_station_id", None),
        primary_base_code=getattr(base, "code", None),
        standard_daily_minutes=getattr(contract, "standard_daily_minutes", None),
        standard_weekly_minutes=getattr(contract, "standard_weekly_minutes", None),
        overtime_eligible=bool(getattr(contract, "overtime_eligible", False)),
        night_shift_eligible=bool(getattr(contract, "night_shift_eligible", False)),
        standby_eligible=bool(getattr(contract, "standby_eligible", False)),
        active_authorisation_count=active_authorisations,
        has_active_contract=contract is not None,
        is_active=bool(user.is_active),
    )


@router.get("/roster-people", response_model=WorkforceRosterPeoplePage)
def list_roster_people_page(
    search: Optional[str] = Query(default=None, max_length=255),
    department_id: Optional[str] = Query(default=None),
    base_station_id: Optional[str] = Query(default=None),
    active_only: bool = Query(default=True),
    roster_eligible_only: bool = Query(default=True),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=25, le=250),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _require_people_access(
        db,
        current_user=current_user,
        department_id=department_id,
        base_station_id=base_station_id,
    )
    today = date.today()
    query = _people_query(
        db,
        amo_id=amo_id,
        today=today,
        search=search,
        department_id=department_id,
        base_station_id=base_station_id,
        active_only=active_only,
        roster_eligible_only=roster_eligible_only,
    )
    total = int(query.with_entities(func.count(account_models.User.id)).scalar() or 0)
    rows = (
        query.order_by(account_models.User.full_name.asc(), account_models.User.staff_code.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    user_ids = [str(user.id) for user, _, _, _ in rows]
    auth_counts = _authorisation_counts(db, user_ids=user_ids, today=today)
    items = [
        _roster_person(
            user=user,
            contract=contract,
            department=department,
            base=base,
            active_authorisations=auth_counts.get(str(user.id), (0, 0))[1],
        )
        for user, contract, department, base in rows
    ]
    pages = (total + page_size - 1) // page_size if total else 0
    return WorkforceRosterPeoplePage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        has_more=page < pages,
        departments=_department_options(db, amo_id=amo_id),
    )


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
    amo_id = _require_people_access(
        db,
        current_user=current_user,
        department_id=department_id,
        base_station_id=base_station_id,
    )
    today = date.today()
    rows = (
        _people_query(
            db,
            amo_id=amo_id,
            today=today,
            search=search,
            department_id=department_id,
            base_station_id=base_station_id,
            active_only=active_only,
            roster_eligible_only=roster_eligible_only,
        )
        .order_by(account_models.User.full_name.asc(), account_models.User.staff_code.asc())
        .limit(limit)
        .all()
    )
    user_ids = [str(user.id) for user, _, _, _ in rows]
    auth_counts = _authorisation_counts(db, user_ids=user_ids, today=today)

    output: list[WorkforcePersonRead] = []
    for user, contract, department, base in rows:
        total_auth, active_auth = auth_counts.get(str(user.id), (0, 0))
        output.append(
            WorkforcePersonRead(
                user_id=str(user.id),
                staff_code=user.staff_code,
                full_name=user.full_name,
                email=user.email,
                role=_value(user.role) or "",
                position_title=user.position_title,
                department_id=str(user.department_id) if user.department_id else None,
                department_code=getattr(department, "code", None),
                department_name=getattr(department, "name", None),
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
                is_active=bool(user.is_active),
            )
        )
    return output
