from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import Base, get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_router import (
    _event,
    _integration_payload,
    create_integration_link as _create_integration_link,
)
from .workspace_service import audit, require_control_user, resolve_tenant, utcnow


router = APIRouter(prefix="/workspace", tags=["Document Control Integrations"])

_ALLOWED_TABLE_RULES: dict[str, tuple[str, ...]] = {
    "QMS": ("qms_", "quality_", "audit_", "car_", "corrective_"),
    "TRAINING": ("training_",),
    "WORKFORCE": (
        "workforce_",
        "personnel_",
        "employment_",
        "leave_",
        "attendance_",
        "timesheet",
        "overtime_",
        "users",
        "departments",
    ),
    "PLANNING": ("planning_", "maintenance_program", "work_order", "work_package", "task_"),
    "PRODUCTION": ("production_", "work_order", "work_package", "task_", "defect"),
    "MAINTENANCE": ("maintenance_", "work_order", "work_package", "task_", "defect", "crs_"),
    "FLEET": ("fleet_", "aircraft", "engine", "component", "asset_"),
    "STORES": ("inventory_", "stores_", "stock_", "part_", "tool_", "supplier", "purchase_", "goods_"),
    "TECHNICAL_RECORDS": ("technical_", "records_", "crs_", "maintenance_record", "work_order"),
}


def _safe_identifier(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    if not normalized:
        raise HTTPException(status_code=422, detail="A valid integration entity type is required")
    return normalized


def _table_allowed(source_module: str, table_name: str) -> bool:
    rules = _ALLOWED_TABLE_RULES.get(source_module.upper(), ())
    lowered = table_name.lower()
    return any(lowered == rule or lowered.startswith(rule) for rule in rules)


def _candidate_table_names(source_module: str, entity_type: str, metadata: dict[str, Any]) -> list[str]:
    explicit = metadata.get("source_table")
    normalized = _safe_identifier(entity_type)
    module = source_module.lower()
    candidates = [
        str(explicit or "").strip().lower(),
        normalized,
        f"{normalized}s",
        f"{module}_{normalized}",
        f"{module}_{normalized}s",
    ]
    if module == "qms":
        candidates.extend([f"qms_{normalized}", f"qms_{normalized}s"])
    return list(dict.fromkeys(value for value in candidates if value))


def _resolve_source_table(source_module: str, entity_type: str, metadata: dict[str, Any]) -> sa.Table:
    candidates = _candidate_table_names(source_module, entity_type, metadata)
    tables = Base.metadata.tables
    for candidate in candidates:
        table = tables.get(candidate)
        if table is not None and _table_allowed(source_module, table.name):
            return table

    normalized = _safe_identifier(entity_type)
    fuzzy = [
        table
        for table in tables.values()
        if _table_allowed(source_module, table.name)
        and (
            table.name.endswith(normalized)
            or table.name.endswith(f"{normalized}s")
            or normalized in table.name.split("_")
        )
    ]
    if len(fuzzy) == 1:
        return fuzzy[0]

    allowed_examples = sorted(
        table.name
        for table in tables.values()
        if _table_allowed(source_module, table.name)
    )[:25]
    raise HTTPException(
        status_code=422,
        detail={
            "code": "INTEGRATION_SOURCE_UNRESOLVED",
            "message": "The source entity type does not resolve to one authoritative module table.",
            "source_module": source_module,
            "entity_type": entity_type,
            "allowed_source_tables": allowed_examples,
            "hint": "Provide metadata.source_table using one of the listed module tables.",
        },
    )


def _column(table: sa.Table, preferred: list[str], explicit: Any = None) -> sa.Column:
    if explicit:
        name = _safe_identifier(str(explicit))
        if name not in table.c:
            raise HTTPException(status_code=422, detail=f"Column {name!r} does not exist on {table.name}")
        return table.c[name]
    for name in preferred:
        if name in table.c:
            return table.c[name]
    raise HTTPException(
        status_code=422,
        detail={
            "code": "INTEGRATION_SOURCE_COLUMN_MISSING",
            "message": f"No supported identity column exists on {table.name}.",
        },
    )


def verify_source_entity(
    db: Session,
    *,
    tenant,
    source_module: str,
    entity_type: str,
    entity_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(metadata or {})
    table = _resolve_source_table(source_module, entity_type, metadata)
    id_column = _column(table, ["id", "entity_id", "record_id", "course_id", "work_order_id"], metadata.get("id_column"))

    tenant_column = None
    for name in ("amo_id", "tenant_id"):
        if name in table.c:
            tenant_column = table.c[name]
            break
    if tenant_column is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INTEGRATION_SOURCE_NOT_TENANT_SCOPED",
                "message": f"The source table {table.name} has no AMO or tenant boundary.",
            },
        )

    tenant_values = {str(tenant.amo_id), str(tenant.id)}
    statement = sa.select(table).where(sa.cast(id_column, sa.String) == str(entity_id))
    row = db.execute(statement).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="The linked source record does not exist")
    if str(row.get(tenant_column.name)) not in tenant_values:
        raise HTTPException(status_code=403, detail="The linked source record belongs to another tenant")

    status_column = None
    explicit_status = metadata.get("status_column")
    if explicit_status:
        name = _safe_identifier(str(explicit_status))
        if name not in table.c:
            raise HTTPException(status_code=422, detail=f"Status column {name!r} does not exist on {table.name}")
        status_column = table.c[name]
    else:
        for name in ("status", "state", "lifecycle_status", "verification_status", "is_active"):
            if name in table.c:
                status_column = table.c[name]
                break

    raw_status = row.get(status_column.name) if status_column is not None else None
    if isinstance(raw_status, bool):
        live_status = "ACTIVE" if raw_status else "INACTIVE"
    else:
        live_status = str(getattr(raw_status, "value", raw_status or "VERIFIED")).upper()

    return {
        "source_table": table.name,
        "id_column": id_column.name,
        "tenant_column": tenant_column.name,
        "status_column": status_column.name if status_column is not None else None,
        "status_snapshot": live_status,
        "verified_at": datetime.utcnow().isoformat(),
    }


def refresh_integration_link(db: Session, tenant, link: dm.DocumentIntegrationLink) -> dict[str, Any]:
    verification = verify_source_entity(
        db,
        tenant=tenant,
        source_module=link.source_module,
        entity_type=link.entity_type,
        entity_id=link.entity_id,
        metadata=dict(link.metadata_json or {}),
    )
    link.status_snapshot = verification["status_snapshot"]
    link.metadata_json = {**dict(link.metadata_json or {}), **verification}
    link.updated_at = utcnow()
    return verification


@router.post("/t/{tenant_slug}/integration-links", include_in_schema=False)
def create_verified_integration_link(
    tenant_slug: str,
    payload: schemas.IntegrationLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    verification = verify_source_entity(
        db,
        tenant=tenant,
        source_module=payload.source_module,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        metadata=dict(payload.metadata),
    )
    verified_payload = payload.model_copy(
        update={
            "status_snapshot": verification["status_snapshot"],
            "metadata": {**dict(payload.metadata), **verification},
        }
    )
    return _create_integration_link(
        tenant_slug=tenant_slug,
        payload=verified_payload,
        request=request,
        db=db,
        current_user=current_user,
    )


@router.post("/t/{tenant_slug}/integration-links/{link_id}/refresh")
def refresh_verified_integration_link(
    tenant_slug: str,
    link_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    link = (
        db.query(dm.DocumentIntegrationLink)
        .filter(
            dm.DocumentIntegrationLink.tenant_id == tenant.amo_id,
            dm.DocumentIntegrationLink.id == link_id,
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Document integration link not found")
    before = _integration_payload(link)
    verification = refresh_integration_link(db, tenant, link)
    after = _integration_payload(link)
    audit(
        db,
        tenant,
        request,
        "document.integration_link.refreshed",
        "document_integration_link",
        link.id,
        {"before": before, "after": after, "verification": verification},
    )
    db.commit()
    _event(
        event_type="doc_control.integration_refreshed",
        entity_type="document_integration_link",
        entity_id=link.id,
        action="refreshed",
        user=current_user,
        tenant_id=tenant.amo_id,
        metadata={
            "manual_id": link.manual_id,
            "source_module": link.source_module,
            "source_entity_id": link.entity_id,
            "status_snapshot": link.status_snapshot,
        },
    )
    return after
