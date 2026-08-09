from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_read_db

from .audit_programme_models import QualityAuditProgramme, QualityAuditProgrammeItem
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(prefix="/audit-programmes/planner", tags=["Quality audit programme scheduling"])


@router.get("/queue")
def list_programme_scheduling_queue(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    """Return bounded approved/active programme requirements awaiting scheduling.

    This endpoint intentionally joins the governed programme requirement to its
    Audit Universe reference in one bounded query. The frontend must not fan out
    one programme-detail request per revision just to build the Planner queue.
    """

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = (
        db.query(QualityAuditProgrammeItem)
        .join(QualityAuditProgramme, QualityAuditProgramme.id == QualityAuditProgrammeItem.programme_id)
        .options(selectinload(QualityAuditProgrammeItem.universe_item))
        .filter(
            QualityAuditProgrammeItem.amo_id == ctx.amo_id,
            QualityAuditProgramme.amo_id == ctx.amo_id,
            QualityAuditProgramme.status.in_(["APPROVED", "ACTIVE"]),
            QualityAuditProgrammeItem.state == "PLANNED",
        )
    )
    total = int(query.order_by(None).count())
    rows = (
        query.order_by(
            QualityAuditProgrammeItem.target_start.asc().nullslast(),
            QualityAuditProgramme.programme_year.asc(),
            QualityAuditProgrammeItem.title.asc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "programme_id": str(item.programme_id),
                "programme_ref": item.programme.programme_ref,
                "programme_status": item.programme.status,
                "programme_year": item.programme.programme_year,
                "programme_revision_no": item.programme.revision_no,
                "programme_item_id": str(item.id),
                "universe_item_id": str(item.universe_item_id),
                "auditable_entity": item.universe_item.display_label if item.universe_item else None,
                "audit_type": item.audit_type,
                "title": item.title,
                "recurrence": item.recurrence,
                "mandatory_surveillance": bool(item.mandatory_surveillance),
                "target_start": item.target_start,
                "target_end": item.target_end,
                "prioritization_basis": item.prioritization_basis or [],
            }
            for item in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(rows) < total,
    }
