from __future__ import annotations

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts.tenant_authority import is_tenant_admin

from .workspace_decision_policy import is_decision_approver
from .workspace_service import is_control_user, role_value


def document_control_persona(user: account_models.User) -> str:
    """Return the user's global DMS persona.

    Document ownership/review authority is document-specific and is deliberately
    resolved from DocumentResponsibilityAssignment rather than inflated into the
    user's global account role.
    """
    if is_tenant_admin(user):
        return "ADMIN"
    if is_control_user(user):
        return "DOCUMENT_CONTROL"
    if role_value(user) == "ACCOUNTABLE_EXECUTIVE":
        return "ACCOUNTABLE_EXECUTIVE"
    return "READER"


def document_control_capabilities(user: account_models.User) -> dict[str, bool | str]:
    control = is_control_user(user)
    approve = is_decision_approver(user)
    admin = is_tenant_admin(user)
    persona = document_control_persona(user)
    return {
        "persona": persona,
        "read": True,
        "control": control,
        "approve": approve,
        "register": control,
        "edit_properties": control,
        "upload_revision": control,
        "manage_authority_records": control,
        "manage_distribution": control,
        "manage_physical_copies": control,
        "manage_retention": control,
        "configure": admin,
        "publish": control,
        "accountable_approval": approve,
        "admin_all": admin,
    }


def reader_capabilities() -> dict[str, bool | str]:
    return {
        "persona": "READER",
        "read": True,
        "control": False,
        "approve": False,
        "register": False,
        "edit_properties": False,
        "upload_revision": False,
        "manage_authority_records": False,
        "manage_distribution": False,
        "manage_physical_copies": False,
        "manage_retention": False,
        "configure": False,
        "publish": False,
        "accountable_approval": False,
        "admin_all": False,
    }
