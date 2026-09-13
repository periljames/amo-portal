from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_read_db

from .assurance_sources import programme_responsibility
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(prefix="/excellence/cockpit", tags=["Quality assurance cockpit detail"])
ViewContext = Literal["global", "mine"]


@router.get("/unscheduled-requirements")
def unscheduled_programme_requirements(
    view: ViewContext = Query(default="global"),
    period: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2200),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    where = [
        "p.amo_id = :amo_id",
        "p.programme_year = :period",
        "p.status IN ('APPROVED','ACTIVE','UNDER_REVIEW')",
        "i.schedule_id IS NULL",
        "COALESCE(i.state, 'PLANNED') NOT IN ('COMPLETED','CANCELLED')",
    ]
    params: dict[str, Any] = {"amo_id": ctx.amo_id, "period": period, "limit": limit, "offset": offset}
    if view == "mine":
        where.append(programme_responsibility(db))
        params["actor_user_id"] = ctx.user_id
    total = db.execute(text("SELECT COUNT(*) FROM quality_audit_programme_items i JOIN quality_audit_programmes p ON p.id = i.programme_id AND p.amo_id = i.amo_id WHERE " + " AND ".join(where)), params).scalar_one()
    rows = db.execute(
        text(
            "SELECT i.id, i.programme_id, p.programme_ref, p.title AS programme_title, "
            "i.title, i.audit_type, i.mandatory_surveillance, i.target_start, i.target_end, "
            "i.default_duration_days, i.default_location, i.lead_auditor_user_id, i.observer_auditor_user_id, "
            "i.auditee_user_id, i.state "
            "FROM quality_audit_programme_items i "
            "JOIN quality_audit_programmes p ON p.id = i.programme_id AND p.amo_id = i.amo_id "
            "WHERE " + " AND ".join(where) +
            " ORDER BY i.mandatory_surveillance DESC, i.target_start NULLS LAST, i.title, i.id LIMIT :limit OFFSET :offset"
        ),
        params,
    ).mappings().all()
    items = []
    for row in rows:
        item = dict(row)
        for field in ("target_start", "target_end"):
            if item.get(field) is not None:
                item[field] = item[field].isoformat()
        items.append(item)
    return {
        "items": items,
        "total_returned": len(items),
        "total": total, "limit": limit, "offset": offset,
        "view": view,
        "period": period,
        "planner_path": f"/maintenance/{ctx.amo_code}/quality/audits/plan",
        "programme_path": f"/maintenance/{ctx.amo_code}/quality/audits/program",
    }
