from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.training.integration import training_source_status_snapshot
from amodb.database import Base, get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_router import (
    _event,
    _integration_payload,
    create_integration_link as _create_integration_link,
)
from .workspace_service import audit, require_control_user, resolve_tenant


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

# The prefix rule is intentionally narrowed for Training.  Import staging,
# notifications, audit logs, access tokens and low-level participant rows are
# not governed DMS link targets and must not be exposed through the catalogue.
_EXPLICIT_ALLOWED_TABLES: dict[str, set[str]] = {
    "TRAINING": {
        "training_courses",
        "training_requirements",
        "training_records",
        "training_events",
        "training_files",
        "training_certificate_issues",
        "training_plans",
        "training_plan_items",
        "training_attendance_windows",
        "training_assessment_instances",
        "training_authorization_cases",
        "training_experience_reviews",
        "training_competence_reviews",
        "training_remedial_actions",
    },
}

_DISPLAY_COLUMN_PRIORITY = (
    "code",
    "course_id",
    "course_name",
    "certificate_number",
    "original_filename",
    "reference",
    "number",
    "title",
    "name",
    "description",
    "email",
    "registration",
    "part_number",
    "serial_number",
)


def _search_training_records(
    db: Session,
    *,
    table: sa.Table,
    tenant_values: list[str],
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    courses = Base.metadata.tables.get("training_courses")
    users = Base.metadata.tables.get("users")
    if courses is None or users is None:
        return []
    statement = (
        sa.select(
            table.c.id,
            table.c.valid_until,
            table.c.completion_date,
            table.c.verification_status,
            table.c.record_status,
            table.c.source_status,
            courses.c.course_id.label("course_code"),
            courses.c.course_name,
            users.c.full_name.label("person_name"),
            users.c.staff_code,
        )
        .select_from(
            table.join(courses, sa.and_(courses.c.id == table.c.course_id, courses.c.amo_id == table.c.amo_id))
            .join(users, sa.and_(users.c.id == table.c.user_id, users.c.amo_id == table.c.amo_id))
        )
        .where(sa.cast(table.c.amo_id, sa.String).in_(tenant_values))
        .order_by(table.c.completion_date.desc(), table.c.id.desc())
        .limit(limit)
    )
    if query:
        term = f"%{query}%"
        statement = statement.where(
            sa.or_(
                sa.cast(courses.c.course_id, sa.String).ilike(term),
                sa.cast(courses.c.course_name, sa.String).ilike(term),
                sa.cast(users.c.full_name, sa.String).ilike(term),
                sa.cast(users.c.staff_code, sa.String).ilike(term),
            )
        )
    items: list[dict[str, Any]] = []
    for row in db.execute(statement).mappings().all():
        status_value = training_source_status_snapshot(
            table.name,
            row,
            fallback=str(row.get("verification_status") or ""),
            as_of=date.today(),
        )
        course = str(row.get("course_code") or row.get("course_name") or "Training")
        person = str(row.get("person_name") or row.get("staff_code") or "Personnel")
        completed = str(row.get("completion_date") or "date unavailable")
        items.append({
            "id": str(row["id"]),
            "label": f"{person} · {course} · completed {completed}",
            "status": status_value,
            "source_module": "TRAINING",
            "source_table": table.name,
            "entity_type": table.name,
        })
    return items


def _safe_identifier(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    if not normalized:
        raise HTTPException(status_code=422, detail="A valid integration entity type is required")
    return normalized


def _table_allowed(source_module: str, table_name: str) -> bool:
    module = source_module.upper()
    explicit = _EXPLICIT_ALLOWED_TABLES.get(module)
    lowered = table_name.lower()
    if explicit is not None:
        return lowered in explicit
    rules = _ALLOWED_TABLE_RULES.get(module, ())
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


def _tenant_column(table: sa.Table) -> sa.Column:
    for name in ("amo_id", "tenant_id"):
        if name in table.c:
            return table.c[name]
    raise HTTPException(
        status_code=422,
        detail={
            "code": "INTEGRATION_SOURCE_NOT_TENANT_SCOPED",
            "message": f"The source table {table.name} has no AMO or tenant boundary.",
        },
    )


def _status_column(table: sa.Table, explicit: Any = None) -> sa.Column | None:
    if explicit:
        name = _safe_identifier(str(explicit))
        if name not in table.c:
            raise HTTPException(status_code=422, detail=f"Status column {name!r} does not exist on {table.name}")
        return table.c[name]
    for name in ("status", "state", "lifecycle_status", "verification_status", "is_active"):
        if name in table.c:
            return table.c[name]
    return None


def _display_columns(table: sa.Table) -> list[sa.Column]:
    return [table.c[name] for name in _DISPLAY_COLUMN_PRIORITY if name in table.c][:4]


def _catalog_table(source_module: str, source_table: str) -> sa.Table:
    module = str(source_module or "").strip().upper()
    if module not in _ALLOWED_TABLE_RULES:
        raise HTTPException(status_code=422, detail="Unsupported integration source module")
    name = _safe_identifier(source_table)
    table = Base.metadata.tables.get(name)
    if table is None or not _table_allowed(module, table.name):
        raise HTTPException(status_code=422, detail="The requested source table is not permitted for this module")
    _tenant_column(table)
    _column(table, ["id", "entity_id", "record_id", "course_id", "work_order_id"])
    return table


def _display_value(row: sa.RowMapping, columns: list[sa.Column], fallback: str) -> str:
    values = [str(row.get(column.name) or "").strip() for column in columns]
    values = [value for value in values if value]
    return " · ".join(values[:3]) or fallback


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
    tenant_column = _tenant_column(table)

    tenant_values = {str(tenant.amo_id), str(tenant.id)}
    statement = sa.select(table).where(sa.cast(id_column, sa.String) == str(entity_id))
    row = db.execute(statement).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="The linked source record does not exist")
    if str(row.get(tenant_column.name)) not in tenant_values:
        raise HTTPException(status_code=403, detail="The linked source record belongs to another tenant")

    status_column = _status_column(table, metadata.get("status_column"))
    raw_status = row.get(status_column.name) if status_column is not None else None
    if isinstance(raw_status, bool):
        live_status = "ACTIVE" if raw_status else "INACTIVE"
    else:
        live_status = str(getattr(raw_status, "value", raw_status or "VERIFIED")).upper()
    if source_module.strip().upper() == "TRAINING":
        live_status = training_source_status_snapshot(
            table.name,
            row,
            fallback=live_status,
            as_of=date.today(),
        )

    return {
        "source_table": table.name,
        "id_column": id_column.name,
        "tenant_column": tenant_column.name,
        "status_column": status_column.name if status_column is not None else None,
        "status_snapshot": live_status,
        "verified_at": datetime.utcnow().isoformat(),
    }


@router.get("/t/{tenant_slug}/integration-catalog")
def get_integration_catalog(
    tenant_slug: str,
    source_module: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    resolve_tenant(db, tenant_slug, current_user)
    requested_module = str(source_module or "").strip().upper()
    if requested_module and requested_module not in _ALLOWED_TABLE_RULES:
        raise HTTPException(status_code=422, detail="Unsupported integration source module")

    modules = [requested_module] if requested_module else sorted(_ALLOWED_TABLE_RULES)
    result: list[dict[str, Any]] = []
    for module in modules:
        tables: list[dict[str, Any]] = []
        for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name):
            if not _table_allowed(module, table.name):
                continue
            try:
                id_column = _column(table, ["id", "entity_id", "record_id", "course_id", "work_order_id"])
                tenant_column = _tenant_column(table)
            except HTTPException:
                continue
            tables.append({
                "name": table.name,
                "entity_type": table.name,
                "id_column": id_column.name,
                "tenant_column": tenant_column.name,
                "display_columns": [column.name for column in _display_columns(table)],
            })
        result.append({"module": module, "tables": tables})
    return {"modules": result}


@router.get("/t/{tenant_slug}/integration-catalog/search")
def search_integration_catalog(
    tenant_slug: str,
    source_module: str,
    source_table: str,
    q: str = "",
    limit: int = Query(default=25, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    module = source_module.strip().upper()
    table = _catalog_table(module, source_table)
    id_column = _column(table, ["id", "entity_id", "record_id", "course_id", "work_order_id"])
    tenant_column = _tenant_column(table)
    display_columns = _display_columns(table)
    status_column = _status_column(table)
    tenant_values = [str(tenant.amo_id), str(tenant.id)]

    if module == "TRAINING" and table.name == "training_records":
        items = _search_training_records(
            db,
            table=table,
            tenant_values=tenant_values,
            query=q.strip(),
            limit=limit,
        )
        return {"items": items, "limit": limit, "source_module": module, "source_table": table.name}

    statement = sa.select(table).where(sa.cast(tenant_column, sa.String).in_(tenant_values))
    query = q.strip()
    if query and display_columns:
        search_term = f"%{query}%"
        statement = statement.where(sa.or_(*[sa.cast(column, sa.String).ilike(search_term) for column in display_columns]))
    statement = statement.limit(limit)
    rows = db.execute(statement).mappings().all()

    items: list[dict[str, Any]] = []
    for row in rows:
        entity_id = str(row.get(id_column.name) or "")
        if not entity_id:
            continue
        raw_status = row.get(status_column.name) if status_column is not None else None
        if isinstance(raw_status, bool):
            status_value = "ACTIVE" if raw_status else "INACTIVE"
        else:
            status_value = str(getattr(raw_status, "value", raw_status or "VERIFIED")).upper()
        if module == "TRAINING":
            status_value = training_source_status_snapshot(
                table.name,
                row,
                fallback=status_value,
                as_of=date.today(),
            )
        items.append({
            "id": entity_id,
            "label": _display_value(row, display_columns, entity_id),
            "status": status_value,
            "source_module": module,
            "source_table": table.name,
            "entity_type": table.name,
        })
    return {"items": items, "limit": limit, "source_module": module, "source_table": table.name}


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
