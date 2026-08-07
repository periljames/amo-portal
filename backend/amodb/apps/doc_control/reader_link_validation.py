"""Tenant-scoped validation for governed reader links to real QMS records."""
from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.quality import models as quality_models


ENTITY_MODELS = {
    "QMS_AUDIT": quality_models.QMSAudit,
    "AUDIT": quality_models.QMSAudit,
    "QMS_FINDING": quality_models.QMSAuditFinding,
    "FINDING": quality_models.QMSAuditFinding,
    "QMS_CORRECTIVE_ACTION": quality_models.QMSCorrectiveAction,
    "CORRECTIVE_ACTION": quality_models.QMSCorrectiveAction,
    "CAR": quality_models.QMSCorrectiveAction,
    "CAP": quality_models.QMSCorrectiveAction,
}


def validate_qms_link(db: Session, *, tenant_id: str, entity_type: str | None, entity_id: str | None) -> dict | None:
    if not entity_type and not entity_id:
        return None
    if not entity_type or not entity_id:
        raise HTTPException(status_code=422, detail="Both linked entity type and ID are required")
    kind = entity_type.strip().upper()
    model = ENTITY_MODELS.get(kind)
    if not model:
        raise HTTPException(status_code=422, detail=f"Unsupported governed QMS link type: {kind}")
    try:
        entity_uuid = uuid.UUID(str(entity_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="Linked QMS entity ID is not a valid UUID") from exc
    row = db.query(model).filter(model.id == entity_uuid, model.amo_id == tenant_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Linked QMS record was not found in the active AMO")
    if isinstance(row, quality_models.QMSAudit):
        return {"entity_type": "QMS_AUDIT", "entity_id": str(row.id), "reference": row.audit_ref, "status": str(getattr(row.status, "value", row.status))}
    if isinstance(row, quality_models.QMSAuditFinding):
        return {"entity_type": "QMS_FINDING", "entity_id": str(row.id), "reference": row.finding_ref, "audit_id": str(row.audit_id), "status": "CLOSED" if row.closed_at else "OPEN"}
    return {"entity_type": "QMS_CORRECTIVE_ACTION", "entity_id": str(row.id), "finding_id": str(row.finding_id), "status": str(getattr(row.status, "value", row.status))}
