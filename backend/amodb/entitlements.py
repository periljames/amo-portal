"""
Module entitlement helpers.

These helpers centralise the logic for checking whether a request can
access a given module (Quality, Fleet, Work, etc.) based on resolved
license entitlements for the tenant (AMO).
"""

from __future__ import annotations

from typing import Callable, Optional

from datetime import datetime

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import services as account_services

from .database import get_db
from .security import get_current_active_user


def _has_module_subscription(db: Session, amo_id: str, module_key: str) -> Optional[bool]:
    subscription = (
        db.query(account_models.ModuleSubscription)
        .filter(
            account_models.ModuleSubscription.amo_id == amo_id,
            account_models.ModuleSubscription.module_code == module_key,
        )
        .order_by(account_models.ModuleSubscription.updated_at.desc())
        .first()
    )
    if not subscription:
        return None

    now = datetime.utcnow()
    if subscription.effective_from and now < subscription.effective_from:
        return False
    if subscription.effective_to and now > subscription.effective_to:
        return False
    return subscription.status in {
        account_models.ModuleSubscriptionStatus.ENABLED,
        account_models.ModuleSubscriptionStatus.TRIAL,
    }


def _has_module_entitlement(db: Session, amo_id: str, module_key: str) -> bool:
    """
    Return True if the AMO has an active entitlement for the given module.

    Unlimited entitlements always pass. Numeric entitlements require a
    positive limit; 0 / None are treated as not entitled.
    """

    entitlements = account_services.resolve_entitlements(db, amo_id=amo_id)
    entitlement = entitlements.get(module_key)

    if entitlement is None:
        return False

    if entitlement.is_unlimited:
        return True

    return entitlement.limit is not None and entitlement.limit > 0


def require_module(module_key: str) -> Callable[[account_models.User, Session], account_models.User]:
    """
    FastAPI dependency that blocks access when a module is not entitled.

    Usage:
        router = APIRouter(
            prefix="/quality",
            dependencies=[Depends(require_module("quality"))],
        )
    """

    def dependency(
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_db),
    ) -> account_models.User:
        # Global superusers can always access modules for diagnostics/support.
        if getattr(current_user, "is_superuser", False):
            return current_user

        amo_id = getattr(current_user, "amo_id", None)
        if not amo_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No AMO selected for the current session.",
            )

        subscription_allowed = _has_module_subscription(db, amo_id, module_key)
        if subscription_allowed is not None:
            if not subscription_allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Module '{module_key}' is not enabled for this account.",
                )
            return current_user

        if not _has_module_entitlement(db, amo_id, module_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Module '{module_key}' is not enabled for this account.",
            )

        return current_user

    return dependency
