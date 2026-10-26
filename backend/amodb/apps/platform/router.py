from __future__ import annotations

from typing import Any
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from amodb.database import get_db, get_read_db
from amodb.security import get_current_active_user
from amodb.apps.accounts import models as account_models
from . import diagnostics, metrics, models, network_diagnostics, services

router = APIRouter(prefix="/platform", tags=["platform-control-plane"])


def require_platform_superuser(current_user=Depends(get_current_active_user)):
    if not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform superuser access is required.")
    if getattr(current_user, "amo_id", None) and not getattr(current_user, "is_platform_context", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform user must not be bound to an AMO tenant.")
    return current_user


def _actor_id(user) -> str:
    return str(getattr(user, "id", ""))


def _reason(payload: dict[str, Any]) -> str:
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A reason is required.")
    return reason


def _bad(exc: Exception, code: int = 400):
    raise HTTPException(status_code=code, detail=str(exc))


def _support_session_payload(row: models.PlatformTenantSupportSession) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "platform_user_id": row.platform_user_id,
        "access_level": row.access_level,
        "status": row.status,
        "reason": row.reason,
        "requested_by_user_id": row.requested_by_user_id,
        "approved_by_user_id": row.approved_by_user_id,
        "approved_at": row.approved_at,
        "denied_by_user_id": row.denied_by_user_id,
        "denied_at": row.denied_at,
        "expires_at": row.expires_at,
        "ended_at": row.ended_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "metadata": row.metadata_json or {},
    }


def _support_session_expiry(payload: dict[str, Any]) -> datetime:
    hours = int(payload.get("expires_in_hours") or 8)
    hours = max(1, min(hours, 12))
    return datetime.now(timezone.utc) + timedelta(hours=hours)


@router.get("/dashboard/summary")
def dashboard_summary(data_mode: str = "REAL", db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.dashboard_summary(db, data_mode=data_mode)


@router.get("/dashboard/mrr-growth")
def mrr_growth(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return {"items": [], "source": "billing_rollups", "note": "MRR growth is returned empty until billing rollups are populated."}


@router.get("/dashboard/resource-summary")
def dashboard_resource_summary(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.resources_summary(db)


@router.get("/dashboard/recent-alerts")
def recent_alerts(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.list_security_alerts(db, limit=10)


@router.get("/dashboard/recent-jobs")
def recent_jobs(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.list_jobs(db, limit=10)


@router.get("/tenants")
def list_tenants(q: str | None = None, status_filter: str | None = Query(None, alias="status"), data_mode: str = "REAL", limit: int = 50, offset: int = 0, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.list_tenants(db, q=q, status_filter=status_filter, data_mode=data_mode, limit=limit, offset=offset)


@router.post("/tenants")
def create_tenant(payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try:
        return services.create_tenant(db, payload=payload, actor_id=_actor_id(user))
    except Exception as exc:
        _bad(exc)


@router.post("/tenants/{tenant_id}/owner-invitation")
def send_tenant_owner_invitation(
    tenant_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    """Send a one-time password setup link without revealing credentials."""
    from amodb.apps.accounts import router_public as auth_router
    from amodb.apps.accounts import services as account_services
    from datetime import timedelta

    tenant = db.get(account_models.AMO, tenant_id)
    if tenant is None or not tenant.is_active:
        raise HTTPException(status_code=404, detail="Active tenant not found")
    if not auth_router.RESET_LINK_BASE_URL:
        raise HTTPException(status_code=503, detail="PORTAL_BASE_URL must be configured before invitations can be sent")
    owner = db.query(account_models.User).filter(
        account_models.User.amo_id == tenant_id,
        account_models.User.is_amo_admin.is_(True),
        account_models.User.staff_code.like("OWNER-%"),
        account_models.User.is_active.is_(True),
    ).order_by(account_models.User.created_at.asc()).first()
    if owner is None:
        raise HTTPException(status_code=404, detail="Initial tenant owner account not found")
    recent = db.query(account_models.PasswordResetToken.id).filter(
        account_models.PasswordResetToken.user_id == owner.id,
        account_models.PasswordResetToken.issued_at >= datetime.now(timezone.utc) - timedelta(minutes=2),
    ).first()
    if recent:
        raise HTTPException(status_code=429, detail="Please allow two minutes between owner invitations")
    raw = account_services.create_password_reset_token(db, owner)
    link = auth_router._build_reset_link(amo_slug=tenant.login_slug, token=raw)
    if not link:
        raise HTTPException(status_code=503, detail="Owner invitation link is not configured")
    auth_router._maybe_send_email(
        background_tasks, owner.email, "Set up your Venspera tenant administrator account",
        "Your organization has been provisioned. Use the secure one-time link to set your password: " + link,
        db=db, amo_id=tenant_id, user_id=str(owner.id), action_url=link,
    )
    services.audit(
        db, actor_user_id=_actor_id(user), action="tenant.owner_invitation.sent",
        tenant_id=tenant_id, entity_type="user", entity_id=owner.id,
        reason="Initial tenant administrator password setup",
        details={"delivery": "email", "email": owner.email},
    )
    db.commit()
    return {"tenant_id": tenant_id, "owner_email": owner.email, "status": "INVITATION_REQUESTED"}


@router.get("/tenants/{tenant_id}/storage-quota")
def tenant_storage_quota(
    tenant_id: str, db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    from . import storage_quota_service
    from amodb.apps.quality.tenant_security import set_postgres_tenant_context
    set_postgres_tenant_context(db, amo_id=tenant_id, user_id=_actor_id(user))
    if not db.get(account_models.AMO, tenant_id):
        raise HTTPException(status_code=404, detail="Tenant not found")
    return storage_quota_service.read_quota(db, tenant_id)


@router.post("/tenants/{tenant_id}/storage-quota")
def update_tenant_storage_quota(
    tenant_id: str, payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    from . import storage_quota_service
    from amodb.apps.quality.tenant_security import set_postgres_tenant_context
    set_postgres_tenant_context(db, amo_id=tenant_id, user_id=_actor_id(user))
    try:
        quota_bytes = payload.get("quota_bytes")
        if type(quota_bytes) is not int:
            raise ValueError("Provide an exact integer allocation in bytes")
        result = storage_quota_service.allocate(
            db, tenant_id=tenant_id, quota_bytes=quota_bytes,
            actor_id=_actor_id(user), reason=_reason(payload),
        )
        services.audit(db, actor_user_id=_actor_id(user), action="tenant.storage_quota.changed",
            tenant_id=tenant_id, reason=_reason(payload),
            details={"quota_bytes": quota_bytes, "generation": result["generation"]})
        db.commit()
        return result
    except (ValueError, TypeError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/tenants/{tenant_id}/storage-quota/reconcile")
def reconcile_tenant_storage_quota(
    tenant_id: str, payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    from . import storage_quota_service
    from amodb.apps.quality.tenant_security import set_postgres_tenant_context
    set_postgres_tenant_context(db, amo_id=tenant_id, user_id=_actor_id(user))
    try:
        result = storage_quota_service.reconcile(db, tenant_id=tenant_id, actor_id=_actor_id(user))
        services.audit(db, actor_user_id=_actor_id(user), action="tenant.storage_quota.reconciled",
            tenant_id=tenant_id, reason=_reason(payload), details={"drift": result["drift"]})
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/tenants/{tenant_id}/storage-quota/verify-objects")
def verify_tenant_retained_objects(
    tenant_id: str, payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    """Operator-triggered physical audit; refuses incomplete large scans."""
    from . import storage_quota_service
    from amodb.apps.quality.tenant_security import set_postgres_tenant_context
    set_postgres_tenant_context(db, amo_id=tenant_id, user_id=_actor_id(user))
    try:
        result = storage_quota_service.audit_retained_objects(
            db, tenant_id=tenant_id, actor_id=_actor_id(user),
            max_objects=payload.get("max_objects", 1000),
            verify_checksums=payload.get("verify_checksums", False),
        )
        services.audit(
            db, actor_user_id=_actor_id(user), action="tenant.storage_objects.physically_verified",
            tenant_id=tenant_id, reason=_reason(payload),
            details={"checked_objects": result["checked_objects"],
                     "physically_verified": result["physically_verified"],
                     "checksum_verified": result["checksum_verified"],
                     "ledger_drift": result["ledger_drift"]},
        )
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/tenants/{tenant_id}/activation-checklist")
def tenant_activation_checklist(
    tenant_id: str,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    from amodb.apps.accounts import services as account_services
    from . import storage_quota_service
    from amodb.apps.quality.tenant_security import set_postgres_tenant_context
    set_postgres_tenant_context(db, amo_id=tenant_id, user_id=_actor_id(user))
    from amodb import storage as shared_storage

    tenant = db.get(account_models.AMO, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    owner = db.query(account_models.User).filter(
        account_models.User.amo_id == tenant_id,
        account_models.User.staff_code.like("OWNER-%"),
        account_models.User.is_amo_admin.is_(True),
    ).order_by(account_models.User.created_at).first()
    licensed = account_services.get_billing_access_status(db, amo_id=tenant_id)
    quota = storage_quota_service.read_quota(db, tenant_id)
    # Configuration alone cannot establish that storage is reachable: exercise
    # the same S3 round-trip used by runtime health checks before claiming the
    # tenant is ready for paid production activation.
    try:
        shared_storage_health = shared_storage.health_check() if shared_storage.shared_storage_enabled() else {"ok": False}
    except Exception:
        shared_storage_health = {"ok": False}
    enabled_modules = db.query(account_models.ModuleSubscription).filter(
        account_models.ModuleSubscription.amo_id == tenant_id,
        account_models.ModuleSubscription.status.in_([
            account_models.ModuleSubscriptionStatus.ENABLED, account_models.ModuleSubscriptionStatus.TRIAL,
        ]),
    ).all()
    active_entitlements = account_services.resolve_entitlements(db, amo_id=tenant_id)
    licensed_modules = [
        item.module_code for item in enabled_modules
        if item.module_code in active_entitlements and (
            active_entitlements[item.module_code].is_unlimited
            or int(active_entitlements[item.module_code].limit or 0) > 0
        )
    ]
    checks = [
        {"key": "organization", "label": "Tenant organization created", "passed": bool(tenant.id)},
        {"key": "owner", "label": "Initial tenant administrator account assigned", "passed": owner is not None},
        {"key": "owner_setup", "label": "Active administrator completed password setup", "passed": bool(owner and owner.is_active and not owner.must_change_password)},
        {"key": "tenant_active", "label": "Organization is not suspended", "passed": bool(tenant.is_active)},
        {"key": "subscription", "label": "Effective commercial subscription permits access", "passed": bool(licensed.has_access)},
        {"key": "modules", "label": "At least one module is enabled", "passed": bool(enabled_modules)},
        {"key": "module_entitlements", "label": "Enabled modules have effective paid license entitlements", "passed": bool(licensed_modules)},
        {"key": "storage", "label": "Tenant byte quota explicitly allocated and reconciled",
         "passed": quota["quota_bytes"] > 0 and quota["integrity_state"] == "OK"},
        {"key": "shared_storage", "label": "Shared object storage verified reachable",
         "passed": bool(shared_storage_health.get("ok"))},
    ]
    return {
        "tenant_id": tenant_id, "ready": all(row["passed"] for row in checks),
        "checks": checks, "storage": quota,
    }


@router.get("/tenants/{tenant_id}")
def tenant_detail(tenant_id: str, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    try:
        return services.get_tenant_detail(db, tenant_id)
    except Exception as exc:
        _bad(exc, 404)


@router.patch("/tenants/{tenant_id}")
def update_tenant(tenant_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    amo = db.get(account_models.AMO, tenant_id)
    if not amo:
        raise HTTPException(status_code=404, detail="Tenant not found")
    for field in ["name", "contact_email", "contact_phone", "country"]:
        if field in payload:
            setattr(amo, field, payload[field])
    services.audit(db, actor_user_id=_actor_id(user), action="tenant.updated", tenant_id=tenant_id, entity_type="tenant", entity_id=tenant_id, reason=payload.get("reason"), details=payload)
    db.commit()
    return services.get_tenant_detail(db, tenant_id)


@router.post("/tenants/{tenant_id}/suspend")
def suspend_tenant(tenant_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.set_tenant_active(db, tenant_id=tenant_id, active=False, actor_id=_actor_id(user), reason=_reason(payload))
    except Exception as exc: _bad(exc)


@router.post("/tenants/{tenant_id}/reactivate")
def reactivate_tenant(tenant_id: str, payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.set_tenant_active(db, tenant_id=tenant_id, active=True, actor_id=_actor_id(user), reason=(payload or {}).get("reason") or "Platform reactivation")
    except Exception as exc: _bad(exc)


@router.post("/tenants/{tenant_id}/lock")
def lock_tenant(tenant_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.set_tenant_lock(db, tenant_id=tenant_id, locked=True, actor_id=_actor_id(user), reason=_reason(payload))
    except Exception as exc: _bad(exc)


@router.post("/tenants/{tenant_id}/unlock")
def unlock_tenant(tenant_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.set_tenant_lock(db, tenant_id=tenant_id, locked=False, actor_id=_actor_id(user), reason=_reason(payload))
    except Exception as exc: _bad(exc)


@router.post("/tenants/{tenant_id}/read-only")
def set_read_only(tenant_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.set_tenant_lock(db, tenant_id=tenant_id, locked=bool(payload.get("read_only", True)), actor_id=_actor_id(user), reason=_reason(payload))
    except Exception as exc: _bad(exc)




@router.post("/tenants/{tenant_id}/support-sessions")
def create_support_session(tenant_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    amo = db.get(account_models.AMO, tenant_id)
    if not amo or not amo.is_active:
        raise HTTPException(status_code=404, detail="Active tenant not found")
    access_level = str(payload.get("access_level") or "READ_ONLY").strip().upper()
    if access_level not in {"READ_ONLY", "ADMIN"}:
        raise HTTPException(status_code=422, detail="access_level must be READ_ONLY or ADMIN")
    reason = _reason(payload)
    status_value = "ACTIVE" if access_level == "READ_ONLY" else "PENDING"
    row = models.PlatformTenantSupportSession(
        tenant_id=tenant_id,
        platform_user_id=_actor_id(user),
        access_level=access_level,
        status=status_value,
        reason=reason,
        requested_by_user_id=_actor_id(user),
        expires_at=_support_session_expiry(payload),
        metadata_json={
            "requested_route": payload.get("requested_route"),
            "ticket_reference": payload.get("ticket_reference"),
        },
    )
    db.add(row)
    db.flush()
    services.audit(
        db,
        actor_user_id=_actor_id(user),
        action="support.session.created" if status_value == "ACTIVE" else "support.session.requested",
        tenant_id=tenant_id,
        entity_type="platform_tenant_support_session",
        entity_id=row.id,
        reason=reason,
        details={"access_level": access_level, "status": status_value, "expires_at": row.expires_at.isoformat()},
    )
    db.commit()
    db.refresh(row)
    return _support_session_payload(row)


@router.get("/support-sessions")
def list_support_sessions(tenant_id: str | None = None, status_filter: str | None = Query(None, alias="status"), db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    q = db.query(models.PlatformTenantSupportSession)
    if tenant_id:
        q = q.filter(models.PlatformTenantSupportSession.tenant_id == tenant_id)
    if status_filter:
        q = q.filter(models.PlatformTenantSupportSession.status == status_filter.strip().upper())
    rows = q.order_by(models.PlatformTenantSupportSession.created_at.desc()).limit(100).all()
    return {"items": [_support_session_payload(row) for row in rows]}


@router.get("/support-sessions/current")
def current_support_sessions(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    now = datetime.now(timezone.utc)
    rows = (
        db.query(models.PlatformTenantSupportSession)
        .filter(
            models.PlatformTenantSupportSession.platform_user_id == _actor_id(user),
            models.PlatformTenantSupportSession.status == "ACTIVE",
            models.PlatformTenantSupportSession.expires_at > now,
            models.PlatformTenantSupportSession.ended_at.is_(None),
        )
        .order_by(models.PlatformTenantSupportSession.created_at.desc())
        .all()
    )
    return {"items": [_support_session_payload(row) for row in rows]}


@router.post("/support-sessions/{session_id}/end")
def end_support_session(session_id: str, payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformTenantSupportSession, session_id)
    if not row or row.platform_user_id != _actor_id(user):
        raise HTTPException(status_code=404, detail="Support session not found")
    if row.status in {"ACTIVE", "PENDING"}:
        row.status = "ENDED"
        row.ended_at = datetime.now(timezone.utc)
        services.audit(
            db,
            actor_user_id=_actor_id(user),
            action="support.session.ended",
            tenant_id=row.tenant_id,
            entity_type="platform_tenant_support_session",
            entity_id=row.id,
            reason=(payload or {}).get("reason") or "Platform support session ended",
            details={"access_level": row.access_level},
        )
        db.commit()
        db.refresh(row)
    return _support_session_payload(row)

@router.get("/tenants/{tenant_id}/insights")
def tenant_insights(tenant_id: str, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.get_tenant_detail(db, tenant_id)


@router.get("/tenants/{tenant_id}/resource-usage")
def tenant_resources(tenant_id: str, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.latest_resource_snapshot(db, tenant_id) or {"tenant_id": tenant_id, "empty": True}


@router.get("/modules/catalog")
def modules_catalog(user=Depends(require_platform_superuser)):
    """Canonical list of shipped modules the superadmin activates per tenant."""
    return {"items": services.module_catalog()}


@router.get("/tenants/{tenant_id}/entitlements")
def tenant_entitlements(tenant_id: str, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.get_tenant_detail(db, tenant_id).get("modules", [])


@router.patch("/tenants/{tenant_id}/entitlements")
def patch_tenant_entitlements(tenant_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.update_entitlements(db, tenant_id=tenant_id, payload=payload, actor_id=_actor_id(user))
    except Exception as exc: _bad(exc)


@router.get("/users")
def users(q: str | None = None, tenant_id: str | None = None, status_filter: str | None = Query(None, alias="status"), limit: int = 50, offset: int = 0, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.list_users(db, q=q, tenant_id=tenant_id, status_filter=status_filter, limit=limit, offset=offset)


@router.get("/users/activity/summary")
def user_activity_summary(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.analytics_summary(db)


@router.get("/users/heatmap")
def user_heatmap(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return {"items": [], "note": "Login heatmap starts filling from login activity events going forward."}


@router.get("/users/{user_id}")
def user_detail(user_id: str, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    result = services.list_users(db, q=user_id, limit=1)
    return result["items"][0] if result["items"] else {"id": user_id, "found": False}


@router.post("/users/{user_id}/disable")
def disable_user(user_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.set_user_active(db, user_id=user_id, active=False, actor_id=_actor_id(user), reason=_reason(payload))
    except Exception as exc: _bad(exc)


@router.post("/users/{user_id}/enable")
def enable_user(user_id: str, payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.set_user_active(db, user_id=user_id, active=True, actor_id=_actor_id(user), reason=(payload or {}).get("reason") or "Platform enable")
    except Exception as exc: _bad(exc)


@router.post("/users/{user_id}/revoke-sessions")
def revoke_sessions(user_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.revoke_user_sessions(db, user_id=user_id, actor_id=_actor_id(user), reason=_reason(payload))
    except Exception as exc: _bad(exc)


@router.post("/users/{user_id}/force-password-reset")
def force_password_reset(user_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.revoke_user_sessions(db, user_id=user_id, actor_id=_actor_id(user), reason=_reason(payload)) | {"must_change_password": True}
    except Exception as exc: _bad(exc)


@router.get("/users/{user_id}/activity")
def user_activity(user_id: str, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return {"items": [], "note": "Activity event timeline is collected going forward."}


@router.get("/billing/summary")
def platform_billing_summary(data_mode: str = "REAL", db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.billing_summary(db, data_mode=data_mode)


@router.get("/billing/control")
def platform_billing_control(data_mode: str = "REAL", db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.billing_control_summary(db, data_mode=data_mode)


@router.post("/billing/maintenance/run")
def platform_billing_maintenance_run(payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    payload = payload or {}
    return services.run_billing_maintenance_now(db, actor_id=_actor_id(user), reason=str(payload.get("reason") or "manual billing maintenance run"))


@router.get("/billing/mrr-growth")
def platform_billing_mrr(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return {"items": [], "source": "billing_rollups"}


@router.get("/billing/revenue-by-plan")
def revenue_by_plan(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    rows = db.query(account_models.CatalogSKU).all()
    return {"items": [{"plan_code": r.code, "amount_cents": r.amount_cents, "currency": r.currency, "term": getattr(r.term, "value", str(r.term))} for r in rows]}


@router.get("/billing/invoices")
def billing_invoices(
    data_mode: str = "REAL", tenant_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return services.list_invoices(
            db, data_mode=data_mode, tenant_id=tenant_id, status_filter=status_filter,
            q=q, limit=limit, offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/billing/invoices/export")
def export_platform_invoices(
    tenant_id: str, data_mode: str = "REAL",
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    """Export one explicitly selected tenant without relying on browser-side pagination."""
    import csv
    import io
    from fastapi.responses import Response

    if not db.get(account_models.AMO, tenant_id):
        raise HTTPException(status_code=404, detail="Tenant not found")
    rows = services.list_invoices(
        db, data_mode=data_mode, tenant_id=tenant_id, limit=200, offset=0,
    )
    # The export queries the complete tenant history, not the first UI page.
    from amodb.apps.accounts import services as account_services
    invoice_rows = db.query(account_models.BillingInvoice).join(
        account_models.AMO, account_models.BillingInvoice.amo_id == account_models.AMO.id,
    ).filter(account_models.BillingInvoice.amo_id == tenant_id)
    if str(data_mode).upper() == "REAL":
        invoice_rows = invoice_rows.filter(account_models.AMO.is_demo.is_(False))
    elif str(data_mode).upper() == "DEMO":
        invoice_rows = invoice_rows.filter(account_models.AMO.is_demo.is_(True))
    elif str(data_mode).upper() != "ALL":
        raise HTTPException(status_code=422, detail="Invalid billing data mode")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["invoice", "tenant_id", "amount_minor_units", "currency", "status", "issued_at", "due_at", "paid_at"])
    for row in invoice_rows.order_by(account_models.BillingInvoice.created_at.desc()).yield_per(250):
        writer.writerow([
            account_services.format_invoice_number(row), row.amo_id, row.amount_cents,
            row.currency, row.status.value, row.issued_at, row.due_at, row.paid_at,
        ])
    return Response(
        output.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="venspera-tenant-invoices.csv"'},
    )


@router.get("/billing/invoices/{invoice_id}")
def platform_invoice_detail(
    invoice_id: str,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    invoice = db.get(account_models.BillingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return services._invoice_payload(invoice)


@router.get("/billing/invoices/{invoice_id}/document")
def platform_invoice_document(
    invoice_id: str,
    format: str = Query("pdf", pattern="^(pdf|html)$"),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    from fastapi.responses import HTMLResponse, Response
    from amodb.apps.accounts import router_billing as renderer

    invoice = db.get(account_models.BillingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if format == "pdf":
        return Response(
            renderer._render_invoice_pdf(db, invoice), media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{renderer._invoice_filename(invoice, "pdf")}"'},
        )
    return HTMLResponse(
        renderer._render_invoice_html(db, invoice),
        headers={"Content-Disposition": f'attachment; filename="{renderer._invoice_filename(invoice, "html")}"'},
    )


@router.post("/billing/invoices/{invoice_id}/void")
def platform_void_invoice(
    invoice_id: str, payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    try:
        return services.void_invoice(
            db, invoice_id=invoice_id, actor_id=_actor_id(user), reason=_reason(payload),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc



@router.get("/billing/tenants/{tenant_id}")
def billing_tenant_detail(tenant_id: str, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.get_tenant_detail(db, tenant_id)


@router.post("/billing/invoices/{invoice_id}/mark-paid")
def mark_invoice_paid(invoice_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try:
        return services.mark_invoice_paid(
            db, invoice_id=invoice_id, actor_id=_actor_id(user),
            reason=_reason(payload),
            payment_reference=str(payload.get("payment_reference") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/billing/tenants/{tenant_id}/manual-invoice")
def manual_invoice(tenant_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    amount_cents = payload.get("amount_cents")
    if amount_cents is None and payload.get("amount") is not None:
        try:
            amount_cents = int(round(float(payload["amount"]) * 100))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="amount must be a number")
    if amount_cents is None:
        raise HTTPException(status_code=422, detail="amount_cents (or amount) is required")
    due_at = None
    raw_due = payload.get("due_at")
    if isinstance(raw_due, str) and raw_due.strip():
        try:
            due_at = datetime.fromisoformat(raw_due.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail="due_at must be an ISO-8601 datetime")
    try:
        return services.create_manual_invoice(
            db,
            tenant_id=tenant_id,
            amount_cents=int(amount_cents),
            currency=str(payload.get("currency") or "USD"),
            description=payload.get("description"),
            mark_paid=bool(payload.get("mark_paid")),
            due_at=due_at,
            actor_id=_actor_id(user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        _bad(exc)


@router.post("/billing/tenants/{tenant_id}/override-entitlements")
def override_entitlements(tenant_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    return patch_tenant_entitlements(tenant_id, payload, db, user)


@router.post("/billing/tenants/{tenant_id}/lock")
def billing_lock(tenant_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    return lock_tenant(tenant_id, payload, db, user)


@router.post("/billing/tenants/{tenant_id}/unlock")
def billing_unlock(tenant_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    return unlock_tenant(tenant_id, payload, db, user)


@router.get("/analytics/summary")
def analytics_summary(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.analytics_summary(db)


@router.get("/analytics/dau")
def analytics_dau(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"value": services.analytics_summary(db)["dau"]}
@router.get("/analytics/wau")
def analytics_wau(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"value": services.analytics_summary(db)["wau"]}
@router.get("/analytics/mau")
def analytics_mau(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"value": services.analytics_summary(db)["mau"]}
@router.get("/analytics/module-usage")
def module_usage(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": []}
@router.get("/analytics/tenant-heatmap")
def tenant_heatmap(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": metrics.live_summary().get("noisiest_tenants", [])}
@router.get("/analytics/login-heatmap")
def login_heatmap(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": []}
@router.get("/analytics/api-volume")
def api_volume(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return metrics.live_summary()
@router.get("/analytics/slow-routes")
def slow_routes(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": metrics.live_summary().get("slowest_routes", [])}
@router.get("/analytics/error-routes")
def error_routes(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": [r for r in metrics.live_summary().get("slowest_routes", []) if r.get("server_error_count", 0) > 0]}
@router.get("/analytics/top-tenants")
def top_tenants(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": metrics.live_summary().get("noisiest_tenants", [])}


@router.get("/metrics/summary")
def metrics_summary(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return metrics.live_summary()


@router.get("/metrics/route-throughput")
def route_throughput(minutes: int = 60, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return metrics.live_summary()


@router.get("/metrics/tenants/{tenant_id}")
def tenant_metrics(tenant_id: str, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return {"tenant_id": tenant_id, "summary": metrics.live_summary()}


@router.post("/metrics/run-throughput-probe")
def run_throughput_probe(payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    return services.create_command_job(db, payload={"command_name": "RUN_THROUGHPUT_PROBE", "reason": (payload or {}).get("reason") or "Manual throughput probe"}, actor_id=_actor_id(user))


@router.get("/commands/catalog")
def commands_catalog(user=Depends(require_platform_superuser)):
    return {"items": services.command_catalog_payload()}


@router.post("/commands")
def commands_create(payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.job_payload(services.create_command_job(db, payload=payload, actor_id=_actor_id(user)))
    except Exception as exc: _bad(exc)


@router.get("/commands")
def commands_list(limit: int = 50, offset: int = 0, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.list_jobs(db, limit=limit, offset=offset)


@router.get("/commands/{job_id}")
def command_get(job_id: str, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformCommandJob, job_id)
    if not row: raise HTTPException(status_code=404, detail="Command job not found")
    return services.job_payload(row)


@router.post("/commands/{job_id}/approve")
def command_approve(job_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformCommandJob, job_id)
    if not row: raise HTTPException(status_code=404, detail="Command job not found")
    row.status = "APPROVED"; row.approved_by_user_id = _actor_id(user); services.add_job_event(db, row, "APPROVED", payload.get("reason") or "Approved")
    services.execute_command_job(db, row, actor_id=_actor_id(user)); db.commit(); return services.job_payload(row)


@router.post("/commands/{job_id}/cancel")
def command_cancel(job_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformCommandJob, job_id)
    if not row: raise HTTPException(status_code=404, detail="Command job not found")
    row.status = "CANCELLED"; services.add_job_event(db, row, "CANCELLED", payload.get("reason") or "Cancelled"); db.commit(); return services.job_payload(row)


@router.post("/commands/{job_id}/retry")
def command_retry(job_id: str, payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformCommandJob, job_id)
    if not row: raise HTTPException(status_code=404, detail="Command job not found")
    services.execute_command_job(db, row, actor_id=_actor_id(user)); db.commit(); return services.job_payload(row)


@router.post("/diagnostics/run")
def diagnostics_run(payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    return services.job_payload(services.create_command_job(db, payload={"command_name": (payload or {}).get("command_name") or "RUN_PLATFORM_HEALTH_PROBE", "reason": (payload or {}).get("reason") or "Manual diagnostics"}, actor_id=_actor_id(user)))


@router.get("/security/summary")
def security_summary(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return services.security_summary(db)
@router.get("/security/alerts")
def security_alerts(limit: int = 50, offset: int = 0, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return services.list_security_alerts(db, limit=limit, offset=offset)
@router.get("/security/failed-logins")
def failed_logins(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": []}
@router.get("/security/suspicious-ips")
def suspicious_ips(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": []}
@router.get("/security/cross-tenant-denials")
def cross_tenant_denials(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": []}
@router.get("/security/mfa-coverage")
def mfa_coverage(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"coverage_percent": services.security_summary(db).get("mfa_coverage_percent")}
@router.get("/security/audit-log")
def audit_log(limit: int = 50, offset: int = 0, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    q = db.query(models.PlatformAuditLog).order_by(models.PlatformAuditLog.created_at.desc()); total = q.count()
    return {"items": [{"id": r.id, "action": r.action, "tenant_id": r.tenant_id, "actor_user_id": r.actor_user_id, "entity_type": r.entity_type, "entity_id": r.entity_id, "reason": r.reason, "created_at": r.created_at} for r in q.offset(offset).limit(min(limit,200)).all()], "total": total}
@router.get("/security/tenant-risk")
def tenant_risk(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": []}
@router.post("/security/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformSecurityAlert, alert_id)
    if not row: raise HTTPException(status_code=404, detail="Alert not found")
    row.status = "ACKNOWLEDGED"; row.acknowledged_at = services.now_utc(); row.acknowledged_by = _actor_id(user); db.commit(); return {"id": row.id, "status": row.status}
@router.post("/security/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str, payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformSecurityAlert, alert_id)
    if not row: raise HTTPException(status_code=404, detail="Alert not found")
    row.status = "RESOLVED"; row.resolved_at = services.now_utc(); row.resolved_by = _actor_id(user); db.commit(); return {"id": row.id, "status": row.status}


@router.get("/integrations/summary")
def integrations_summary(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return services.integration_summary(db)
@router.get("/integrations/api-keys")
def api_keys(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": services.list_api_keys(db)}
@router.post("/integrations/api-keys")
def api_key_create(payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.create_api_key(db, name=payload.get("name") or "Platform key", scopes=payload.get("scopes") or [], actor_id=_actor_id(user))
    except Exception as exc: _bad(exc)
@router.post("/integrations/api-keys/{key_id}/revoke")
def api_key_revoke(key_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.revoke_api_key(db, key_id=key_id, actor_id=_actor_id(user), reason=_reason(payload))
    except Exception as exc: _bad(exc)
@router.post("/integrations/api-keys/{key_id}/rotate")
def api_key_rotate(key_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    return services.job_payload(services.create_command_job(db, payload={"command_name":"ROTATE_TENANT_API_KEY", "tenant_id": payload.get("tenant_id"), "reason": _reason(payload)}, actor_id=_actor_id(user)))
@router.get("/integrations/webhooks")
def webhooks(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": services.list_webhooks(db)}
@router.post("/integrations/webhooks")
def webhook_create(payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.create_webhook(db, payload=payload, actor_id=_actor_id(user))
    except Exception as exc: _bad(exc)
@router.patch("/integrations/webhooks/{webhook_id}")
def webhook_update(webhook_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)): return {"id": webhook_id, "updated": False, "detail": "Use pause/resume/delete specific actions."}
@router.post("/integrations/webhooks/{webhook_id}/test")
def webhook_test(webhook_id: str, payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)): return services.job_payload(services.create_command_job(db, payload={"command_name":"RUN_NETWORK_DIAGNOSTIC", "reason":"Webhook test diagnostic"}, actor_id=_actor_id(user)))
@router.post("/integrations/webhooks/{webhook_id}/pause")
def webhook_pause(webhook_id: str, payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformWebhookConfig, webhook_id)
    if row: row.status = "PAUSED"; db.commit()
    return {"id": webhook_id, "status": getattr(row, "status", "NOT_FOUND")}
@router.post("/integrations/webhooks/{webhook_id}/resume")
def webhook_resume(webhook_id: str, payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformWebhookConfig, webhook_id)
    if row: row.status = "ACTIVE"; db.commit()
    return {"id": webhook_id, "status": getattr(row, "status", "NOT_FOUND")}
@router.delete("/integrations/webhooks/{webhook_id}")
def webhook_delete(webhook_id: str, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformWebhookConfig, webhook_id)
    if row: row.status = "DELETED"; db.commit()
    return {"id": webhook_id, "status": getattr(row, "status", "NOT_FOUND")}
@router.get("/integrations/webhooks/{webhook_id}/deliveries")
def webhook_deliveries(webhook_id: str, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    rows = db.query(models.PlatformWebhookDeliveryLog).filter(models.PlatformWebhookDeliveryLog.webhook_id == webhook_id).order_by(models.PlatformWebhookDeliveryLog.created_at.desc()).limit(50).all()
    return {"items": [{"id": r.id, "event_type": r.event_type, "status_code": r.status_code, "success": r.success, "duration_ms": r.duration_ms, "attempt_count": r.attempt_count, "error_detail": r.error_detail, "created_at": r.created_at} for r in rows]}
@router.get("/integrations/providers")
def providers(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": services.list_providers(db)}
@router.patch("/integrations/providers/{provider_id}")
def provider_update(provider_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)): return {"id": provider_id, "status": "NOT_CONFIGURED", "detail": "Provider secrets are stored redacted only when configured by a provider-specific workflow."}
@router.post("/integrations/providers/{provider_id}/health-check")
def provider_health(provider_id: str, payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)): return services.job_payload(services.create_command_job(db, payload={"command_name":"RUN_NETWORK_DIAGNOSTIC", "reason":"Provider health check"}, actor_id=_actor_id(user)))


@router.get("/infrastructure/live")
def infrastructure_live(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    """Instant host/DB metrics for ~2s real-time polling (Task-Manager style)."""
    return services.live_system_metrics(db)


@router.get("/diagnostics/ping")
def diagnostics_ping(user=Depends(require_platform_superuser)):
    """Tiny response so the browser can measure control-plane round-trip latency."""
    return {"ok": True, "server_time": services.now_utc().isoformat()}


@router.post("/diagnostics/db-check")
def diagnostics_db_check(payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    """On-demand database connection speed/latency check."""
    samples = (payload or {}).get("samples")
    try:
        samples = int(samples) if samples is not None else 5
    except (TypeError, ValueError):
        samples = 5
    return services.database_latency_check(db, samples=samples)


_SPEEDTEST_MAX_BYTES = 64 * 1024 * 1024


@router.get("/diagnostics/speedtest/download")
def diagnostics_speedtest_download(bytes: int = 8_000_000, user=Depends(require_platform_superuser)):
    """Stream incompressible random bytes so the browser can measure download throughput."""
    import os as _os
    from fastapi.responses import StreamingResponse

    size = max(1024, min(int(bytes or 0), _SPEEDTEST_MAX_BYTES))
    chunk_size = 64 * 1024

    def _generate():
        remaining = size
        while remaining > 0:
            piece = _os.urandom(min(chunk_size, remaining))
            remaining -= len(piece)
            yield piece

    headers = {
        "Cache-Control": "no-store, no-transform",
        "X-Accel-Buffering": "no",
        "X-Speedtest-Bytes": str(size),
    }
    return StreamingResponse(_generate(), media_type="application/octet-stream", headers=headers)


@router.post("/diagnostics/speedtest/upload")
async def diagnostics_speedtest_upload(request: Request, user=Depends(require_platform_superuser)):
    """Consume an uploaded payload and report received size + duration for upload throughput."""
    import time as _time

    started = _time.perf_counter()
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > _SPEEDTEST_MAX_BYTES:
            break
    elapsed = _time.perf_counter() - started
    return {"bytes_received": total, "server_ms": round(elapsed * 1000, 2)}


@router.post("/diagnostics/network/internet")
def diagnostics_network_internet(payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    """Run a server -> internet speed test (provider/ISP SLA) and log it."""
    payload = payload or {}
    kwargs: dict[str, Any] = {}
    if payload.get("download_bytes"):
        kwargs["download_bytes"] = int(payload["download_bytes"])
    if payload.get("upload_bytes"):
        kwargs["upload_bytes"] = int(payload["upload_bytes"])
    if payload.get("host"):
        requested_host = network_diagnostics._validated_host(str(payload["host"]))
        configured_host = network_diagnostics._validated_host(network_diagnostics.DEFAULT_SPEEDTEST_HOST)
        if requested_host != configured_host:
            raise HTTPException(status_code=422, detail="Speed-test target is controlled by PLATFORM_NET_SPEEDTEST_HOST")
        kwargs["host"] = requested_host
    try:
        result = network_diagnostics.run_internet_speedtest(**kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    network_diagnostics.persist_probe(db, scenario="server_internet", source="manual", data=result)
    return result


@router.post("/diagnostics/network/database")
def diagnostics_network_database(payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    """Run a server <-> database latency/throughput test and log it."""
    payload = payload or {}
    kwargs: dict[str, Any] = {}
    if payload.get("payload_bytes"):
        kwargs["payload_bytes"] = int(payload["payload_bytes"])
    result = network_diagnostics.run_database_throughput(db, **kwargs)
    network_diagnostics.persist_probe(db, scenario="server_database", source="manual", data=result)
    return result


@router.post("/diagnostics/network/client")
def diagnostics_network_client(payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    """Log a browser-measured result (client -> portal or client -> internet)."""
    scenario = str(payload.get("scenario") or "").strip()
    if scenario not in {"client_portal", "client_internet"}:
        raise HTTPException(status_code=422, detail="scenario must be client_portal or client_internet")

    def _to_bps(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    data = {
        "target": payload.get("target"),
        "ok": bool(payload.get("ok", True)),
        "latency_ms": _to_bps(payload.get("latency_ms")),
        "jitter_ms": _to_bps(payload.get("jitter_ms")),
        "download_bps": _to_bps(payload.get("download_bps")),
        "upload_bps": _to_bps(payload.get("upload_bps")),
        "download_bytes": payload.get("download_bytes"),
        "upload_bytes": payload.get("upload_bytes"),
        "error": payload.get("error"),
        "details": payload.get("details") if isinstance(payload.get("details"), dict) else None,
    }
    row = network_diagnostics.persist_probe(db, scenario=scenario, source="client", data=data)
    return {"id": row.id, "scenario": scenario, "captured_at": row.captured_at}


@router.get("/diagnostics/network/history")
def diagnostics_network_history(window: str = "24h", scenario: str | None = None, sla_download_mbps: float | None = None, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    """Historical network diagnostics with 24h / 7d / 30d aggregates + SLA breaches."""
    return network_diagnostics.history(db, window=window, scenario=scenario, sla_download_mbps=sla_download_mbps)


@router.get("/infrastructure/summary")
def infrastructure_summary(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return services.infrastructure_summary(db)
@router.get("/infrastructure/feature-flags")
def feature_flags(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": services.list_feature_flags(db)}
@router.post("/infrastructure/feature-flags")
def feature_flag_create(payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.create_feature_flag(db, payload=payload, actor_id=_actor_id(user))
    except Exception as exc: _bad(exc)
@router.patch("/infrastructure/feature-flags/{flag_id}")
def feature_flag_update(flag_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformFeatureFlag, flag_id)
    if not row: raise HTTPException(status_code=404, detail="Feature flag not found")
    if "enabled" in payload: row.enabled = bool(payload["enabled"])
    row.updated_by = _actor_id(user); db.commit(); return {"id": row.id, "enabled": row.enabled}
@router.delete("/infrastructure/feature-flags/{flag_id}")
def feature_flag_delete(flag_id: str, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformFeatureFlag, flag_id)
    if row: db.delete(row); db.commit()
    return {"id": flag_id, "deleted": bool(row)}
@router.get("/infrastructure/maintenance")
def maintenance_windows(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    rows = db.query(models.PlatformMaintenanceWindow).order_by(models.PlatformMaintenanceWindow.created_at.desc()).limit(50).all()
    return {"items": [{"id": r.id, "title": r.title, "status": r.status, "starts_at": r.starts_at, "ends_at": r.ends_at, "impact_level": r.impact_level} for r in rows]}
@router.post("/infrastructure/maintenance")
def maintenance_create(payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = models.PlatformMaintenanceWindow(title=payload.get("title") or "Maintenance window", description=payload.get("description"), impact_level=payload.get("impact_level") or "LOW", created_by=_actor_id(user))
    db.add(row); db.commit(); return {"id": row.id, "status": row.status}
@router.post("/infrastructure/maintenance/{window_id}/start")
def maintenance_start(window_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformMaintenanceWindow, window_id)
    if row: row.status = "ACTIVE"; db.commit()
    return {"id": window_id, "status": getattr(row, "status", "NOT_FOUND")}
@router.post("/infrastructure/maintenance/{window_id}/complete")
def maintenance_complete(window_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformMaintenanceWindow, window_id)
    if row: row.status = "COMPLETED"; db.commit()
    return {"id": window_id, "status": getattr(row, "status", "NOT_FOUND")}
@router.post("/infrastructure/maintenance/{window_id}/cancel")
def maintenance_cancel(window_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformMaintenanceWindow, window_id)
    if row: row.status = "CANCELLED"; db.commit()
    return {"id": window_id, "status": getattr(row, "status", "NOT_FOUND")}
@router.get("/infrastructure/snapshots")
def infrastructure_snapshots(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    rows = db.query(models.PlatformInfrastructureSnapshot).order_by(models.PlatformInfrastructureSnapshot.captured_at.desc()).limit(50).all()
    return {"items": [{"id": r.id, "captured_at": r.captured_at, "status": r.status, "cpu_percent": r.cpu_percent, "memory_percent": r.memory_percent, "api_requests_per_minute": r.api_requests_per_minute} for r in rows]}
@router.post("/infrastructure/diagnostics")
def infrastructure_diagnostics(payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)): return diagnostics_run(payload or {"reason":"Infrastructure diagnostics"}, db, user)
@router.post("/infrastructure/reset-api-tokens")
def reset_api_tokens(payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)): return services.job_payload(services.create_command_job(db, payload={"command_name":"INFRA_RESET_GLOBAL_API_TOKENS", "reason": _reason(payload)}, actor_id=_actor_id(user)))
@router.post("/infrastructure/failover-database")
def failover_database(payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)): return services.job_payload(services.create_command_job(db, payload={"command_name":"INFRA_FAILOVER_DATABASE", "reason": _reason(payload)}, actor_id=_actor_id(user)))


@router.get("/support/summary")
def support_summary(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return services.support_summary(db)
@router.get("/support/tickets")
def support_tickets(limit: int = 50, offset: int = 0, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return services.list_support_tickets(db, limit=limit, offset=offset)
@router.get("/support/integrations")
def support_integrations(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": services.support_summary(db)["providers"]}
@router.patch("/support/integrations/{provider}")
def support_integration_update(provider: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)): return {"provider": provider, "status": "NOT_CONFIGURED"}
@router.post("/support/integrations/{provider}/test")
def support_integration_test(provider: str, payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)): return diagnostics_run({"reason": f"Support integration test: {provider}"}, db, user)


@router.post("/support-sessions")
def support_session_start(payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.start_support_session(db, tenant_id=payload.get("tenant_id"), actor_id=_actor_id(user), reason=_reason(payload), mode=payload.get("mode") or "READ_ONLY", minutes=int(payload.get("minutes") or 30))
    except Exception as exc: _bad(exc)
@router.get("/support-sessions")
def support_session_list(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": services.list_support_sessions(db)}
@router.post("/support-sessions/{session_id}/end")
def support_session_end(session_id: str, payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformSupportSession, session_id)
    if not row: raise HTTPException(status_code=404, detail="Support session not found")
    row.status = "ENDED"; row.ended_at = services.now_utc(); db.commit(); return {"id": row.id, "status": row.status}


@router.get("/resources/summary")
def resources_summary(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return services.resources_summary(db)
@router.get("/resources/tenants")
def resources_tenants(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return services.resources_summary(db)
@router.get("/resources/tenants/{tenant_id}")
def resources_tenant(tenant_id: str, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return services.latest_resource_snapshot(db, tenant_id) or {"tenant_id": tenant_id, "empty": True}
@router.get("/resources/trends")
def resources_trends(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": []}


@router.get("/notifications/summary")
def notifications_summary(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return services.notifications_summary(db)
@router.get("/notifications")
def notifications_list(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)): return {"items": services.list_notifications(db)}
@router.post("/notifications/{notification_id}/read")
def notification_read(notification_id: str, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    row = db.get(models.PlatformNotification, notification_id)
    if row: row.read_at = services.now_utc(); db.commit()
    return {"id": notification_id, "read": bool(row)}
@router.post("/notifications/read-all")
def notifications_read_all(db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    db.query(models.PlatformNotification).filter(models.PlatformNotification.read_at.is_(None)).update({"read_at": services.now_utc()}, synchronize_session=False); db.commit(); return {"ok": True}
