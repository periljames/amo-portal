from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb import entitlements
from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import services as account_services
from amodb.database import get_read_db
from amodb.security import get_current_active_user


router = APIRouter(prefix="/commerce/access/modules", tags=["tenant-module-access"])


def _metadata(row: account_models.ModuleSubscription) -> dict[str, Any]:
    if not row.metadata_json:
        return {}
    try:
        value = json.loads(row.metadata_json)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _payment_due_for_module(
    db: Session,
    *,
    tenant_id: str,
    module_code: str,
    now: datetime,
) -> bool:
    aliases = entitlements._module_aliases(module_code)
    rows = (
        db.query(account_models.ModuleSubscription)
        .filter(
            account_models.ModuleSubscription.amo_id == tenant_id,
            account_models.ModuleSubscription.module_code.in_(aliases),
        )
        .all()
    )
    contract_codes: set[str] = set()
    for row in rows:
        metadata = _metadata(row)
        if metadata.get("commercial_offer_only"):
            continue
        end = _aware(row.effective_to)
        if end is not None and end <= now:
            contract_codes.add(str(metadata.get("contract_module_code") or metadata.get("bundle_parent") or row.module_code))
        elif row.status == account_models.ModuleSubscriptionStatus.SUSPENDED:
            contract_codes.add(str(metadata.get("contract_module_code") or metadata.get("bundle_parent") or row.module_code))
    if not contract_codes:
        return False

    query = db.query(account_models.BillingInvoice.id).filter(
        account_models.BillingInvoice.amo_id == tenant_id,
        account_models.BillingInvoice.status == account_models.InvoiceStatus.PENDING,
        account_models.BillingInvoice.due_at.isnot(None),
        account_models.BillingInvoice.due_at <= now,
    )
    for contract_code in sorted(contract_codes):
        if query.filter(
            account_models.BillingInvoice.description.contains(f'"module_code":"{contract_code}"'),
            account_models.BillingInvoice.description.contains('"source":"MODULE_RENEWAL"'),
        ).first() is not None:
            return True
    return False


def module_access_state(
    db: Session,
    *,
    tenant_id: str,
    module_code: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    checked_at = now or datetime.now(timezone.utc)
    account = account_services.get_billing_access_status(db, amo_id=tenant_id, as_of=checked_at)
    if not account.has_access:
        return {
            "module_code": module_code,
            "access_state": "ACCOUNT_PAYMENT_REQUIRED",
            "has_access": False,
            "redirect_to_billing": True,
            "message": account.lock_reason or "Account billing action is required.",
        }

    subscription_allowed = entitlements._has_module_subscription(db, tenant_id, module_code)
    if subscription_allowed is True:
        return {
            "module_code": module_code,
            "access_state": "ACTIVE",
            "has_access": True,
            "redirect_to_billing": False,
            "message": None,
        }

    if _payment_due_for_module(
        db,
        tenant_id=tenant_id,
        module_code=module_code,
        now=checked_at,
    ):
        return {
            "module_code": module_code,
            "access_state": "MODULE_PAYMENT_REQUIRED",
            "has_access": False,
            "redirect_to_billing": True,
            "message": f"The {module_code} module requires renewal payment.",
        }

    if subscription_allowed is None and entitlements._has_module_entitlement(db, tenant_id, module_code):
        return {
            "module_code": module_code,
            "access_state": "LEGACY_ENTITLED",
            "has_access": True,
            "redirect_to_billing": False,
            "message": None,
        }

    return {
        "module_code": module_code,
        "access_state": "NOT_SUBSCRIBED",
        "has_access": False,
        "redirect_to_billing": True,
        "message": f"The {module_code} module is not included in this AMO's current subscription.",
    }


@router.get("/{module_code}")
def get_module_access_state(
    module_code: str,
    db: Session = Depends(get_read_db),
    user: account_models.User = Depends(get_current_active_user),
):
    if getattr(user, "is_superuser", False):
        return {
            "module_code": module_code,
            "access_state": "PLATFORM_SUPERUSER",
            "has_access": True,
            "redirect_to_billing": False,
            "message": None,
        }
    tenant_id = str(getattr(user, "amo_id", None) or "")
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context is required.")
    return module_access_state(db, tenant_id=tenant_id, module_code=module_code)
