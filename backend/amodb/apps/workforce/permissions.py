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
    ROSTER_MANAGE_SHIFT_SEMANTICS = "roster.manage_shift_semantics"
    ROSTER_MANAGE_CONTROLLED_OUTPUT = "roster.manage_controlled_output"
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
    WORKFORCE_ASSIGN_PATTERNS = "workforce.assign_patterns"
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
    PermissionCode.WORKFORCE_ASSIGN_PATTERNS.value,
    PermissionCode.ROSTER_ALLOCATE_WORK.value,
}

# Supervisors operate only inside their concrete department/base scope. Version
# creation, tenant-wide validation and submission are planning functions; a
# supervisor can still edit/delete/allocate assignments in an authorized scope.
SUPERVISOR = EMPLOYEE | {
    PermissionCode.ROSTER_VIEW_DEPARTMENT.value,
    PermissionCode.ROSTER_EDIT.value,
    PermissionCode.ROSTER_DELETE_DRAFT_ASSIGNMENT.value,
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

ACCOUNTABLE_EXECUTIVE = EMPLOYEE | {
    PermissionCode.ROSTER_VIEW_ALL.value,
    PermissionCode.ROSTER_VALIDATE.value,
    PermissionCode.ROSTER_APPROVE.value,
    PermissionCode.ROSTER_PUBLISH.value,
    PermissionCode.ROSTER_AMEND_PUBLISHED.value,
    PermissionCode.ROSTER_MANAGE_APPROVAL_AUTHORITIES.value,
    PermissionCode.WORKFORCE_VIEW_SENSITIVE.value,
}

QUALITY = EMPLOYEE | {
    PermissionCode.ROSTER_VIEW_ALL.value,
    PermissionCode.ROSTER_VALIDATE.value,
    PermissionCode.ROSTER_OVERRIDE_WARNING.value,
    PermissionCode.ROSTER_OVERRIDE_BLOCKER.value,
    PermissionCode.ROSTER_MANAGE_RULES.value,
    PermissionCode.ROSTER_MANAGE_SHIFT_SEMANTICS.value,
    PermissionCode.ROSTER_MANAGE_CONTROLLED_OUTPUT.value,
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
    PermissionCode.WORKFORCE_ASSIGN_PATTERNS.value,
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
    "USER": EMPLOYEE,
    "ACCOUNTABLE_EXECUTIVE": ACCOUNTABLE_EXECUTIVE,
    "BASE_MAINTENANCE_MANAGER": BASE_MANAGER,
    "LINE_MAINTENANCE_MANAGER": DEPARTMENT_HEAD,
    "WORKSHOP_MANAGER": DEPARTMENT_HEAD,
    "PLANNING_ENGINEER": PLANNER,
    "ROSTER_PLANNER": PLANNER,
    "PRODUCTION_ENGINEER": SUPERVISOR,
    "DEPARTMENT_SUPERVISOR": SUPERVISOR,
    "DEPARTMENT_HEAD": DEPARTMENT_HEAD,
    "BASE_MANAGER": BASE_MANAGER,
    "LINE_MANAGER": DEPARTMENT_HEAD,
    "QUALITY_MANAGER": QUALITY,
    "QUALITY_INSPECTOR": QUALITY - {
        PermissionCode.ROSTER_OVERRIDE_BLOCKER.value,
        PermissionCode.ROSTER_MANAGE_RULES.value,
        PermissionCode.ROSTER_MANAGE_SHIFT_SEMANTICS.value,
        PermissionCode.ROSTER_MANAGE_CONTROLLED_OUTPUT.value,
    },
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


_SCOPED_ROSTER_DEFAULTS = {
    PermissionCode.ROSTER_VIEW_DEPARTMENT.value,
    PermissionCode.ROSTER_EDIT.value,
    PermissionCode.ROSTER_DELETE_DRAFT_ASSIGNMENT.value,
    PermissionCode.ROSTER_APPROVE.value,
    PermissionCode.ROSTER_AMEND_PUBLISHED.value,
    PermissionCode.ROSTER_ALLOCATE_WORK.value,
}


def _role_value(user: account_models.User) -> str:
    return str(getattr(getattr(user, "role", None), "value", getattr(user, "role", "")))


def default_permissions_for(user: account_models.User) -> set[str]:
    """Resolve permissions only from explicit account role and grants.

    Free-text position titles are descriptive HR data, not authorization data.
    They must never silently turn a user into a roster planner, supervisor,
    department head, publisher, Quality authority, HR manager or payroll user.
    """

    if not user or getattr(user, "is_system_account", False):
        return set()
    if getattr(user, "is_superuser", False) or getattr(user, "is_amo_admin", False):
        return set(ALL_PERMISSIONS)
    return set(ROLE_PERMISSIONS.get(_role_value(user), EMPLOYEE))


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


def _active_contract_base_ids(db: Session, *, amo_id: str, user_id: str) -> set[str]:
    today = date.today()
    rows = db.query(models.EmploymentContract).filter(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.user_id == user_id,
        models.EmploymentContract.employment_status == models.EmploymentStatus.ACTIVE,
        models.EmploymentContract.effective_from <= today,
        or_(models.EmploymentContract.effective_to.is_(None), models.EmploymentContract.effective_to >= today),
    ).all()
    base_ids: set[str] = set()
    for row in rows:
        if row.primary_base_station_id:
            base_ids.add(str(row.primary_base_station_id))
        if row.secondary_base_station_id:
            base_ids.add(str(row.secondary_base_station_id))
    return base_ids


def _default_scope_allows(
    db: Session,
    *,
    user: account_models.User,
    permission_code: str,
    department_id: Optional[str],
    base_station_id: Optional[str],
) -> bool:
    defaults = default_permissions_for(user)
    if permission_code not in defaults:
        return False
    if permission_code not in _SCOPED_ROSTER_DEFAULTS:
        return True

    # Explicitly tenant-wide roles may exercise scoped actions globally. A
    # department/base role must provide a concrete resource scope; calling a
    # scoped permission with neither identifier can never mean "all tenant".
    if PermissionCode.ROSTER_VIEW_ALL.value in defaults:
        return True
    if department_id is None and base_station_id is None:
        return False

    if department_id is not None:
        user_department_id = str(getattr(user, "department_id", "") or "")
        if not user_department_id or user_department_id != str(department_id):
            return False

    if base_station_id is not None:
        amo_id = getattr(user, "effective_amo_id", None) or user.amo_id
        if str(base_station_id) not in _active_contract_base_ids(db, amo_id=amo_id, user_id=user.id):
            return False

    return True


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
    return _default_scope_allows(
        db,
        user=user,
        permission_code=code,
        department_id=department_id,
        base_station_id=base_station_id,
    )


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
    """Return globally effective permissions using the same rules as guards.

    Scope-bound role defaults are omitted from this global permission list. UI
    controls that depend on department/base permissions should obtain or apply
    a concrete scope instead of treating this list as a tenant-wide grant.
    """

    defaults = default_permissions_for(user)
    permissions = {
        code for code in defaults
        if code not in _SCOPED_ROSTER_DEFAULTS
        or PermissionCode.ROSTER_VIEW_ALL.value in defaults
    }
    amo_id = getattr(user, "effective_amo_id", None) or user.amo_id
    today = date.today()
    rows = db.query(models.WorkforcePermissionGrant).filter(
        models.WorkforcePermissionGrant.amo_id == amo_id,
        models.WorkforcePermissionGrant.user_id == user.id,
        or_(models.WorkforcePermissionGrant.effective_from.is_(None), models.WorkforcePermissionGrant.effective_from <= today),
        or_(models.WorkforcePermissionGrant.effective_to.is_(None), models.WorkforcePermissionGrant.effective_to >= today),
        models.WorkforcePermissionGrant.department_id.is_(None),
        models.WorkforcePermissionGrant.base_station_id.is_(None),
    ).order_by(models.WorkforcePermissionGrant.created_at.asc()).all()
    effects: dict[str, set[models.PermissionEffect]] = {}
    for row in rows:
        effects.setdefault(row.permission_code, set()).add(row.effect)
    for code, code_effects in effects.items():
        if models.PermissionEffect.DENY in code_effects:
            permissions.discard(code)
        elif models.PermissionEffect.GRANT in code_effects:
            permissions.add(code)
    return sorted(permissions)


def any_permission(db: Session, *, user: account_models.User, permissions: Iterable[PermissionCode | str]) -> bool:
    return any(has_permission(db, user=user, permission=permission) for permission in permissions)
