from __future__ import annotations

from amodb.apps.accounts.tenant_authority import is_tenant_admin

from fastapi import HTTPException

from amodb.apps.accounts import models as account_models

from .workspace_service import role_value


# Document controllers may prepare and administer records, but controlled approval
# decisions are deliberately restricted to accountable management roles. Quality
# inspectors and auditors remain evidence/review participants; they do not inherit
# librarian/controller or publication authority from their operational titles.
DECISION_APPROVER_ROLES = {
    "ACCOUNTABLE_EXECUTIVE",
}


def is_decision_approver(user: account_models.User) -> bool:
    return bool(
        is_tenant_admin(user) or role_value(user) in DECISION_APPROVER_ROLES
    )


def require_decision_approver(user: account_models.User) -> None:
    if not is_decision_approver(user):
        raise HTTPException(
            status_code=403,
            detail="Accountable document approval privileges required",
        )
