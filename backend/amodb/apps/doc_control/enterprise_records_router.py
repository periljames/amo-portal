from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import knowledge_models as km
from .workspace_decision_policy import is_decision_approver
from .workspace_integration_router import _column, _resolve_source_table, verify_source_entity
from .workspace_service import audit, require_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Enterprise Records"])


class EnterpriseRecordRefreshRequest(BaseModel):
    source_module: str | None = Field(default=None, max_length=64)
    canonical_ids: list[str] = Field(default_factory=list, max_length=500)


def _enum_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _parsed_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _first_present(row: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        if name in row and row.get(name) not in (None, ""):
            return row.get(name)
    return None


def _canonical_id(source_module: str, entity_type: str, entity_id: str) -> str:
    return f"{source_module.upper()}:{entity_type.upper()}:{entity_id}"


def _source_snapshot(db: Session, tenant, link: dm.DocumentIntegrationLink) -> dict[str, Any]:
    metadata = dict(link.metadata_json or {})
    try:
        table = _resolve_source_table(link.source_module, link.entity_type, metadata)
        id_column = _column(
            table,
            ["id", "entity_id", "record_id", "course_id", "work_order_id"],
            metadata.get("id_column"),
        )
        tenant_column = next((table.c[name] for name in ("amo_id", "tenant_id") if name in table.c), None)
        if tenant_column is None:
            raise HTTPException(status_code=422, detail=f"{table.name} is not tenant scoped")

        statement = sa.select(table).where(sa.cast(id_column, sa.String) == str(link.entity_id))
        row = db.execute(statement).mappings().first()
        if not row:
            return {
                "sync_state": "MISSING",
                "status": "SOURCE_MISSING",
                "source_table": table.name,
                "sync_message": "The source record no longer exists.",
            }
        if str(row.get(tenant_column.name)) not in {str(tenant.amo_id), str(tenant.id)}:
            return {
                "sync_state": "ERROR",
                "status": "SOURCE_FORBIDDEN",
                "source_table": table.name,
                "sync_message": "The source record belongs to another tenant.",
            }

        status_column_name = metadata.get("status_column")
        if status_column_name and str(status_column_name) in table.c:
            status_column = table.c[str(status_column_name)]
        else:
            status_column = next(
                (
                    table.c[name]
                    for name in ("status", "state", "lifecycle_status", "verification_status", "is_active")
                    if name in table.c
                ),
                None,
            )
        raw_status = row.get(status_column.name) if status_column is not None else None
        if isinstance(raw_status, bool):
            live_status = "ACTIVE" if raw_status else "INACTIVE"
        else:
            live_status = (_enum_text(raw_status) or "VERIFIED").upper()

        reference = _first_present(
            row,
            (
                "record_number",
                "reference_number",
                "reference_no",
                "audit_number",
                "finding_number",
                "car_number",
                "work_order_number",
                "job_card_number",
                "course_code",
                "code",
                "number",
                "registration",
                "serial_number",
            ),
        )
        title = _first_present(
            row,
            (
                "title",
                "name",
                "subject",
                "summary",
                "course_name",
                "task_name",
                "description",
            ),
        )
        source_updated_at = _first_present(
            row,
            (
                "updated_at",
                "modified_at",
                "completed_at",
                "closed_at",
                "issued_at",
                "event_date",
                "date",
                "created_at",
            ),
        )
        owner_user_id = _first_present(
            row,
            (
                "owner_user_id",
                "assigned_to_user_id",
                "assignee_id",
                "responsible_user_id",
                "created_by_user_id",
            ),
        )
        stored_status = (link.status_snapshot or "").upper()
        sync_state = "CHANGED" if stored_status and stored_status != live_status else "CURRENT"
        return {
            "sync_state": sync_state,
            "status": live_status,
            "source_table": table.name,
            "reference": str(reference) if reference not in (None, "") else None,
            "title": str(title) if title not in (None, "") else None,
            "source_updated_at": _iso(source_updated_at),
            "owner_user_id": str(owner_user_id) if owner_user_id not in (None, "") else None,
            "sync_message": (
                f"Source status changed from {stored_status} to {live_status}."
                if sync_state == "CHANGED"
                else None
            ),
        }
    except HTTPException as exc:
        return {
            "sync_state": "ERROR",
            "status": link.status_snapshot or "SOURCE_ERROR",
            "source_table": metadata.get("source_table"),
            "sync_message": str(exc.detail),
        }
    except Exception as exc:  # pragma: no cover - protects the register from one broken adapter
        return {
            "sync_state": "ERROR",
            "status": link.status_snapshot or "SOURCE_ERROR",
            "source_table": metadata.get("source_table"),
            "sync_message": f"{exc.__class__.__name__}: {exc}",
        }


def _linked_records(
    db: Session,
    *,
    tenant,
    source_module: str | None,
) -> list[dict[str, Any]]:
    query = db.query(dm.DocumentIntegrationLink).filter(dm.DocumentIntegrationLink.tenant_id == tenant.amo_id)
    if source_module and source_module.upper() != "DOCUMENT_CONTROL":
        query = query.filter(dm.DocumentIntegrationLink.source_module == source_module.upper())
    rows = query.order_by(dm.DocumentIntegrationLink.created_at.desc()).all()

    groups: dict[str, list[dm.DocumentIntegrationLink]] = defaultdict(list)
    for row in rows:
        groups[_canonical_id(row.source_module, row.entity_type, row.entity_id)].append(row)

    manual_ids = {row.manual_id for row in rows}
    manuals = {
        row.id: row
        for row in db.query(manual_models.Manual)
        .filter(manual_models.Manual.id.in_(manual_ids or ["-"]), manual_models.Manual.tenant_id == tenant.id)
        .all()
    }

    records: list[dict[str, Any]] = []
    for canonical, links in groups.items():
        first = links[0]
        metadata = dict(first.metadata_json or {})
        snapshot = _source_snapshot(db, tenant, first)
        linked_documents = []
        for link in links:
            manual = manuals.get(link.manual_id)
            linked_documents.append(
                {
                    "link_id": link.id,
                    "manual_id": link.manual_id,
                    "document_code": getattr(manual, "code", None),
                    "document_title": getattr(manual, "title", None),
                    "revision_id": link.revision_id,
                    "relation_type": link.relation_type,
                    "blocking": bool(link.blocking),
                }
            )
        last_verified = metadata.get("verified_at")
        live_status = str(snapshot.get("status") or first.status_snapshot or "UNKNOWN").upper()
        required_state = metadata.get("required_state")
        required_satisfied = not required_state or live_status == str(required_state).upper()
        sync_state = str(snapshot.get("sync_state") or "ERROR")
        blocking = any(link.blocking for link in links)
        records.append(
            {
                "canonical_id": canonical,
                "record_kind": "MODULE_RECORD",
                "source_module": first.source_module,
                "record_type": first.entity_type,
                "source_record_id": first.entity_id,
                "reference": snapshot.get("reference") or metadata.get("source_reference") or first.entity_id,
                "title": snapshot.get("title") or metadata.get("source_title") or first.entity_type.replace("_", " ").title(),
                "summary": metadata.get("summary"),
                "status": live_status,
                "sync_state": sync_state,
                "sync_message": snapshot.get("sync_message"),
                "source_table": snapshot.get("source_table") or metadata.get("source_table"),
                "source_route": metadata.get("source_route") or metadata.get("detail_route") or metadata.get("route"),
                "source_updated_at": snapshot.get("source_updated_at"),
                "last_verified_at": last_verified,
                "owner_user_id": snapshot.get("owner_user_id"),
                "blocking": blocking,
                "required_state": required_state,
                "required_state_satisfied": required_satisfied,
                "requires_attention": sync_state in {"CHANGED", "MISSING", "ERROR"} or (blocking and not required_satisfied),
                "linked_documents": linked_documents,
                "link_count": len(linked_documents),
                "relation_types": sorted({link.relation_type for link in links}),
                "generated_record_id": None,
                "download_url": None,
            }
        )
    return records


def _generated_records(db: Session, *, tenant, tenant_slug: str) -> list[dict[str, Any]]:
    rows = (
        db.query(km.DocumentationRecord)
        .filter(km.DocumentationRecord.tenant_id == tenant.amo_id)
        .order_by(km.DocumentationRecord.submitted_at.desc(), km.DocumentationRecord.id.desc())
        .all()
    )
    template_ids = {row.template_manual_id for row in rows}
    templates = {
        row.id: row
        for row in db.query(manual_models.Manual)
        .filter(manual_models.Manual.id.in_(template_ids or ["-"]), manual_models.Manual.tenant_id == tenant.id)
        .all()
    }
    records = []
    for row in rows:
        template = templates.get(row.template_manual_id)
        records.append(
            {
                "canonical_id": _canonical_id("DOCUMENT_CONTROL", "GENERATED_RECORD", row.id),
                "record_kind": "GENERATED_RECORD",
                "source_module": "DOCUMENT_CONTROL",
                "record_type": "GENERATED_RECORD",
                "source_record_id": row.id,
                "reference": row.record_number,
                "title": getattr(template, "title", None) or row.artifact_filename,
                "summary": getattr(template, "code", None),
                "status": row.status,
                "sync_state": "CURRENT",
                "sync_message": None,
                "source_table": km.DocumentationRecord.__tablename__,
                "source_route": None,
                "source_updated_at": _iso(row.submitted_at),
                "last_verified_at": _iso(row.reviewed_at or row.submitted_at),
                "owner_user_id": row.submitted_by_user_id,
                "blocking": False,
                "required_state": None,
                "required_state_satisfied": True,
                "requires_attention": row.status in {"PENDING_REVIEW", "SUBMITTED", "RETURNED"},
                "linked_documents": [
                    {
                        "link_id": None,
                        "manual_id": row.template_manual_id,
                        "document_code": getattr(template, "code", None),
                        "document_title": getattr(template, "title", None),
                        "revision_id": row.template_revision_id,
                        "relation_type": "GENERATED_FROM",
                        "blocking": False,
                    }
                ],
                "link_count": 1,
                "relation_types": ["GENERATED_FROM"],
                "generated_record_id": row.id,
                "download_url": f"/manuals/t/{tenant_slug}/records/{row.id}/artifact.pdf",
            }
        )
    return records


def _health(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "canonical_records": len(records),
        "module_records": sum(1 for row in records if row["record_kind"] == "MODULE_RECORD"),
        "generated_records": sum(1 for row in records if row["record_kind"] == "GENERATED_RECORD"),
        "current": sum(1 for row in records if row["sync_state"] == "CURRENT"),
        "changed": sum(1 for row in records if row["sync_state"] == "CHANGED"),
        "missing": sum(1 for row in records if row["sync_state"] == "MISSING"),
        "errors": sum(1 for row in records if row["sync_state"] == "ERROR"),
        "attention_required": sum(1 for row in records if row["requires_attention"]),
        "linked_to_multiple_documents": sum(1 for row in records if row["link_count"] > 1),
    }


@router.get("/t/{tenant_slug}/enterprise-records")
def list_enterprise_records(
    tenant_slug: str,
    source_module: str | None = None,
    record_type: str | None = None,
    status: str | None = None,
    sync_state: str | None = None,
    query: str | None = Query(default=None, max_length=200),
    page: int = 1,
    per_page: int = 75,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    module_filter = source_module.upper() if source_module else None
    records = _linked_records(db, tenant=tenant, source_module=module_filter)
    if module_filter in (None, "DOCUMENT_CONTROL"):
        records.extend(_generated_records(db, tenant=tenant, tenant_slug=tenant.slug))

    all_health = _health(records)
    if record_type:
        records = [row for row in records if row["record_type"].upper() == record_type.upper()]
    if status:
        records = [row for row in records if row["status"].upper() == status.upper()]
    if sync_state:
        records = [row for row in records if row["sync_state"].upper() == sync_state.upper()]
    if query and query.strip():
        needle = query.strip().lower()
        records = [
            row
            for row in records
            if needle
            in " ".join(
                str(value or "").lower()
                for value in (
                    row["reference"],
                    row["title"],
                    row["source_module"],
                    row["record_type"],
                    row["status"],
                    row["source_record_id"],
                )
            )
        ]

    records.sort(
        key=lambda row: (
            0 if row["requires_attention"] else 1,
            -(_parsed_datetime(row["source_updated_at"]) or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
            row["reference"],
        )
    )
    current_page = max(1, page)
    size = max(1, min(250, per_page))
    total = len(records)
    start = (current_page - 1) * size
    items = records[start : start + size]
    modules = sorted({row["source_module"] for row in records})
    record_types = sorted({row["record_type"] for row in records})
    return {
        "items": items,
        "health": all_health,
        "filters": {"source_modules": modules, "record_types": record_types},
        "pagination": {
            "page": current_page,
            "per_page": size,
            "total": total,
            "returned": len(items),
        },
        "capabilities": {
            "refresh": True,
            "review_generated_records": is_decision_approver(current_user),
            "control": True,
        },
    }


@router.post("/t/{tenant_slug}/enterprise-records/refresh")
def refresh_enterprise_records(
    tenant_slug: str,
    payload: EnterpriseRecordRefreshRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(dm.DocumentIntegrationLink).filter(dm.DocumentIntegrationLink.tenant_id == tenant.amo_id)
    if payload.source_module:
        query = query.filter(dm.DocumentIntegrationLink.source_module == payload.source_module.upper())
    links = query.order_by(dm.DocumentIntegrationLink.created_at.asc()).all()

    selected = set(payload.canonical_ids)
    groups: dict[str, list[dm.DocumentIntegrationLink]] = defaultdict(list)
    for link in links:
        canonical = _canonical_id(link.source_module, link.entity_type, link.entity_id)
        if selected and canonical not in selected:
            continue
        groups[canonical].append(link)

    refreshed = 0
    changed = 0
    missing = 0
    errors = 0
    now = datetime.now(timezone.utc).isoformat()
    for canonical, grouped_links in groups.items():
        first = grouped_links[0]
        try:
            verification = verify_source_entity(
                db,
                tenant=tenant,
                source_module=first.source_module,
                entity_type=first.entity_type,
                entity_id=first.entity_id,
                metadata=dict(first.metadata_json or {}),
            )
            for link in grouped_links:
                previous = link.status_snapshot
                link.status_snapshot = verification["status_snapshot"]
                link.metadata_json = {
                    **dict(link.metadata_json or {}),
                    **verification,
                    "last_sync_attempt_at": now,
                    "sync_error": None,
                }
                if previous and previous != link.status_snapshot:
                    changed += 1
            refreshed += 1
        except HTTPException as exc:
            target_status = "SOURCE_MISSING" if exc.status_code == 404 else "SOURCE_ERROR"
            for link in grouped_links:
                link.status_snapshot = target_status
                link.metadata_json = {
                    **dict(link.metadata_json or {}),
                    "last_sync_attempt_at": now,
                    "sync_error": str(exc.detail),
                }
            if exc.status_code == 404:
                missing += 1
            else:
                errors += 1
        except Exception as exc:  # pragma: no cover - keeps the batch progressing
            for link in grouped_links:
                link.status_snapshot = "SOURCE_ERROR"
                link.metadata_json = {
                    **dict(link.metadata_json or {}),
                    "last_sync_attempt_at": now,
                    "sync_error": f"{exc.__class__.__name__}: {exc}",
                }
            errors += 1

    summary = {
        "canonical_sources_considered": len(groups),
        "refreshed": refreshed,
        "changed_links": changed,
        "missing": missing,
        "errors": errors,
    }
    audit(
        db,
        tenant,
        request,
        "document.enterprise_records.refreshed",
        "enterprise_record_register",
        tenant.amo_id,
        summary,
    )
    db.commit()
    return summary
