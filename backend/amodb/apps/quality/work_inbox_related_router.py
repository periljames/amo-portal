"""Read-only connections to governed Training, Document Control and Provider work.

Each adapter uses its authoritative source; no generic inbox mutation can satisfy
a regulated approval, acknowledgement, training outcome or external identity.
"""
from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_read_db
from .tenant_security import (
    TenantContext, assert_quality_permission, has_quality_permission,
    resolve_tenant_context, set_postgres_tenant_context,
)

router = APIRouter(tags=["Connected Quality Work"])

# These are constant, audited SQL projections. Never interpolate user-selected
# identifiers into SQL; bind tenant, assignee, search, limit and offset.
SOURCES = {
    "training-steps": {
        "label": "Training workflow",
        "permission": "qms.training.view",
        "projection": """SELECT CAST(s.id AS TEXT) id,
              (w.title || ' · ' || s.label) title,
              CAST(s.status AS TEXT) status,
              DATE(w.due_at) due_date
          FROM training_workflow_steps s
          JOIN training_workflow_instances w ON w.id=s.workflow_instance_id AND w.amo_id=s.amo_id
          WHERE s.amo_id=:amo AND s.assigned_user_id=:actor
            AND UPPER(s.status) NOT IN ('DONE','COMPLETE','COMPLETED','CANCELLED','REJECTED')
            AND UPPER(w.status) NOT IN ('DONE','COMPLETE','COMPLETED','CLOSED','CANCELLED','REJECTED')""",
        "route": "training/competence",
        "next_action": "Continue your assigned training workflow",
        "scope": "ASSIGNED",
    },
    "training-remedial": {
        "label": "Remedial training",
        "permission": "qms.training.view",
        "projection": """SELECT CAST(id AS TEXT) id,
              COALESCE(NULLIF(required_activity,''),'Complete the required remedial activity') title,
              CAST(status AS TEXT) status,
              DATE(due_date) due_date
          FROM training_remedial_actions
          WHERE amo_id=:amo AND owner_user_id=:actor
            AND UPPER(status) NOT IN ('DONE','COMPLETE','COMPLETED','CLOSED','CANCELLED','REJECTED')""",
        "route": "training/competence/assessments",
        "next_action": "Complete remedial training and submit evidence",
        "scope": "ASSIGNED",
    },
    "document-reviews": {
        "label": "Controlled document review",
        "permission": "qms.document.view",
        "projection": """SELECT CAST(r.id AS TEXT) id,
              ('Review controlled manual · ' || COALESCE(m.title,m.code,'Manual')) title,
              CAST(r.status AS TEXT) status,
              DATE(r.due_at) due_date
          FROM document_review_plans r
          JOIN manuals m ON m.id=r.manual_id AND m.tenant_id=r.tenant_id
          WHERE r.tenant_id=:amo AND r.owner_user_id=:actor
            AND UPPER(r.status) NOT IN ('DONE','COMPLETE','COMPLETED','CLOSED','CANCELLED','REJECTED')""",
        "route": "quality/documents/library",
        "next_action": "Review the controlled manual in Document Control",
        "scope": "ASSIGNED",
    },
    "document-acknowledgements": {
        "label": "Document acknowledgement",
        "permission": "qms.document.view",
        "projection": """SELECT CAST(r.id AS TEXT) id,
              ('Acknowledge controlled distribution · ' || c.title) title,
              CAST(r.status AS TEXT) status,
              DATE(COALESCE(r.due_at,c.due_at)) due_date
          FROM document_distribution_campaign_recipients r
          JOIN document_distribution_campaigns c ON c.id=r.campaign_id AND c.tenant_id=r.tenant_id
          WHERE r.tenant_id=:amo AND r.recipient_user_id=:actor
            AND c.issued_at IS NOT NULL
            AND c.acknowledgement_required IS TRUE
            AND UPPER(r.status) NOT IN ('DONE','COMPLETE','COMPLETED','ACKNOWLEDGED','CANCELLED','REJECTED')""",
        "route": "quality/documents/distribution",
        "next_action": "Acknowledge the issued controlled document",
        "scope": "ASSIGNED",
    },
    "provider-approvals": {
        "label": "External provider account",
        "permission": "qms.external.manage",
        "projection": """SELECT CAST(g.id AS TEXT) id,
              ('Review verified provider representative · ' || s.legal_name || ' · ' || i.email) title,
              'AWAITING_QUALITY_APPROVAL' status,
              NULL due_date
          FROM external_tenant_grants g
          JOIN external_identities i ON i.id=g.identity_id
          JOIN external_tenant_providers p ON p.id=g.tenant_provider_id AND p.amo_id=g.amo_id
          JOIN procurement_suppliers s ON s.id=p.supplier_id AND s.amo_id=p.amo_id
          WHERE g.amo_id=:amo AND UPPER(g.status)='PENDING'
            AND i.verified_at IS NOT NULL""",
        "route": "quality/external-accounts?view=accounts",
        "next_action": "Quality Manager to review the verified account grant",
        "scope": "SHARED_REVIEW",
    },
}


@router.get("/related")
def related_work(
    category: Literal["all", "overdue", "due-today", "upcoming"] = Query("all"),
    source: str = Query("", max_length=40),
    q: str = Query("", max_length=80),
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(30, ge=1, le=50),
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Session = Depends(get_read_db),
):
    assert_quality_permission(db, ctx, "qms.inbox.view")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    if source and source not in SOURCES:
        raise HTTPException(422, "Choose a supported connected-work source.")
    errors: list[dict] = []
    expressions: list[str] = []
    params = {"amo": ctx.amo_id, "actor": ctx.user_id, "q": "%" + q.lower().strip() + "%",
              "limit": limit, "offset": offset}
    total = 0
    filter_sql = " WHERE 1=1"
    if q.strip():
        filter_sql += " AND LOWER(COALESCE(title,'')) LIKE :q"
    if category == "overdue":
        filter_sql += " AND due_date < CURRENT_DATE"
    elif category == "due-today":
        filter_sql += " AND due_date = CURRENT_DATE"
    elif category == "upcoming":
        filter_sql += " AND (due_date > CURRENT_DATE OR due_date IS NULL)"
    for key, spec in SOURCES.items():
        if source and key != source:
            continue
        if not has_quality_permission(db, ctx, spec["permission"]):
            continue
        scoped = f"({spec['projection']})"
        try:
            with db.begin_nested():
                count = db.execute(text(
                    f"SELECT COUNT(*) FROM {scoped} scoped {filter_sql}"
                ), params).scalar_one()
                # Append only after the source was successfully queried.
                expressions.append(
                    "SELECT id,title,status,due_date,'" + key +
                    "' source FROM " + scoped + " scoped " + filter_sql
                )
                total += int(count or 0)
        except Exception:
            errors.append({
                "source": spec["label"],
                "message": "This connected workflow source is currently unavailable.",
            })
    items = []
    if expressions:
        rows = db.execute(text(
            "SELECT * FROM (" + " UNION ALL ".join(expressions) +
            ") connected ORDER BY CASE WHEN due_date < CURRENT_DATE THEN 0 "
            "WHEN due_date = CURRENT_DATE THEN 1 "
            "WHEN due_date IS NULL THEN 3 ELSE 2 END, "
            "due_date ASC NULLS LAST,title,id,source LIMIT :limit OFFSET :offset"
        ), params).mappings().all()
        for row in rows:
            spec = SOURCES[row["source"]]
            status = str(row["status"] or "").upper()
            blocked = row["source"] == "training-steps" and status in {"PENDING", "QUEUED"}
            action = (
                "Await activation of an earlier training step"
                if blocked else spec["next_action"]
            )
            items.append({
                "id": row["source"] + ":" + str(row["id"]),
                "record_id": str(row["id"]),
                "source": row["source"],
                "source_label": spec["label"],
                "title": row["title"],
                "status": status,
                "due_date": row["due_date"],
                "route": (
                    f"/maintenance/{ctx.amo_code}/quality/external-accounts?view=accounts&grant={quote(str(row['id']), safe='')}"
                    if row["source"] == "provider-approvals"
                    else f"/maintenance/{ctx.amo_code}/" + spec["route"]
                ),
                "scope": spec["scope"],
                "next_action": action,
                "blocked": blocked,
            })
    return {
        "items": items, "total": total, "limit": limit, "offset": offset,
        "source_errors": errors, "category": category, "source": source,
        "view": "related",
    }
