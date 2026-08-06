"""Compact reference data for corporate-structure forms."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import require_admin

from . import models
from .router_admin import router


class OrganizationReferenceUser(BaseModel):
    id: str
    full_name: str
    staff_code: str
    email: str
    position_title: Optional[str] = None
    is_active: bool


class OrganizationReferenceGroup(BaseModel):
    id: str
    code: str
    name: str
    group_type: str


class OrganizationReferenceDepartment(BaseModel):
    id: str
    code: str
    name: str


class OrganizationReferenceData(BaseModel):
    users: list[OrganizationReferenceUser]
    groups: list[OrganizationReferenceGroup]
    departments: list[OrganizationReferenceDepartment]


def _target_amo_id(current_user: models.User, requested_amo_id: Optional[str]) -> str:
    return str(requested_amo_id if current_user.is_superuser and requested_amo_id else current_user.amo_id)


@router.get("/organization/reference-data", response_model=OrganizationReferenceData)
def organization_reference_data(
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    target = _target_amo_id(current_user, amo_id)
    users = db.query(models.User).filter(models.User.amo_id == target).order_by(models.User.full_name.asc()).all()
    groups = db.query(models.UserGroup).filter(
        models.UserGroup.amo_id == target,
        models.UserGroup.is_active.is_(True),
    ).order_by(models.UserGroup.name.asc()).all()
    departments = db.query(models.Department).filter(
        models.Department.amo_id == target,
        models.Department.is_active.is_(True),
    ).order_by(models.Department.sort_order.asc(), models.Department.name.asc()).all()
    return OrganizationReferenceData(
        users=[OrganizationReferenceUser(
            id=str(row.id), full_name=row.full_name, staff_code=row.staff_code,
            email=row.email, position_title=row.position_title, is_active=bool(row.is_active),
        ) for row in users],
        groups=[OrganizationReferenceGroup(
            id=str(row.id), code=row.code, name=row.name,
            group_type=str(getattr(row.group_type, "value", row.group_type)),
        ) for row in groups],
        departments=[OrganizationReferenceDepartment(id=str(row.id), code=row.code, name=row.name) for row in departments],
    )
