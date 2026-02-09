from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from amodb.apps.audit import services as audit_services
from amodb.apps.audit import schemas as audit_schemas

from . import models, schemas
from amodb.apps.accounts import services as account_services
from amodb.apps.finance import services as finance_services

router = APIRouter(prefix="/admin/tenants", tags=["modules_admin"])


def _require_superuser(current_user: models.User) -> models.User:
    if getattr(current_user, "is_system_account", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System/service accounts cannot use superuser endpoints.",
        )
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required.",
        )
    return current_user

ALLOWED_MODULES = {
    "finance_inventory",
    "fleet",
    "maintenance_program",
    "quality",
    "reliability",
    "training",
    "work",
}


def _resolve_tenant(db: Session, *, tenant_id: str) -> models.AMO:
    amo = db.query(models.AMO).filter(models.AMO.id == tenant_id).first()
    if not amo:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    return amo


def _ensure_access(current_user: models.User, tenant_id: str) -> None:
    if current_user.is_superuser:
        return
    if current_user.amo_id != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access not allowed.")


def _upsert_subscription(
    db: Session,
    *,
    amo_id: str,
    module_code: str,
    status_value: models.ModuleSubscriptionStatus,
    plan_code: Optional[str] = None,
    effective_from: Optional[datetime] = None,
    effective_to: Optional[datetime] = None,
    metadata_json: Optional[str] = None,
) -> models.ModuleSubscription:
    subscription = (
        db.query(models.ModuleSubscription)
        .filter(
            models.ModuleSubscription.amo_id == amo_id,
            models.ModuleSubscription.module_code == module_code,
        )
        .first()
    )
    if not subscription:
        subscription = models.ModuleSubscription(
            amo_id=amo_id,
            module_code=module_code,
        )
    subscription.status = status_value
    if plan_code is not None:
        subscription.plan_code = plan_code
    if effective_from is not None:
        subscription.effective_from = effective_from
    if effective_to is not None:
        subscription.effective_to = effective_to
    if metadata_json is not None:
        subscription.metadata_json = metadata_json
    db.add(subscription)
    db.flush()
    return subscription


@router.get(
    "/{tenant_id}/modules",
    response_model=List[schemas.ModuleSubscriptionRead],
)
def list_modules(
    tenant_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    _ensure_access(current_user, tenant_id)
    _resolve_tenant(db, tenant_id=tenant_id)
    return (
        db.query(models.ModuleSubscription)
        .filter(models.ModuleSubscription.amo_id == tenant_id)
        .order_by(models.ModuleSubscription.module_code.asc())
        .all()
    )


@router.post(
    "/{tenant_id}/modules/{module_code}/enable",
    response_model=schemas.ModuleSubscriptionRead,
    status_code=status.HTTP_200_OK,
)
def enable_module(
    tenant_id: str,
    module_code: str,
    payload: Optional[schemas.ModuleSubscriptionCreate] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    _ensure_access(current_user, tenant_id)
    _resolve_tenant(db, tenant_id=tenant_id)
    if module_code not in ALLOWED_MODULES:
        raise HTTPException(status_code=404, detail="Unknown module code.")

    subscription = _upsert_subscription(
        db,
        amo_id=tenant_id,
        module_code=module_code,
        status_value=models.ModuleSubscriptionStatus.ENABLED,
        plan_code=payload.plan_code if payload else None,
        effective_from=payload.effective_from if payload else datetime.utcnow(),
        effective_to=payload.effective_to if payload else None,
        metadata_json=payload.metadata_json if payload else None,
    )

    account_services.seed_default_departments(db, amo_id=tenant_id)
    if module_code == "finance_inventory":
        finance_services.ensure_finance_defaults(db, amo_id=tenant_id)

    audit_services.create_audit_event(
        db,
        amo_id=tenant_id,
        data=audit_schemas.AuditEventCreate(
            entity_type="ModuleSubscription",
            entity_id=subscription.id,
            action="enable",
            actor_user_id=current_user.id,
            after_json={"module_code": module_code, "status": subscription.status.value},
        ),
    )
    db.commit()
    db.refresh(subscription)
    return subscription


@router.post(
    "/{tenant_id}/modules/{module_code}/disable",
    response_model=schemas.ModuleSubscriptionRead,
    status_code=status.HTTP_200_OK,
)
def disable_module(
    tenant_id: str,
    module_code: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    _ensure_access(current_user, tenant_id)
    _resolve_tenant(db, tenant_id=tenant_id)
    if module_code not in ALLOWED_MODULES:
        raise HTTPException(status_code=404, detail="Unknown module code.")

    subscription = _upsert_subscription(
        db,
        amo_id=tenant_id,
        module_code=module_code,
        status_value=models.ModuleSubscriptionStatus.DISABLED,
    )
    audit_services.create_audit_event(
        db,
        amo_id=tenant_id,
        data=audit_schemas.AuditEventCreate(
            entity_type="ModuleSubscription",
            entity_id=subscription.id,
            action="disable",
            actor_user_id=current_user.id,
            after_json={"module_code": module_code, "status": subscription.status.value},
        ),
    )
    db.commit()
    db.refresh(subscription)
    return subscription
