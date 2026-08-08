from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from amodb.database import get_read_db, get_write_db

from . import ops_data_models as ops_models
from . import product_analytics
from .router import require_platform_superuser


router = APIRouter(prefix="/ops/v1", tags=["platform-operations-management"])

_ALLOWED_VIEW_SCOPES = {"tenant_fleet", "users", "incidents", "product_analytics", "commercial"}
_ALLOWED_FLEET_FILTERS = {"health", "active", "q", "min_users", "max_users", "sort", "country", "plan", "module", "billing", "security", "integration"}
_INCIDENT_STATES = ("DETECTED", "ACKNOWLEDGED", "MITIGATED", "RESOLVED")
_INCIDENT_SEVERITIES = {"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
_CHANGE_KINDS = {"DEPLOYMENT", "FEATURE_FLAG", "MAINTENANCE", "INCIDENT", "CONFIGURATION", "MIGRATION"}


def _actor(user) -> str:
    return str(getattr(user, "id", ""))


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _bounded_list(value: Any, *, limit: int = 200) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip()[:128] for item in value if str(item).strip()))[:limit]


def _view_payload(row: ops_models.PlatformSavedView) -> dict[str, Any]:
    return {"id": row.id, "scope": row.scope, "name": row.name, "filters": row.filters_json or {}, "created_at": _iso(row.created_at), "updated_at": _iso(row.updated_at)}


def _incident_payload(row: ops_models.PlatformIncident) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "summary": row.summary,
        "severity": row.severity,
        "state": row.state,
        "source": row.source,
        "components": row.components_json or [],
        "affected_nodes": row.affected_nodes_json or [],
        "affected_tenants": row.affected_tenants_json or [],
        "alert_refs": row.alert_refs_json or [],
        "change_refs": row.change_refs_json or [],
        "runbook": row.runbook,
        "external_ref": row.external_ref,
        "started_at": _iso(row.started_at),
        "acknowledged_at": _iso(row.acknowledged_at),
        "mitigated_at": _iso(row.mitigated_at),
        "resolved_at": _iso(row.resolved_at),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


@router.get("/product-analytics/rollups")
def product_rollups(
    data_mode: str = Query("REAL"),
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return product_analytics.analytics_summary(db, data_mode=data_mode, days=days)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/tenant-health/saved-views")
def saved_views(
    scope: str = Query("tenant_fleet"),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    if scope not in _ALLOWED_VIEW_SCOPES:
        raise HTTPException(status_code=422, detail="Unsupported saved-view scope")
    rows = (
        db.query(ops_models.PlatformSavedView)
        .filter(ops_models.PlatformSavedView.platform_user_id == _actor(user), ops_models.PlatformSavedView.scope == scope)
        .order_by(ops_models.PlatformSavedView.updated_at.desc())
        .limit(100)
        .all()
    )
    return {"items": [_view_payload(row) for row in rows]}


@router.post("/tenant-health/saved-views", status_code=status.HTTP_201_CREATED)
def save_view(payload: dict[str, Any], db: Session = Depends(get_write_db), user=Depends(require_platform_superuser)):
    scope = str(payload.get("scope") or "tenant_fleet").strip()
    name = str(payload.get("name") or "").strip()[:128]
    filters = payload.get("filters") or {}
    if scope not in _ALLOWED_VIEW_SCOPES or not name:
        raise HTTPException(status_code=422, detail="Valid scope and name are required")
    if not isinstance(filters, dict):
        raise HTTPException(status_code=422, detail="filters must be an object")
    if scope == "tenant_fleet":
        unknown = set(filters) - _ALLOWED_FLEET_FILTERS
        if unknown:
            raise HTTPException(status_code=422, detail=f"Unsupported tenant fleet filters: {', '.join(sorted(unknown))}")
    safe_filters = {str(key)[:64]: value for key, value in filters.items() if isinstance(value, (str, int, float, bool)) or value is None}
    row = (
        db.query(ops_models.PlatformSavedView)
        .filter(ops_models.PlatformSavedView.platform_user_id == _actor(user), ops_models.PlatformSavedView.scope == scope, ops_models.PlatformSavedView.name == name)
        .first()
    )
    if row is None:
        row = ops_models.PlatformSavedView(platform_user_id=_actor(user), scope=scope, name=name, filters_json=safe_filters)
        db.add(row)
    else:
        row.filters_json = safe_filters
        row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _view_payload(row)


@router.delete("/tenant-health/saved-views/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_view(view_id: str, db: Session = Depends(get_write_db), user=Depends(require_platform_superuser)):
    row = db.get(ops_models.PlatformSavedView, view_id)
    if row is None or row.platform_user_id != _actor(user):
        raise HTTPException(status_code=404, detail="Saved view not found")
    db.delete(row)
    db.commit()
    return None


@router.get("/incident-center")
def list_incidents(
    state: str | None = Query(None),
    severity: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    query = db.query(ops_models.PlatformIncident)
    if state:
        query = query.filter(ops_models.PlatformIncident.state == state.strip().upper())
    if severity:
        query = query.filter(ops_models.PlatformIncident.severity == severity.strip().upper())
    total = query.count()
    rows = query.order_by(ops_models.PlatformIncident.started_at.desc()).offset(offset).limit(limit).all()
    return {"items": [_incident_payload(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/incident-center", status_code=status.HTTP_201_CREATED)
def create_incident(payload: dict[str, Any], db: Session = Depends(get_write_db), user=Depends(require_platform_superuser)):
    title = str(payload.get("title") or "").strip()[:255]
    severity = str(payload.get("severity") or "HIGH").strip().upper()
    if not title or severity not in _INCIDENT_SEVERITIES:
        raise HTTPException(status_code=422, detail="title and a valid severity are required")
    row = ops_models.PlatformIncident(
        title=title,
        summary=str(payload.get("summary") or "")[:4000] or None,
        severity=severity,
        state="DETECTED",
        source=str(payload.get("source") or "manual")[:64],
        components_json=_bounded_list(payload.get("components")),
        affected_nodes_json=_bounded_list(payload.get("affected_nodes")),
        affected_tenants_json=_bounded_list(payload.get("affected_tenants"), limit=1000),
        alert_refs_json=_bounded_list(payload.get("alert_refs")),
        change_refs_json=_bounded_list(payload.get("change_refs")),
        runbook=str(payload.get("runbook") or "")[:255] or None,
        external_ref=str(payload.get("external_ref") or "")[:255] or None,
        created_by=_actor(user),
    )
    db.add(row)
    db.flush()
    db.add(ops_models.PlatformIncidentEvent(incident_id=row.id, event_type="DETECTED", message="Incident detected/created.", actor_user_id=_actor(user), data_json={"severity": severity}))
    db.commit()
    db.refresh(row)
    return _incident_payload(row)


@router.get("/incident-center/{incident_id}")
def incident_detail(incident_id: str, db: Session = Depends(get_read_db), user=Depends(require_platform_superuser)):
    row = db.get(ops_models.PlatformIncident, incident_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    events = db.query(ops_models.PlatformIncidentEvent).filter(ops_models.PlatformIncidentEvent.incident_id == incident_id).order_by(ops_models.PlatformIncidentEvent.created_at.asc()).limit(1000).all()
    return {**_incident_payload(row), "timeline": [{"id": item.id, "event_type": item.event_type, "message": item.message, "actor_user_id": item.actor_user_id, "data": item.data_json or {}, "created_at": _iso(item.created_at)} for item in events]}


@router.post("/incident-center/{incident_id}/transition")
def transition_incident(incident_id: str, payload: dict[str, Any], db: Session = Depends(get_write_db), user=Depends(require_platform_superuser)):
    target = str(payload.get("state") or "").strip().upper()
    message = str(payload.get("message") or "").strip()[:4000]
    row = db.get(ops_models.PlatformIncident, incident_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    if target not in _INCIDENT_STATES:
        raise HTTPException(status_code=422, detail="Unsupported incident state")
    current_index = _INCIDENT_STATES.index(row.state) if row.state in _INCIDENT_STATES else 0
    target_index = _INCIDENT_STATES.index(target)
    if target_index < current_index or target_index > current_index + 1:
        raise HTTPException(status_code=409, detail="Incident transitions must advance one state at a time")
    if target_index == current_index:
        return _incident_payload(row)
    now = datetime.now(timezone.utc)
    row.state = target
    if target == "ACKNOWLEDGED":
        row.acknowledged_at = now
        row.acknowledged_by = _actor(user)
    elif target == "MITIGATED":
        row.mitigated_at = now
        row.mitigated_by = _actor(user)
    elif target == "RESOLVED":
        row.resolved_at = now
        row.resolved_by = _actor(user)
    row.updated_at = now
    db.add(ops_models.PlatformIncidentEvent(incident_id=row.id, event_type=target, message=message or f"Incident moved to {target}.", actor_user_id=_actor(user), data_json={}))
    db.commit()
    return _incident_payload(row)


@router.get("/change-markers")
def change_markers(
    kind: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    query = db.query(ops_models.PlatformChangeMarker)
    if kind:
        query = query.filter(ops_models.PlatformChangeMarker.kind == kind.strip().upper())
    rows = query.order_by(ops_models.PlatformChangeMarker.occurred_at.desc()).limit(limit).all()
    return {"items": [{"id": row.id, "kind": row.kind, "reference": row.reference, "title": row.title, "details": row.details_json or {}, "actor_user_id": row.actor_user_id, "occurred_at": _iso(row.occurred_at)} for row in rows]}


@router.post("/change-markers", status_code=status.HTTP_201_CREATED)
def create_change_marker(payload: dict[str, Any], db: Session = Depends(get_write_db), user=Depends(require_platform_superuser)):
    kind = str(payload.get("kind") or "").strip().upper()
    title = str(payload.get("title") or "").strip()[:255]
    if kind not in _CHANGE_KINDS or not title:
        raise HTTPException(status_code=422, detail="Valid kind and title are required")
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    safe_details = {str(key)[:64]: str(value)[:512] for key, value in details.items() if not isinstance(value, (dict, list, tuple, set))}
    row = ops_models.PlatformChangeMarker(kind=kind, reference=str(payload.get("reference") or "")[:255] or None, title=title, details_json=safe_details, actor_user_id=_actor(user))
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "kind": row.kind, "reference": row.reference, "title": row.title, "details": row.details_json or {}, "occurred_at": _iso(row.occurred_at)}
