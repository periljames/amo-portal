from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from amodb.apps.accounts import models as account_models

from . import models as platform_models
from . import saas_models




def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _commercial_state(
    *,
    license_status: str | None,
    module_enabled: int,
    module_trial: int,
    provider_statuses: dict[str, str],
) -> str:
    provider_values = {str(value or "").upper() for value in provider_statuses.values()}
    if "PAST_DUE" in provider_values:
        return "PAST_DUE"
    if license_status == "ACTIVE" or module_enabled > 0 or "ACTIVE" in provider_values:
        return "CONNECTED"
    if license_status == "TRIALING" or module_trial > 0 or "TRIALING" in provider_values:
        return "TRIAL"
    if provider_values & {"CHECKOUT_PENDING", "PAYMENT_PENDING"}:
        return "PAYMENT_PENDING"
    return "UNCONNECTED"


def _is_conflict(*, administrative_active: bool, commercial_status: str) -> bool:
    return not administrative_active and commercial_status in {
        "CONNECTED",
        "TRIAL",
        "PAYMENT_PENDING",
        "PAST_DUE",
    }


def _counts_by_tenant(db: Session, tenant_ids: list[str], status: account_models.ModuleSubscriptionStatus) -> dict[str, int]:
    return {
        str(amo_id): int(count or 0)
        for amo_id, count in (
            db.query(account_models.ModuleSubscription.amo_id, func.count(account_models.ModuleSubscription.id))
            .filter(
                account_models.ModuleSubscription.amo_id.in_(tenant_ids),
                account_models.ModuleSubscription.status == status,
            )
            .group_by(account_models.ModuleSubscription.amo_id)
            .all()
        )
    }


def list_tenants_authoritative(
    db: Session,
    *,
    q: str | None = None,
    status_filter: str | None = None,
    data_mode: str | None = "REAL",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Return a bounded register with administrative and commercial state separated."""
    mode = str(data_mode or "REAL").strip().upper()
    if mode not in {"REAL", "DEMO", "ALL"}:
        mode = "REAL"
    query = db.query(account_models.AMO)
    if mode == "REAL":
        query = query.filter(account_models.AMO.is_demo.is_(False))
    elif mode == "DEMO":
        query = query.filter(account_models.AMO.is_demo.is_(True))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                account_models.AMO.name.ilike(like),
                account_models.AMO.amo_code.ilike(like),
                account_models.AMO.login_slug.ilike(like),
            )
        )
    if status_filter == "active":
        query = query.filter(account_models.AMO.is_active.is_(True))
    elif status_filter == "inactive":
        query = query.filter(account_models.AMO.is_active.is_(False))

    total = int(query.count())
    bounded_limit = max(1, min(int(limit), 200))
    bounded_offset = max(0, int(offset))
    rows = (
        query.order_by(account_models.AMO.created_at.desc(), account_models.AMO.id.desc())
        .offset(bounded_offset)
        .limit(bounded_limit)
        .all()
    )
    tenant_ids = [str(row.id) for row in rows]
    if not tenant_ids:
        return {"items": [], "total": total, "limit": bounded_limit, "offset": bounded_offset, "data_mode": mode}

    user_stats = {
        str(amo_id): {"count": int(count or 0), "last_login_at": last_login}
        for amo_id, count, last_login in (
            db.query(
                account_models.User.amo_id,
                func.count(account_models.User.id),
                func.max(account_models.User.last_login_at),
            )
            .filter(account_models.User.amo_id.in_(tenant_ids))
            .group_by(account_models.User.amo_id)
            .all()
        )
    }

    latest_licenses: dict[str, account_models.TenantLicense] = {}
    license_rows = (
        db.query(account_models.TenantLicense)
        .options(joinedload(account_models.TenantLicense.catalog_sku))
        .filter(account_models.TenantLicense.amo_id.in_(tenant_ids))
        .order_by(
            account_models.TenantLicense.amo_id.asc(),
            account_models.TenantLicense.created_at.desc(),
            account_models.TenantLicense.id.desc(),
        )
        .all()
    )
    for license_row in license_rows:
        latest_licenses.setdefault(str(license_row.amo_id), license_row)

    enabled_counts = _counts_by_tenant(db, tenant_ids, account_models.ModuleSubscriptionStatus.ENABLED)
    trial_counts = _counts_by_tenant(db, tenant_ids, account_models.ModuleSubscriptionStatus.TRIAL)

    provider_by_tenant: dict[str, dict[str, str]] = {tenant_id: {} for tenant_id in tenant_ids}
    for provider_row in (
        db.query(saas_models.SaaSBillingAccount)
        .filter(saas_models.SaaSBillingAccount.tenant_id.in_(tenant_ids))
        .all()
    ):
        provider_by_tenant.setdefault(str(provider_row.tenant_id), {})[str(provider_row.provider)] = str(provider_row.status or "UNKNOWN").upper()

    items: list[dict[str, Any]] = []
    for amo in rows:
        tenant_id = str(amo.id)
        license_row = latest_licenses.get(tenant_id)
        license_status = _enum_value(getattr(license_row, "status", None))
        enabled = enabled_counts.get(tenant_id, 0)
        trial = trial_counts.get(tenant_id, 0)
        providers = provider_by_tenant.get(tenant_id, {})
        commercial_status = _commercial_state(
            license_status=license_status,
            module_enabled=enabled,
            module_trial=trial,
            provider_statuses=providers,
        )
        conflict = _is_conflict(administrative_active=bool(amo.is_active), commercial_status=commercial_status)
        sku = getattr(license_row, "catalog_sku", None) if license_row else None
        users = user_stats.get(tenant_id, {"count": 0, "last_login_at": None})
        items.append(
            {
                "id": amo.id,
                "amo_code": amo.amo_code,
                "login_slug": amo.login_slug,
                "name": amo.name,
                "country": amo.country,
                "is_active": bool(amo.is_active),
                "is_demo": bool(amo.is_demo),
                "data_mode": "DEMO" if bool(amo.is_demo) else "REAL",
                "status": "STATUS_CONFLICT" if conflict else ("ACTIVE" if amo.is_active else "SUSPENDED"),
                "administrative_status": "ACTIVE" if amo.is_active else "SUSPENDED",
                "commercial_status": commercial_status,
                "status_conflict": conflict,
                "status_conflict_reason": (
                    "Administrative suspension conflicts with active billing/module/provider evidence."
                    if conflict
                    else None
                ),
                "plan_code": getattr(sku, "code", None),
                "license_status": license_status,
                "is_read_only": bool(getattr(license_row, "is_read_only", False)) if license_row else False,
                "enabled_module_count": enabled,
                "trial_module_count": trial,
                "provider_statuses": providers,
                "user_count": users["count"],
                "last_user_login_at": users["last_login_at"],
                "created_at": amo.created_at,
                "updated_at": amo.updated_at,
            }
        )
    return {"items": items, "total": total, "limit": bounded_limit, "offset": bounded_offset, "data_mode": mode}


def tenant_lifecycle_evidence(db: Session, *, tenant_id: str) -> dict[str, Any]:
    amo = db.get(account_models.AMO, tenant_id)
    if amo is None:
        raise ValueError("Tenant not found")
    latest_license = (
        db.query(account_models.TenantLicense)
        .filter(account_models.TenantLicense.amo_id == tenant_id)
        .order_by(account_models.TenantLicense.created_at.desc(), account_models.TenantLicense.id.desc())
        .first()
    )
    modules = (
        db.query(account_models.ModuleSubscription)
        .filter(
            account_models.ModuleSubscription.amo_id == tenant_id,
            account_models.ModuleSubscription.status.in_(
                [account_models.ModuleSubscriptionStatus.ENABLED, account_models.ModuleSubscriptionStatus.TRIAL]
            ),
        )
        .all()
    )
    accounts = db.query(saas_models.SaaSBillingAccount).filter(saas_models.SaaSBillingAccount.tenant_id == tenant_id).all()
    license_status = _enum_value(getattr(latest_license, "status", None))
    enabled = sum(1 for row in modules if row.status == account_models.ModuleSubscriptionStatus.ENABLED)
    trial = sum(1 for row in modules if row.status == account_models.ModuleSubscriptionStatus.TRIAL)
    providers = {str(row.provider): str(row.status or "UNKNOWN").upper() for row in accounts}
    commercial_status = _commercial_state(
        license_status=license_status,
        module_enabled=enabled,
        module_trial=trial,
        provider_statuses=providers,
    )
    return {
        "tenant_id": tenant_id,
        "administrative_status": "ACTIVE" if amo.is_active else "SUSPENDED",
        "commercial_status": commercial_status,
        "status_conflict": _is_conflict(administrative_active=bool(amo.is_active), commercial_status=commercial_status),
        "license_status": license_status,
        "enabled_modules": [row.module_code for row in modules if row.status == account_models.ModuleSubscriptionStatus.ENABLED],
        "trial_modules": [row.module_code for row in modules if row.status == account_models.ModuleSubscriptionStatus.TRIAL],
        "provider_statuses": providers,
    }


def reconcile_tenant_status(
    db: Session,
    *,
    tenant_id: str,
    actor_user_id: str,
    reason: str,
    apply: bool,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        raise ValueError("A reconciliation reason is required")
    evidence = tenant_lifecycle_evidence(db, tenant_id=tenant_id)
    amo = db.get(account_models.AMO, tenant_id)
    assert amo is not None
    previous = bool(amo.is_active)
    changed = bool(apply and evidence["status_conflict"])
    if changed:
        amo.is_active = True
    db.add(
        platform_models.PlatformAuditLog(
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            action="tenant.lifecycle.reconciled" if changed else "tenant.lifecycle.reviewed",
            module="platform",
            entity_type="tenant",
            entity_id=tenant_id,
            reason=str(reason)[:1000],
            details_json={"apply": bool(apply), "previous_is_active": previous, "evidence": evidence},
        )
    )
    db.commit()
    return {**tenant_lifecycle_evidence(db, tenant_id=tenant_id), "changed": changed}
