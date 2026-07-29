from __future__ import annotations

from amodb.apps.accounts import models as account_models

from .workspace_decision_policy import is_decision_approver
from .workspace_service import is_control_user


def document_control_capabilities(user: account_models.User) -> dict[str, bool]:
    control = is_control_user(user)
    approve = is_decision_approver(user)
    return {
        "read": True,
        "control": control,
        "approve": approve,
        "register": control,
        "edit_properties": control,
        "upload_revision": control,
        "manage_distribution": control,
        "publish": approve,
    }


def reader_capabilities() -> dict[str, bool]:
    return {
        "read": True,
        "control": False,
        "approve": False,
        "register": False,
        "edit_properties": False,
        "upload_revision": False,
        "manage_distribution": False,
        "publish": False,
    }
