"""Execution-scope authorization for governed forms, checklists, and registers."""
from __future__ import annotations

from fastapi import HTTPException

from amodb.apps.accounts import models as account_models

from . import knowledge_models as km
from .workspace_service import is_control_user, role_value


def _department_value(user: account_models.User) -> str:
    department = getattr(user, "department", None)
    value = getattr(department, "code", department)
    return str(value or "").strip().upper()


def can_execute_profile(
    user: account_models.User,
    profile: km.DocumentationExecutionProfile | None,
) -> bool:
    if not profile:
        return False
    scope = dict(getattr(profile, "access_scope_json", None) or {})
    if not scope or is_control_user(user):
        return True
    allowed_user_ids = {str(value) for value in scope.get("user_ids", []) if value is not None}
    allowed_roles = {str(value).strip().upper() for value in scope.get("roles", []) if value is not None}
    allowed_departments = {
        str(value).strip().upper()
        for value in scope.get("departments", [])
        if value is not None
    }
    return bool(
        str(getattr(user, "id", "")) in allowed_user_ids
        or role_value(user) in allowed_roles
        or (_department_value(user) and _department_value(user) in allowed_departments)
    )


def require_execution_scope(
    user: account_models.User,
    profile: km.DocumentationExecutionProfile | None,
) -> None:
    if not can_execute_profile(user, profile):
        raise HTTPException(
            status_code=403,
            detail="This controlled resource is outside your execution scope",
        )


__all__ = ["can_execute_profile", "require_execution_scope"]
