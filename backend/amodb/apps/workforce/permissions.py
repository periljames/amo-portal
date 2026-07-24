# backend/amodb/apps/workforce/permissions.py
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..accounts import models as account_models
from . import models


class PermissionCode(str, Enum):
    ROSTER_VIEW_OWN = "roster.view_own"
    ROSTER_VIEW_DEPARTMENT = "roster.view_department"
    ROSTER_VIEW_ALL = "roster.view_all"
    ROSTER_CREATE = "roster.create"
    ROSTER_EDIT = "roster.edit"
    ROSTER_DELETE_DRAFT_ASSIGNMENT = "roster.delete_draft_assignment"
    ROSTER_VALIDATE = "roster.validate"
    ROSTER_SUBMIT = "roster.submit"
    ROSTER_APPROVE = "roster.approve"
    ROSTER_PUBLISH = "roster.publish"
    ROSTER_AMEND_PUBLISHED = "roster.amend_published"
    ROSTER_OVERRIDE_WARNING = "roster.override_warning"
    ROSTER_OVERRIDE_BLOCKER = "roster.override_blocker"
    ROSTER_MANAGE_RULES = "roster.manage_rules"
    ROSTER_MANAGE_APPROVAL_AUTHORITIES = "roster.manage_approval_authorities"
    ROSTER_MANAGE_SHIFT_TEMPLATES = "roster.manage_shift_templates"
    ROSTER_MANAGE_PATTERNS = "roster.manage_patterns"
    ROSTER_ALLOCATE_WORK = "roster.allocate_work"
    LEAVE_REQUEST = "leave.request"
    LEAVE_REVIEW = "leave.review"
    LEAVE_APPROVE = "leave.approve"
    LEAVE_MANAGE_BALANCES = "leave.manage_balances"
    ATTENDANCE_VIEW_OWN = "attendance.view_own"
    ATTENDANCE_MANAGE = "attendance.manage"
    ATTENDANCE_APPROVE = "attendance.approve"
    TIMESHEET_VIEW_OWN = "timesheet.view_own"
    TIMESHEET_APPROVE = "timesheet.approve"
    OVERTIME_REQUEST = "overtime.request"
    OVERTIME_APPROVE = "overtime.approve"
    PAYROLL_EXPORT = "payroll.export"
    WORKFORCE_MANAGE_CONTRACTS = "workforce.manage_contracts"
    WORKFORCE_VIEW_SENSITIVE = "workforce.view_sensitive"


ALL_PERMISSIONS = {code.value for code in PermissionCode}

EMPLOYEE = {
    PermissionCode.ROSTER_VIEW_OWN.value,
    PermissionCode.LEAVE_REQUEST.value,
    PermissionCode.ATTENDANCE_VIEW_OWN.value,
    PermissionCode.TIMESHEET_VIEW_OWN.value,
    PermissionCode.OVERTIME_REQUEST.value,
}

PLANNER = EMPLOYEE | {
    PermissionCode.ROSTER_VIEW_DEPARTMENT.value,
    PermissionCode.ROSTER_VIEW_ALL.value,
    PermissionCode.ROSTER_CREATE.value,
    PermissionCode.ROSTER_EDIT.value,
    PermissionCode.ROSTER_DELETE_DRAFT_ASSIGNMENT.value,
    PermissionCode.ROSTER_VALIDATE.value,
    PermissionCode.ROSTER_SUBMIT.value,
    PermissionCode.ROSTER_MANAGE_SHIFT_TEMPLATES.value,
    PermissionCode.ROSTER_MANAGE_PATTERNS.value,
    PermissionCode.ROSTER_ALLOCATE_WORK.value,
}

SUPERVISOR = EMPLOYEE | {
    PermissionCode.ROSTER_VIEW_DEPARTMENT.value,
    PermissionCode.ROSTER_CREATE.value,
    PermissionCode.ROSTER_EDIT.value,
    PermissionCode.ROSTER_DELETE_DRAFT_ASSIGNMENT.value,
    PermissionCode.ROSTER_VALIDATE.value,
    PermissionCode.ROSTER_SUBMIT.value,
    PermissionCode.ROSTER_ALLOCATE_WORK.value,
    PermissionCode.LEAVE_REVIEW.value,
    PermissionCode.ATTENDANCE_MANAGE.value,
    PermissionCode.TIMESHEET_APPROVE.value,
    PermissionCode.OVERTIME_APPROVE.value,
}

DEPARTMENT_HEAD = SUPERVISOR | {
    PermissionCode.ROSTER_APPROVE.value,
    PermissionCode.ROSTER_AMEND_PUBLISHED.value,
}

BASE_MANAGER = DEPARTMENT_HEAD | {
    PermissionCode.ROSTER_VIEW_ALL.value,
    PermissionCode.ROSTER_PUBLISH.value,
    PermissionCode.ROSTER_MANAGE_APPROVAL_AUTHORITIES.value,
}


QUALITY = EMPLOYEE | {
    PermissionCode.ROSTER_VIEW_ALL.value,
    PermissionCode.ROSTER_VALIDATE.value,
    PermissionCode.ROSTER_OVERRIDE_WARNING.value,
    PermissionCode.ROSTER_OVERRIDE_BLOCKER.value,
    PermissionCode.ROSTER_MANAGE_RULES.value,
}


HR = EMPLOYEE | {
    PermissionCode.ROSTER_VIEW_ALL.value,
    PermissionCode.ROSTER_VALIDATE.value,
    PermissionCode.ROSTER_AMEND_PUBLISHED.value,
    PermissionCode.LEAVE_REVIEW.value,
    PermissionCode.LEAVE_APPROVE.value,
    PermissionCode.LEAVE_MANAGE_BALANCES.value,
    PermissionCode.ATTENDANCE_MANAGE.value,
    PermissionCode.ATTENDANCE_APPROVE.value,
    PermissionCode.TIMESHEET_APPROVE.value,
    PermissionCode.OVERTIME_APPROVE.value,
    PermissionCode.WORKFORCE_MANAGE_CONTRACTS.value,
    PermissionCode.WORKFORCE_VIEW_SENSITIVE.value,
}


PAYROLL = EMPLOYEE | {
    PermissionCode.TIMESHEET_APPROVE.value,
    PermissionCode.PAYROLL_EXPORT.value,
    PermissionCode.WORKFORCE_VIEW_SENSITIVE.value,
}


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "SUPERUSER": ALL_PERMISSIONS,
    "AMO_ADMIN": ALL_PERMISSIONS,
    "PLANNING_ENGINEER": PLANNER,
    "ROSTER_PLANNER": PLANNER,
    "PRODUCTION_ENGINEER": SUPERVISOR,
    "DEPARTMENT_SUPERVISOR": SUPERVISOR,
    "DEPARTMENT_HEAD": DEPARTMENT_HEAD,
    "BASE_MANAGER": BASE_MANAGER,
    "LINE_MANAGER": DEPARTMENT_HEAD,
    "QUALITY_MANAGER": QUALITY,
    "QUALITY_INSPECTOR": QUALITY - {PermissionCode.ROSTER_PUBLISH.value, PermissionCode.ROSTER_OVERRIDE_BLOCKER.value},
    "AUDITOR": {PermissionCode.ROSTER_VIEW_ALL.value, PermissionCode.ROSTER_VALIDATE.value},
    "HR_OFFICER": HR - {PermissionCode.ROSTER_PUBLISH.value, PermissionCode.PAYROLL_EXPORT.value},
    "HR_MANAGER": HR | {PermissionCode.PAYROLL_EXPORT.value},
    "PAYROLL_OFFICER": PAYROLL,
    "CERTIFYING_ENGINEER": EMPLOYEE,
    "CERTIFYING_TECHNICIAN": EMPLOYEE,
    "TECHNICIAN": EMPLOYEE,
    "SAFETY_MANAGER": EMPLOYEE | {PermissionCode.ROSTER_VIEW_ALL.value, PermissionCode.ROSTER_VALIDATE.value},
    "STORES": EMPLOYEE,
    "STORES_MANAGER": EMPLOYEE,
    "STOREKEEPER": EMPLOYEE,
    "PROCUREMENT_OFFICER": EMPLOYEE,
    "FINANCE_MANAGER": PAYROLL,
    "ACCOUNTS_OFFICER": PAYROLL,
    "VIEW_ONLY": {PermissionCode.ROSTER_VIEW_OWN.value},
}


def _role_value(user: account_models.User) -> str:
    return str(getattr(getattr(user, "role", None), "value", getattr(user, "role", "")))


def _derived_role(user: account_models.User) -> Optional[str]:
    """Support HR/planner titles without mutating the legacy AccountRole enum.

    Explicit permission grants remain authoritative.  This compatibility layer
    lets existing user management records participate immediately and can be
    removed after AccountRole is migrated to database-backed roles.
    """

    title = str(getattr(user, "position_title", "") or "").lower()
    department = str(getattr(getattr(user, "department", None), "code", "") or "").lower()
    if "human resource" in title or title.startswith("hr ") or department in {"hr", "human-resources", "human_resources"}:
        return "HR_MANAGER" if "manager" in title or "head" in title else "HR_OFFICER"
    if "payroll" in title:
        return "PAYROLL_OFFICER"
    if "roster" in title or "duty planner" in title:
        return "ROSTER_PLANNER"
    if "base manager" in title:
        return "BASE_MANAGER"
    if "department head" in title or title.startswith("head of ") or "department manager" in title or "line manager" in title:
        return "DEPARTMENT_HEAD"
    if "supervisor" in title or "shift lead" in title:
        return "DEPARTMENT_SUPERVISOR"
    return None


def default_permissions_for(user: account_models.User) -> set[str]:
    if not user or getattr(user, "is_system_account", False):
        return set()
    if getattr(user, "is_superuser", False) or getattr(user, "is_amo_admin", False):
        return set(ALL_PERMISSIONS)
    permissions = set(ROLE_PERMISSIONS.get(_role_value(user), EMPLOYEE))
    derived = _derived_role(user)
    if derived:
        permissions |= ROLE_PERMISSIONS.get(derived, set())
    return permissions


def _active_grants(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    permission_code: str,
    department_id: Optional[str] = None,
    base_station_id: Optional[str] = None,
) -> list[models.WorkforcePermissionGrant]:
    today = date.today()
    query = db.query(models.WorkforcePermissionGrant).filter(
        models.WorkforcePermissionGrant.amo_id == amo_id,
        models.WorkforcePermissionGrant.user_id == user_id,
        models.WorkforcePermissionGrant.permission_code == permission_code,
        or_(models.WorkforcePermissionGrant.effective_from.is_(None), models.WorkforcePermissionGrant.effective_from <= today),
        or_(models.WorkforcePermissionGrant.effective_to.is_(None), models.WorkforcePermissionGrant.effective_to >= today),
    )
    rows = query.order_by(models.WorkforcePermissionGrant.created_at.asc()).all()
    return [
        row
        for row in rows
        if (row.department_id is None or row.department_id == department_id)
        and (row.base_station_id is None or row.base_station_id == base_station_id)
    ]


def has_permission(
    db: Session,
    *,
    user: account_models.User,
    permission: PermissionCode | str,
    department_id: Optional[str] = None,
    base_station_id: Optional[str] = None,
) -> bool:
    if not user or getattr(user, "is_system_account", False):
        return False
    code = permission.value if isinstance(permission, PermissionCode) else str(permission)
    amo_id = getattr(user, "effective_amo_id", None) or user.amo_id
    explicit = _active_grants(
        db,
        amo_id=amo_id,
        user_id=user.id,
        permission_code=code,
        department_id=department_id,
        base_station_id=base_station_id,
    )
    if any(row.effect == models.PermissionEffect.DENY for row in explicit):
        return False
    if any(row.effect == models.PermissionEffect.GRANT for row in explicit):
        return True
    return code in default_permissions_for(user)


def require_permission(
    db: Session,
    *,
    user: account_models.User,
    permission: PermissionCode | str,
    department_id: Optional[str] = None,
    base_station_id: Optional[str] = None,
) -> None:
    code = permission.value if isinstance(permission, PermissionCode) else str(permission)
    if not has_permission(
        db,
        user=user,
        permission=code,
        department_id=department_id,
        base_station_id=base_station_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "detail": "You do not have permission to perform this workforce action.",
                "error_code": "WORKFORCE_PERMISSION_DENIED",
                "field_errors": {},
                "conflicts": [{"permission": code}],
                "retryable": False,
            },
        )


def permissions_for_user(db: Session, *, user: account_models.User) -> list[str]:
    permissions = default_permissions_for(user)
    amo_id = getattr(user, "effective_amo_id", None) or user.amo_id
    rows = db.query(models.WorkforcePermissionGrant).filter(
        models.WorkforcePermissionGrant.amo_id == amo_id,
        models.WorkforcePermissionGrant.user_id == user.id,
    ).all()
    for row in rows:
        if row.effect == models.PermissionEffect.DENY:
            permissions.discard(row.permission_code)
        else:
            permissions.add(row.permission_code)
    return sorted(permissions)


def any_permission(db: Session, *, user: account_models.User, permissions: Iterable[PermissionCode | str]) -> bool:
    return any(has_permission(db, user=user, permission=permission) for permission in permissions)
