from __future__ import annotations

from fastapi import Depends, HTTPException, status

from amodb.security import get_current_active_user

from . import models


BILLING_READER_ROLES = {
    models.AccountRole.AMO_ADMIN,
    models.AccountRole.FINANCE_MANAGER,
    models.AccountRole.ACCOUNTS_OFFICER,
}

CONTRACT_MANAGER_ROLES = {
    models.AccountRole.AMO_ADMIN,
    models.AccountRole.FINANCE_MANAGER,
}


def require_authenticated_user(current_user=Depends(get_current_active_user)):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if getattr(current_user, "is_system_account", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System accounts cannot access tenant commercial billing.")
    return current_user


def require_billing_reader(current_user=Depends(require_authenticated_user)):
    if getattr(current_user, "is_superuser", False):
        return current_user
    if not getattr(current_user, "amo_id", None):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant billing context is required.")
    if getattr(current_user, "role", None) not in BILLING_READER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AMO administrator or finance billing role is required to view commercial billing records.",
        )
    return current_user


def require_contract_manager(current_user=Depends(require_billing_reader)):
    if getattr(current_user, "is_superuser", False):
        return current_user
    if getattr(current_user, "role", None) not in CONTRACT_MANAGER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AMO administrator or finance manager authority is required to accept or cancel recurring contracts.",
        )
    return current_user
