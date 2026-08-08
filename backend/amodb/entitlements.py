"""
Module entitlement helpers.

These helpers centralise the logic for checking whether a request can
access a given module (Quality, Fleet, Work, etc.) based on resolved
license entitlements for the tenant (AMO).
"""

from __future__ import annotations

import json
from typing import Callable, Optional

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import services as account_services

from .database import get_read_db
from .security import get_current_active_user


# Commercial compatibility aliases. Historical product groupings continue to
# satisfy a newly separated capability until the tenant receives an explicit
# narrow subscription. An explicit narrow row is authoritative when present.
_MODULE_ALIASES: dict[str, tuple[str, ...]] = {
    "document_control": ("document_control", "quality"),
    "finance": ("finance", "finance_inventory"),
    "inventory": ("inventory", "finance_inventory"),
    "procurement": ("procurement", "finance_inventory"),
    "finance_inventory": ("finance_inventory", "procurement"),
}


def _module_aliases(module_key: str) -> tuple[str, ...]:
    normalized = str(module_key or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _MODULE_ALIASES.get(normalized, (normalized,))


def _row_metadata(row: account_models.ModuleSubscription) -> dict:
    if not row.metadata_json:
        return {}
    try:
        value = json.loads(row.metadata_json)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _offer_only(row: account_models.ModuleSubscription) -> bool:
    return bool(_row_metadata(row).get("commercial_offer_only"))


def _row_is_current(row: account_models.ModuleSubscription, now: datetime) -> bool:
    effective_from = row.effective_from
    effective_to = row.effective_to
    if effective_from and effective_from.tzinfo is None:
        effective_from = effective_from.replace(tzinfo=timezone.utc)
    if effective_to and effective_to.tzinfo is None:
        effective_to = effective_to.replace(tzinfo=timezone.utc)
    if effective_from and now < effective_from:
        return False
    if effective_to and now > effective_to:
        return False
    return True


def _has_module_subscription(db: Session, amo_id: str, module_key: str) -> Optional[bool]:
    aliases = _module_aliases(module_key)
    rows = (
        db.query(account_models.ModuleSubscription)
        .filter(
            account_models.ModuleSubscription.amo_id == amo_id,
            account_models.ModuleSubscription.module_code.in_(aliases),
        )
        .all()
    )
    if not rows:
        return None

    now = datetime.now(timezone.utc)
    exact_code = aliases[0]
    exact = next((row for row in rows if str(row.module_code) == exact_code), None)
    if exact is not None and not _offer_only(exact):
        if not _row_is_current(exact, now):
            return False
        return exact.status in {
            account_models.ModuleSubscriptionStatus.ENABLED,
            account_models.ModuleSubscriptionStatus.TRIAL,
        }

    # A commercial-offer placeholder is not an entitlement decision. Ignore it
    # and preserve a compatible legacy bundle if one exists.
    for row in rows:
        if _offer_only(row):
            continue
        if not _row_is_current(row, now):
            continue
        if row.status in {
            account_models.ModuleSubscriptionStatus.ENABLED,
            account_models.ModuleSubscriptionStatus.TRIAL,
        }:
            return True
    return None if all(_offer_only(row) for row in rows) else False


def _has_module_entitlement(db: Session, amo_id: str, module_key: str) -> bool:
    """Return True if the AMO has an active legacy entitlement for this capability."""
    entitlements = account_services.resolve_entitlements(db, amo_id=amo_id)
    for alias in _module_aliases(module_key):
        entitlement = entitlements.get(alias)
        if entitlement is None:
            continue
        if entitlement.is_unlimited:
            return True
        if entitlement.limit is not None and entitlement.limit > 0:
            return True
    return False


def _raise_module_payment_required_if_due(
    db: Session,
    *,
    amo_id: str,
    module_key: str,
) -> None:
    # Imported lazily to avoid a core-entitlement <-> platform package cycle at
    # application import time. This path executes only when a module is denied,
    # so it does not add queries to normal entitled requests.
    from amodb.apps.platform.module_access_router import _payment_due_for_module

    if _payment_due_for_module(
        db,
        tenant_id=amo_id,
        module_code=module_key,
        now=datetime.now(timezone.utc),
    ):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "MODULE_PAYMENT_REQUIRED",
                "message": f"Module '{module_key}' requires renewal payment.",
                "module_code": module_key,
                "redirect_to_billing": True,
            },
        )


def require_module(module_key: str) -> Callable[[account_models.User, Session], account_models.User]:
    """FastAPI dependency that blocks access when a module is not entitled."""

    def dependency(
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_read_db),
    ) -> account_models.User:
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
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "BILLING_ACCESS_REQUIRED",
                    "message": access_status.lock_reason or "Billing access is locked for this account.",
                    "access_state": access_status.access_state,
                    "redirect_to_billing": True,
                    "actionable_invoice_id": access_status.actionable_invoice_id,
                },
            )

        subscription_allowed = _has_module_subscription(db, amo_id, module_key)
        if subscription_allowed is False:
            _raise_module_payment_required_if_due(db, amo_id=amo_id, module_key=module_key)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "MODULE_NOT_SUBSCRIBED",
                    "message": f"Module '{module_key}' is not enabled for this account.",
                    "module_code": module_key,
                    "upgrade_available": True,
                    "redirect_to_billing": True,
                },
            )
        if subscription_allowed is True:
            return current_user

        if not _has_module_entitlement(db, amo_id, module_key):
            _raise_module_payment_required_if_due(db, amo_id=amo_id, module_key=module_key)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "MODULE_NOT_SUBSCRIBED",
                    "message": f"Module '{module_key}' is not enabled for this account.",
                    "module_code": module_key,
                    "upgrade_available": True,
                    "redirect_to_billing": True,
                },
            )
        return current_user

    return dependency
