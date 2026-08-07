"""
Module entitlement helpers.

These helpers centralise the logic for checking whether a request can
access a given module (Quality, Fleet, Work, etc.) based on resolved
license entitlements for the tenant (AMO).
"""

from __future__ import annotations

from typing import Callable, Optional

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import services as account_services

from .database import get_read_db
from .security import get_current_active_user


def _has_module_subscription(db: Session, amo_id: str, module_key: str) -> Optional[bool]:
    # (amo_id, module_code) is unique, so sorting every module-gated request is
    # unnecessary. Keep this as a single indexed point lookup.
    subscription = (
        db.query(account_models.ModuleSubscription)
        .filter(
            account_models.ModuleSubscription.amo_id == amo_id,
            account_models.ModuleSubscription.module_code == module_key,
        )
        .first()
    )
    if not subscription:
        return None

    now = datetime.now(timezone.utc)
    effective_from = subscription.effective_from
    effective_to = subscription.effective_to
    if effective_from and effective_from.tzinfo is None:
        effective_from = effective_from.replace(tzinfo=timezone.utc)
    if effective_to and effective_to.tzinfo is None:
        effective_to = effective_to.replace(tzinfo=timezone.utc)
    if effective_from and now < effective_from:
        return False
    if effective_to and now > effective_to:
        return False
    return subscription.status in {
        account_models.ModuleSubscriptionStatus.ENABLED,
        account_models.ModuleSubscriptionStatus.TRIAL,
    }


def _has_module_entitlement(db: Session, amo_id: str, module_key: str) -> bool:
    """Return True if the AMO has an active entitlement for the given module."""
    entitlements = account_services.resolve_entitlements(db, amo_id=amo_id)
    entitlement = entitlements.get(module_key)

    if entitlement is None:
        return False
    if entitlement.is_unlimited:
        return True
    return entitlement.limit is not None and entitlement.limit > 0


def require_module(module_key: str) -> Callable[[account_models.User, Session], account_models.User]:
    """FastAPI dependency that blocks access when a module is not entitled."""

    def dependency(
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_read_db),
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

        access_status = account_services.get_billing_access_status(db, amo_id=amo_id)
        if not access_status.has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=access_status.lock_reason or "Billing access is locked for this account.",
            )

        # Explicit module subscription is authoritative when present. Do not run
        # the legacy entitlement query as well: that historical fallback can scan
        # license records and was previously executed even when the answer was
        # already known from the unique ModuleSubscription row.
        subscription_allowed = _has_module_subscription(db, amo_id, module_key)
        if subscription_allowed is False:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Module '{module_key}' is not enabled for this account.",
            )
        if subscription_allowed is True:
            return current_user

        # Backwards-compatible fallback for tenants still licensed exclusively
        # through LicenseEntitlement records.
        if not _has_module_entitlement(db, amo_id, module_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Module '{module_key}' is not enabled for this account.",
            )
        return current_user

    return dependency
