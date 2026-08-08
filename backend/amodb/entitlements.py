"""Canonical module entitlement checks for tenant requests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.apps.accounts import billing_access, models as account_models

from .database import get_read_db
from .security import get_current_active_user


def _normalize_module_key(module_key: str) -> str:
    return str(module_key or "").strip().lower().replace("-", "_").replace(" ", "_")


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
    code = _normalize_module_key(module_key)
    row = (
        db.query(account_models.ModuleSubscription)
        .filter(
            account_models.ModuleSubscription.amo_id == amo_id,
            account_models.ModuleSubscription.module_code == code,
        )
        .first()
    )
    if row is None or _offer_only(row):
        return None
    if not _row_is_current(row, datetime.now(timezone.utc)):
        return False
    return row.status in {
        account_models.ModuleSubscriptionStatus.ENABLED,
        account_models.ModuleSubscriptionStatus.TRIAL,
    }


def _has_base_contract_entitlement(db: Session, amo_id: str, module_key: str) -> bool:
    entitlement = billing_access.resolve_entitlements(db, amo_id=amo_id).get(
        _normalize_module_key(module_key)
    )
    if entitlement is None:
        return False
    if entitlement.is_unlimited:
        return True
    return entitlement.limit is not None and entitlement.limit > 0


def _raise_module_payment_required_if_due(
    db: Session,
    *,
    amo_id: str,
    module_key: str,
) -> None:
    from amodb.apps.platform.module_access_router import _payment_due_for_module

    if _payment_due_for_module(
        db,
        tenant_id=amo_id,
        module_code=_normalize_module_key(module_key),
        now=datetime.now(timezone.utc),
    ):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "MODULE_PAYMENT_REQUIRED",
                "message": f"Module '{module_key}' requires renewal payment.",
                "module_code": _normalize_module_key(module_key),
                "redirect_to_billing": True,
            },
        )


def require_module(module_key: str) -> Callable[[account_models.User, Session], account_models.User]:
    """FastAPI dependency enforcing one canonical commercial module key."""
    code = _normalize_module_key(module_key)

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

        access_status = billing_access.get_billing_access_status(db, amo_id=amo_id)
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

        subscription_allowed = _has_module_subscription(db, amo_id, code)
        if subscription_allowed is True:
            return current_user
        if subscription_allowed is False:
            _raise_module_payment_required_if_due(db, amo_id=amo_id, module_key=code)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "MODULE_NOT_SUBSCRIBED",
                    "message": f"Module '{code}' is not enabled for this account.",
                    "module_code": code,
                    "upgrade_available": True,
                    "redirect_to_billing": True,
                },
            )

        if _has_base_contract_entitlement(db, amo_id, code):
            return current_user

        _raise_module_payment_required_if_due(db, amo_id=amo_id, module_key=code)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "MODULE_NOT_SUBSCRIBED",
                "message": f"Module '{code}' is not enabled for this account.",
                "module_code": code,
                "upgrade_available": True,
                "redirect_to_billing": True,
            },
        )

    return dependency
