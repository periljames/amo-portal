from __future__ import annotations

from fastapi import HTTPException

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts.tenant_authority import is_tenant_admin


def _role_value(user: account_models.User) -> str:
    role = getattr(user, "role", None)
    return str(getattr(role, "value", role) or "")


def fieldwork_execution_user_ids(audit: object) -> set[str]:
    """Return audit participants allowed to author fieldwork.

    Assignment visibility and execution authority are deliberately different.
    Observers are members of the audit team for visibility/presence, but do not
    author checklist responses, auditor notes or findings. Lead, assistant and
    explicitly governed supporting auditors may execute fieldwork; completion
    remains a separate lead-only gate.
    """

    values = {
        getattr(audit, "lead_auditor_user_id", None),
        getattr(audit, "assistant_auditor_user_id", None),
    }
    values.update(
        str(value)
        for value in (getattr(audit, "supporting_auditor_user_ids", None) or [])
        if value
    )
    return {str(value) for value in values if value}


def audit_allows_fieldwork_execution(audit: object, user_id: str | None) -> bool:
    return bool(user_id and str(user_id) in fieldwork_execution_user_ids(audit))


def require_audit_fieldwork_write_access(
    current_user: account_models.User,
    audit: object,
) -> None:
    if audit_allows_fieldwork_execution(audit, getattr(current_user, "id", None)):
        return

    observer_id = str(getattr(audit, "observer_auditor_user_id", None) or "")
    if observer_id and observer_id == str(getattr(current_user, "id", "")):
        raise HTTPException(
            status_code=403,
            detail=(
                "Observer auditors are read-only participants. They may observe "
                "fieldwork and presence, but cannot record checklist responses, "
                "auditor notes or findings."
            ),
        )

    role = _role_value(current_user)
    if is_tenant_admin(current_user) or role == "QUALITY_MANAGER":
        raise HTTPException(
            status_code=403,
            detail=(
                "Quality management and tenant administration may oversee or flag "
                "fieldwork for review, but cannot author fieldwork unless explicitly "
                "assigned as an executing auditor."
            ),
        )

    raise HTTPException(
        status_code=403,
        detail="Only the assigned lead, assistant or governed supporting auditor may record audit fieldwork.",
    )
