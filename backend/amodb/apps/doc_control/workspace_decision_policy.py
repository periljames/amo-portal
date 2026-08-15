from __future__ import annotations

from fastapi import HTTPException

from amodb.apps.accounts import models as account_models

from .workspace_service import role_value


# Document controllers may prepare and administer records, but controlled approval
# decisions are deliberately restricted to accountable management roles. A Quality
# Inspector remains able to perform controller work without being able to approve,
# publish, archive, or rewrite terminal governance records.
DECISION_APPROVER_ROLES = {
    "SUPERUSER",
    "AMO_ADMIN",
    "ACCOUNTABLE_EXECUTIVE",
    "QUALITY_MANAGER",
}


def is_decision_approver(user: account_models.User) -> bool:
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_amo_admin", False)
        or role_value(user) in DECISION_APPROVER_ROLES
    )


def require_decision_approver(user: account_models.User) -> None:
    if not is_decision_approver(user):
        raise HTTPException(
            status_code=403,
            detail="Accountable document approval privileges required",
        )
