"""My Quality work is a projection of authoritative assignments, not unread mail."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from amodb.database import get_read_db, get_write_db
from .management_review_router import StrictBody, _payload, _public, _save
from .tenant_security import TenantContext, assert_quality_permission, has_quality_permission, resolve_tenant_context, set_postgres_tenant_context

router = APIRouter(prefix="/work-inbox", tags=["My Quality Work"])
SOURCES = {
    "audits": {"table": "qms_audits", "label": "Audit", "permission": "qms.audit.view", "owners": ["lead_auditor_user_id", "observer_auditor_user_id", "assistant_auditor_user_id", "auditee_user_id"], "due": ["planned_end", "planned_start"], "path": "audits/{id}/setup"},
    "cars": {"table": "quality_cars", "label": "CAR / CAPA", "permission": "qms.car.view", "owners": ["assigned_to_user_id"], "due": ["due_date"], "path": "cars/{id}/overview", "approval_permission": "qms.car.manage", "approval_statuses": ["PENDING_VERIFICATION"]},
    "review-actions": {"table": "qms_management_review_actions", "label": "Management review action", "permission": "qms.management_review.view", "owners": ["owner_user_id"], "due": ["due_date"], "path": "management-review/actions?record={id}", "approval_permission": "qms.management_review.manage", "approval_statuses": ["PENDING_VERIFICATION"]},
    "reviews": {"table": "qms_management_reviews", "label": "Management review", "permission": "qms.management_review.view", "owners": ["owner_user_id"], "due": ["due_date"], "path": "management-review/{id}/overview", "approval_permission": "qms.management_review.manage", "approval_statuses": ["PENDING_APPROVAL"]},
    "risks": {"table": "qms_risks", "label": "Risk assessment", "permission": "qms.risk.view", "owners": ["owner_user_id"], "due": ["due_date"], "path": "risk/register?record={id}"},
    "treatments": {"table": "qms_risk_actions", "label": "Risk treatment", "permission": "qms.risk.view", "owners": ["owner_user_id"], "due": ["due_date"], "path": "risk/treatment-plans?record={id}"},
    "commitments": {"table": "qms_external_commitments", "label": "External commitment", "permission": "qms.external.view", "owners": ["owner_user_id"], "due": ["due_date"], "path": "external-interface/commitments?record={id}"},
}
TERMINAL = "'CLOSED','COMPLETED','COMPLETE','DONE','ARCHIVED','CANCELLED','REJECTED','RESOLVED','RETIRED'"
COMPLETE = "'CLOSED','COMPLETED','COMPLETE','DONE','ARCHIVED','RESOLVED'"
WATCH_TABLE = "qms_task_assignments"


class WatchBody(StrictBody):
    source: str = Field(max_length=40)
    record_id: str = Field(min_length=1, max_length=64)


def _context(db, ctx):
    assert_quality_permission(db, ctx, "qms.inbox.view")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)


def _watches(db, ctx):
    rows = db.execute(text(f"SELECT * FROM {WATCH_TABLE} WHERE amo_id=:amo AND owner_user_id=:actor AND source_type='QMS_WATCH' AND status='ACTIVE' AND deleted_at IS NULL"), {"amo": ctx.amo_id, "actor": ctx.user_id}).mappings().all()
    return {(str(_payload(r).get("source")), str(_payload(r).get("record_id"))): _public(r) for r in rows}


def _shape(db, spec):
    return {c["name"] for c in inspect(db.connection()).get_columns(spec["table"])}


def _source_row(db, ctx, source, record_id):
    spec = SOURCES.get(source)
    if not spec: raise HTTPException(422, "Choose a supported Quality source.")
    assert_quality_permission(db, ctx, spec["permission"])
    columns = _shape(db, spec)
    deleted = " AND deleted_at IS NULL" if "deleted_at" in columns else ""
    row = db.execute(text(f"SELECT id,title FROM {spec['table']} WHERE amo_id=:amo AND CAST(id AS TEXT)=:id{deleted}"), {"amo": ctx.amo_id, "id": record_id}).mappings().first()
    if not row: raise HTTPException(404, "This source record was not found in this tenant.")
    return row


@router.get("/summary")
def inbox_summary(ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_read_db)):
    """Count authorised work without loading all rows or claiming group approvals are individually assigned."""
    _context(db, ctx)
    counts = {"assigned_to_me": 0, "approvals": 0, "overdue": 0, "completed": 0}
    errors = []
    for key, spec in SOURCES.items():
        if not has_quality_permission(db, ctx, spec["permission"]):
            continue
        try:
            with db.begin_nested():
                columns = _shape(db, spec)
                owners = [name for name in spec["owners"] if name in columns]
                owner_terms = [f"{name}=:actor" for name in owners]
                if key == "audits" and "supporting_auditor_user_ids" in columns:
                    owner_terms.append(
                        "CAST(supporting_auditor_user_ids AS jsonb) @> jsonb_build_array(CAST(:actor AS text))"
                        if db.bind.dialect.name == "postgresql"
                        else "EXISTS (SELECT 1 FROM json_each(supporting_auditor_user_ids) WHERE value=:actor)"
                    )
                own = "(" + " OR ".join(owner_terms) + ")" if owner_terms else "1=0"
                status = "UPPER(CAST(status AS TEXT))"
                due = next((name for name in spec["due"] if name in columns), None)
                overdue = f"DATE({due}) < CURRENT_DATE" if due else "1=0"
                approval = (
                    f"{status} IN (" + ",".join(f"'{value}'" for value in spec["approval_statuses"]) + ")"
                    if spec.get("approval_permission") and has_quality_permission(db, ctx, spec["approval_permission"])
                    else "1=0"
                )
                def count_when(condition: str) -> str:
                    return f"COALESCE(SUM(CASE WHEN {condition} THEN 1 ELSE 0 END), 0)"
                where = "amo_id=:amo" + (" AND deleted_at IS NULL" if "deleted_at" in columns else "")
                values = db.execute(text(
                    "SELECT " +
                    count_when(f"{own} AND {status} NOT IN ({TERMINAL})") + " AS assigned_to_me, " +
                    count_when(approval) + " AS approvals, " +
                    count_when(f"{own} AND {status} NOT IN ({TERMINAL}) AND {overdue}") + " AS overdue, " +
                    count_when(f"{own} AND {status} IN ({COMPLETE})") + " AS completed " +
                    f"FROM {spec['table']} WHERE {where}"
                ), {"amo": ctx.amo_id, "actor": ctx.user_id}).mappings().one()
                for name in counts:
                    counts[name] += int(values[name] or 0)
        except Exception:
            errors.append({"source": spec["label"], "message": "This source could not be counted."})
    return {**counts, "source_errors": errors}


@router.get("/{view}")
def inbox(view: Literal["assigned-to-me", "approvals", "overdue", "watching", "completed"], q: str = Query("", max_length=80), source: str = Query("", max_length=40), offset: int = Query(0, ge=0, le=100000),
          ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_read_db)):
    _context(db, ctx)
    if source and source not in SOURCES:
        raise HTTPException(422, "Choose a supported Quality source.")
    watches = _watches(db, ctx)
    items, errors, total, unions = [], [], 0, []
    params = {"amo": ctx.amo_id, "actor": ctx.user_id, "q": "%" + q.lower() + "%", "limit": 30, "offset": offset}
    for key, spec in SOURCES.items():
        if source and key != source: continue
        if not has_quality_permission(db, ctx, spec["permission"]): continue
        if view == "approvals" and (not spec.get("approval_permission") or not has_quality_permission(db, ctx, spec["approval_permission"])): continue
        try:
            with db.begin_nested():
                columns = _shape(db, spec)
                due = next((v for v in spec["due"] if v in columns), None)
                due_sql = due or "NULL"
                status_sql = "UPPER(CAST(status AS TEXT))"
                where = "amo_id=:amo"
                if "deleted_at" in columns: where += " AND deleted_at IS NULL"
                if q: where += " AND lower(COALESCE(title,'')) LIKE :q"
                source_params = dict(params)
                if view == "watching":
                    ids = [record_id for source, record_id in watches if source == key]
                    if not ids: continue
                    binds = []
                    for index, record_id in enumerate(ids):
                        bind = f"watch_{key.replace('-', '_')}_{index}"
                        source_params[bind] = record_id
                        binds.append(":" + bind)
                    where += f" AND CAST(id AS TEXT) IN ({','.join(binds)})"
                elif view == "approvals":
                    where += " AND " + status_sql + " IN (" + ",".join(f"'{v}'" for v in spec["approval_statuses"]) + ")"
                else:
                    owners = [name for name in spec["owners"] if name in columns]
                    if not owners: continue
                    owner_terms = [f"{name}=:actor" for name in owners]
                    if key == "audits" and "supporting_auditor_user_ids" in columns:
                        owner_terms.append("CAST(supporting_auditor_user_ids AS jsonb) @> jsonb_build_array(CAST(:actor AS text))" if db.bind.dialect.name == "postgresql" else "EXISTS (SELECT 1 FROM json_each(supporting_auditor_user_ids) WHERE value=:actor)")
                    where += " AND (" + " OR ".join(owner_terms) + ")"
                    where += f" AND {status_sql} IN ({COMPLETE})" if view == "completed" else f" AND {status_sql} NOT IN ({TERMINAL})"
                    if view == "overdue":
                        if not due: continue
                        where += f" AND DATE({due}) < CURRENT_DATE"
                total += db.execute(text(f"SELECT count(*) FROM {spec['table']} WHERE {where}"), source_params).scalar_one()
                # Merge/paginate inside the database. Large offsets must not
                # materialize every preceding assignment in application memory.
                unions.append(f"SELECT CAST(id AS TEXT) AS id,title,CAST(status AS TEXT) AS status,DATE({due_sql}) AS due_date,'{key}' AS source FROM {spec['table']} WHERE {where}")
                params.update(source_params)
        except Exception:
            errors.append({"source": spec["label"], "message": "This assignment source could not be loaded. Refresh or open its register."})
    if unions:
        rows = db.execute(text("SELECT * FROM (" + " UNION ALL ".join(unions) + ") work ORDER BY due_date ASC NULLS LAST,title,id,source LIMIT :limit OFFSET :offset"), params).mappings().all()
        for row in rows:
            key = row["source"]
            spec = SOURCES[key]
            record_id = str(row["id"])
            items.append({"id": f"{key}:{record_id}", "source": key, "source_label": spec["label"], "record_id": record_id, "title": row["title"], "status": row["status"],
                "due_date": row["due_date"], "route": f"/maintenance/{ctx.amo_code}/quality/" + spec["path"].format(id=record_id), "watching": (key, record_id) in watches})
    return {"items": items, "total": total, "offset": offset, "limit": 30, "source_errors": errors, "view": view}


@router.post("/watch")
def watch(body: WatchBody, request: Request, ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_write_db)):
    _context(db, ctx)
    source = _source_row(db, ctx, body.source, body.record_id)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"quality-watch:{ctx.amo_id}:{ctx.user_id}:{body.source}:{body.record_id}"})
    existing = _watches(db, ctx).get((body.source, body.record_id))
    if not existing:
        existing = _save(db, WATCH_TABLE, ctx, {"title": source["title"], "owner_user_id": ctx.user_id, "source_type": "QMS_WATCH", "status": "ACTIVE", "payload": {"source": body.source, "record_id": body.record_id}}, event="WATCH_STARTED", request=request, module="inbox")
    db.commit()
    return {"watching": True, "id": existing["id"]}


@router.delete("/watch/{source}/{record_id}")
def unwatch(source: str, record_id: str, request: Request, ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_write_db)):
    _context(db, ctx)
    existing = _watches(db, ctx).get((source, record_id))
    if existing:
        _save(db, WATCH_TABLE, ctx, {"status": "INACTIVE", "payload": _payload(existing)}, existing=existing, event="WATCH_STOPPED", request=request, module="inbox")
    db.commit()
    return {"watching": False}
