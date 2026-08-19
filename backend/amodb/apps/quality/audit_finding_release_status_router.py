from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.database import get_read_db

from . import models
from .audit_external_access_models import QualityAuditFindingReleaseEvent
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(tags=["Quality finding release status"])


@router.get("/audits/{audit_id}/finding-releases")
def list_finding_release_status(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit_exists = db.query(models.QMSAudit.id).filter(
        models.QMSAudit.amo_id == ctx.amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if audit_exists is None:
        raise HTTPException(status_code=404, detail="Audit not found.")

    rows = db.query(QualityAuditFindingReleaseEvent).filter(
        QualityAuditFindingReleaseEvent.amo_id == ctx.amo_id,
        QualityAuditFindingReleaseEvent.audit_id == audit_id,
    ).order_by(
        QualityAuditFindingReleaseEvent.created_at.asc(),
        QualityAuditFindingReleaseEvent.id.asc(),
    ).all()
    latest: dict[uuid.UUID, QualityAuditFindingReleaseEvent] = {}
    for row in rows:
        latest[row.finding_id] = row
    return {
        "items": [
            {
                "finding_id": str(row.finding_id),
                "action": row.action,
                "include_objective_evidence": row.include_objective_evidence,
                "released_evidence_refs": list(row.released_evidence_refs or []),
                "reason": row.reason,
                "actor_user_id": row.actor_user_id,
                "created_at": row.created_at.isoformat(),
            }
            for row in latest.values()
        ]
    }
