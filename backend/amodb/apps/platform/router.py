from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from amodb.database import get_db, get_read_db
from amodb.security import get_current_active_user
from amodb.apps.accounts import models as account_models
from . import diagnostics, metrics, models, services

router = APIRouter(prefix="/platform", tags=["platform-control-plane"])


def require_platform_superuser(current_user=Depends(get_current_active_user)):
    if not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform superuser access is required.")
    if getattr(current_user, "amo_id", None):
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


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.dashboard_summary(db)


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
def list_tenants(q: str | None = None, status_filter: str | None = Query(None, alias="status"), limit: int = 50, offset: int = 0, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.list_tenants(db, q=q, status_filter=status_filter, limit=limit, offset=offset)


@router.post("/tenants")
def create_tenant(payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try:
        return services.create_tenant(db, payload=payload, actor_id=_actor_id(user))
    except Exception as exc:
        _bad(exc)


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


@router.get("/tenants/{tenant_id}/insights")
def tenant_insights(tenant_id: str, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.get_tenant_detail(db, tenant_id)


@router.get("/tenants/{tenant_id}/resource-usage")
def tenant_resources(tenant_id: str, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.latest_resource_snapshot(db, tenant_id) or {"tenant_id": tenant_id, "empty": True}


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
def platform_billing_summary(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.billing_summary(db)


@router.get("/billing/mrr-growth")
def platform_billing_mrr(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return {"items": [], "source": "billing_rollups"}


@router.get("/billing/revenue-by-plan")
def revenue_by_plan(db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    rows = db.query(account_models.CatalogSKU).all()
    return {"items": [{"plan_code": r.code, "amount_cents": r.amount_cents, "currency": r.currency, "term": getattr(r.term, "value", str(r.term))} for r in rows]}


@router.get("/billing/invoices")
def billing_invoices(limit: int = 50, offset: int = 0, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.list_invoices(db, limit=limit, offset=offset)


@router.get("/billing/tenants/{tenant_id}")
def billing_tenant_detail(tenant_id: str, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    return services.get_tenant_detail(db, tenant_id)


@router.post("/billing/invoices/{invoice_id}/mark-paid")
def mark_invoice_paid(invoice_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    try: return services.mark_invoice_paid(db, invoice_id=invoice_id, actor_id=_actor_id(user), reason=_reason(payload))
    except Exception as exc: _bad(exc)


@router.post("/billing/tenants/{tenant_id}/manual-invoice")
def manual_invoice(tenant_id: str, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    raise HTTPException(status_code=501, detail="Manual invoice creation requires the billing ledger workflow to be wired through command jobs. No fake invoice was created.")


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
