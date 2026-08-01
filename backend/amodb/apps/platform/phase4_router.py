from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.database import get_db, get_read_db
from amodb.apps.accounts import models as account_models

from . import models, services
from .commercial_services import normalize_data_mode
from .router import require_platform_superuser


router = APIRouter(prefix="/phase4", tags=["platform-phase4-operations"])


def _actor(user: Any) -> str:
    return str(getattr(user, "id", ""))


def _reason(payload: dict[str, Any]) -> str:
    value = str(payload.get("reason") or "").strip()
    if not value:
        raise HTTPException(status_code=422, detail="A reason is required.")
    return value


def _tenant_name(db: Session, tenant_id: str | None) -> str | None:
    if not tenant_id:
        return None
    tenant = db.get(account_models.AMO, tenant_id)
    return tenant.name if tenant else None


def _alert_payload(db: Session, row: models.PlatformSecurityAlert) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "description": row.description,
        "category": row.category,
        "severity": row.severity,
        "status": row.status,
        "tenant_id": row.tenant_id,
        "tenant_name": _tenant_name(db, row.tenant_id),
        "actor_user_id": row.actor_user_id,
        "source_ip": row.source_ip,
        "user_agent": row.user_agent,
        "evidence": row.evidence_json or {},
        "created_at": row.created_at,
        "acknowledged_at": row.acknowledged_at,
        "acknowledged_by": row.acknowledged_by,
        "resolved_at": row.resolved_at,
        "resolved_by": row.resolved_by,
    }


def _apply_environment_scope(query, tenant_column, *, data_mode: str):
    mode = normalize_data_mode(data_mode)
    return (
        query.outerjoin(account_models.AMO, account_models.AMO.id == tenant_column)
        .filter(
            or_(
                tenant_column.is_(None),
                account_models.AMO.is_demo.is_(mode == "DEMO"),
            )
        )
    ), mode


@router.get("/security/alerts")
def security_alerts(
    data_mode: str = Query("REAL"),
    q: str | None = None,
    severity: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    tenant_id: str | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        query, mode = _apply_environment_scope(
            db.query(models.PlatformSecurityAlert),
            models.PlatformSecurityAlert.tenant_id,
            data_mode=data_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                models.PlatformSecurityAlert.title.ilike(like),
                models.PlatformSecurityAlert.description.ilike(like),
                models.PlatformSecurityAlert.category.ilike(like),
                models.PlatformSecurityAlert.source_ip.ilike(like),
            )
        )
    if severity:
        query = query.filter(models.PlatformSecurityAlert.severity == severity.strip().upper())
    if status_filter:
        query = query.filter(models.PlatformSecurityAlert.status == status_filter.strip().upper())
    if tenant_id:
        tenant = db.get(account_models.AMO, tenant_id)
        if not tenant or bool(tenant.is_demo) != (mode == "DEMO"):
            raise HTTPException(status_code=404, detail="Tenant not found in the selected environment")
        query = query.filter(models.PlatformSecurityAlert.tenant_id == tenant_id)
    total = query.count()
    rows = query.order_by(models.PlatformSecurityAlert.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "items": [_alert_payload(db, row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "data_mode": mode,
    }


@router.post("/security/alerts/{alert_id}/resolve")
def resolve_security_alert(
    alert_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    row = db.get(models.PlatformSecurityAlert, alert_id)
    if not row:
        raise HTTPException(status_code=404, detail="Security alert not found")
    reason = _reason(payload)
    row.status = "RESOLVED"
    row.resolved_at = datetime.now(timezone.utc)
    row.resolved_by = _actor(user)
    evidence = dict(row.evidence_json or {})
    evidence["resolution_reason"] = reason
    row.evidence_json = evidence
    services.audit(
        db,
        actor_user_id=_actor(user),
        action="security.alert.resolved",
        tenant_id=row.tenant_id,
        entity_type="platform_security_alert",
        entity_id=row.id,
        reason=reason,
        details={"severity": row.severity, "category": row.category},
    )
    db.commit()
    db.refresh(row)
    return _alert_payload(db, row)


@router.get("/security/audit")
def security_audit(
    data_mode: str = Query("REAL"),
    q: str | None = None,
    tenant_id: str | None = None,
    action: str | None = None,
    limit: int = Query(100, ge=1, le=300),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        query, mode = _apply_environment_scope(
            db.query(models.PlatformAuditLog),
            models.PlatformAuditLog.tenant_id,
            data_mode=data_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                models.PlatformAuditLog.action.ilike(like),
                models.PlatformAuditLog.reason.ilike(like),
                models.PlatformAuditLog.entity_type.ilike(like),
                models.PlatformAuditLog.entity_id.ilike(like),
            )
        )
    if tenant_id:
        tenant = db.get(account_models.AMO, tenant_id)
        if not tenant or bool(tenant.is_demo) != (mode == "DEMO"):
            raise HTTPException(status_code=404, detail="Tenant not found in the selected environment")
        query = query.filter(models.PlatformAuditLog.tenant_id == tenant_id)
    if action:
        query = query.filter(models.PlatformAuditLog.action.ilike(f"%{action.strip()}%"))
    total = query.count()
    rows = query.order_by(models.PlatformAuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "items": [
            {
                "id": row.id,
                "action": row.action,
                "module": row.module,
                "actor_user_id": row.actor_user_id,
                "tenant_id": row.tenant_id,
                "tenant_name": _tenant_name(db, row.tenant_id),
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "reason": row.reason,
                "ip_address": row.ip_address,
                "user_agent": row.user_agent,
                "details": row.details_json or {},
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "data_mode": mode,
    }


@router.get("/tenants/select")
def tenant_select(
    data_mode: str = "REAL",
    q: str | None = None,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        mode = normalize_data_mode(data_mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    query = db.query(account_models.AMO).filter(account_models.AMO.is_demo.is_(mode == "DEMO"))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                account_models.AMO.name.ilike(like),
                account_models.AMO.amo_code.ilike(like),
                account_models.AMO.login_slug.ilike(like),
            )
        )
    rows = query.order_by(account_models.AMO.name).limit(250).all()
    return {
        "items": [
            {
                "id": row.id,
                "name": row.name,
                "amo_code": row.amo_code,
                "login_slug": row.login_slug,
                "data_mode": mode,
                "is_active": row.is_active,
            }
            for row in rows
        ],
        "data_mode": mode,
    }


@router.get("/webhooks/{webhook_id}/deliveries")
def webhook_deliveries(
    webhook_id: str,
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    webhook = db.get(models.PlatformWebhookConfig, webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    rows = (
        db.query(models.PlatformWebhookDeliveryLog)
        .filter(models.PlatformWebhookDeliveryLog.webhook_id == webhook_id)
        .order_by(models.PlatformWebhookDeliveryLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "webhook": {
            "id": webhook.id,
            "name": webhook.name,
            "event_type": webhook.event_type,
            "target_url": webhook.target_url,
            "status": webhook.status,
            "tenant_id": webhook.tenant_id,
            "is_global": webhook.is_global,
            "failure_count": webhook.failure_count,
            "last_delivery_at": webhook.last_delivery_at,
        },
        "items": [
            {
                "id": row.id,
                "event_type": row.event_type,
                "status_code": row.status_code,
                "success": row.success,
                "duration_ms": row.duration_ms,
                "attempt_count": row.attempt_count,
                "error_detail": row.error_detail,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }


@router.patch("/webhooks/{webhook_id}")
def update_webhook_state(
    webhook_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    row = db.get(models.PlatformWebhookConfig, webhook_id)
    if not row:
        raise HTTPException(status_code=404, detail="Webhook not found")
    reason = _reason(payload)
    next_status = str(payload.get("status") or "").strip().upper()
    if next_status not in {"ACTIVE", "PAUSED", "DISABLED"}:
        raise HTTPException(status_code=422, detail="status must be ACTIVE, PAUSED or DISABLED")
    row.status = next_status
    services.audit(
        db,
        actor_user_id=_actor(user),
        action="integration.webhook.state_updated",
        tenant_id=row.tenant_id,
        entity_type="platform_webhook_config",
        entity_id=row.id,
        reason=reason,
        details={"status": next_status},
    )
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "status": row.status,
        "failure_count": row.failure_count,
        "last_delivery_at": row.last_delivery_at,
    }


@router.get("/infrastructure/capabilities")
def infrastructure_capabilities(user=Depends(require_platform_superuser)):
    return {
        "database_failover": {
            "available": False,
            "reason": "No safe runtime implementation exists in this codebase.",
        },
        "api_token_reset": {"available": True, "requires_reason": True},
        "feature_flag_scopes": ["GLOBAL", "PLAN", "TENANT"],
        "maintenance_transitions": ["SCHEDULED", "ACTIVE", "COMPLETED", "CANCELLED"],
    }


@router.patch("/infrastructure/maintenance/{window_id}")
def transition_maintenance(
    window_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    row = db.get(models.PlatformMaintenanceWindow, window_id)
    if not row:
        raise HTTPException(status_code=404, detail="Maintenance window not found")
    reason = _reason(payload)
    next_status = str(payload.get("status") or "").strip().upper()
    if next_status not in {"SCHEDULED", "ACTIVE", "COMPLETED", "CANCELLED"}:
        raise HTTPException(status_code=422, detail="Unsupported maintenance status")
    row.status = next_status
    services.audit(
        db,
        actor_user_id=_actor(user),
        action="infrastructure.maintenance.transitioned",
        entity_type="platform_maintenance_window",
        entity_id=row.id,
        reason=reason,
        details={"status": next_status},
    )
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "title": row.title,
        "status": row.status,
        "starts_at": row.starts_at,
        "ends_at": row.ends_at,
        "impact_level": row.impact_level,
    }


@router.post("/tenants/{tenant_id}/support-sessions")
def start_support_session(
    tenant_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    tenant = db.get(account_models.AMO, tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=404, detail="Active tenant not found")
    access_level = str(payload.get("access_level") or "READ_ONLY").strip().upper()
    if access_level not in {"READ_ONLY", "ADMIN"}:
        raise HTTPException(status_code=422, detail="access_level must be READ_ONLY or ADMIN")
    reason = _reason(payload)
    minutes = max(5, min(int(payload.get("minutes") or 30), 120))
    status_value = "ACTIVE" if access_level == "READ_ONLY" else "PENDING"
    row = models.PlatformTenantSupportSession(
        tenant_id=tenant_id,
        platform_user_id=_actor(user),
        access_level=access_level,
        status=status_value,
        reason=reason,
        requested_by_user_id=_actor(user),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=minutes),
        metadata_json={
            "requested_route": payload.get("requested_route"),
            "ticket_reference": payload.get("ticket_reference"),
        },
    )
    db.add(row)
    db.flush()
    services.audit(
        db,
        actor_user_id=_actor(user),
        action="support.session.created" if status_value == "ACTIVE" else "support.session.requested",
        tenant_id=tenant_id,
        entity_type="platform_tenant_support_session",
        entity_id=row.id,
        reason=reason,
        details={"access_level": access_level, "minutes": minutes, "status": status_value},
    )
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "access_level": row.access_level,
        "status": row.status,
        "reason": row.reason,
        "expires_at": row.expires_at,
        "created_at": row.created_at,
    }
