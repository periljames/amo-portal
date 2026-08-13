from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_integration_router import verify_source_entity
from .workspace_router import _applicability_payload
from .workspace_service import audit, get_manual, get_revision, require_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Applicability"])


def _normalize_target(db: Session, *, tenant, payload: schemas.ApplicabilityRuleCreate) -> schemas.ApplicabilityRuleCreate:
    target_type = str(payload.target_type or "").strip()
    target_id = str(payload.target_id or "").strip()
    target_value = str(payload.target_value or "").strip()
    source = str(payload.source or "").strip()
    if not target_id:
        if target_type.upper() not in {"", "GLOBAL", "ALL"}:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "APPLICABILITY_TARGET_INCOMPLETE",
                    "message": "Select a governed target record or use Global applicability.",
                },
            )
        return payload.model_copy(update={
            "target_type": "GLOBAL",
            "target_id": None,
            "target_value": target_value or "All applicable users and operations",
            "source": source or "DOCUMENT_CONTROL",
        })

    criteria = dict(payload.criteria or {})
    source_module = str(criteria.get("source_module") or "").strip().upper()
    source_table = str(criteria.get("source_table") or target_type).strip()
    if not source_module or not source_table:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "APPLICABILITY_TARGET_SOURCE_REQUIRED",
                "message": "Targeted applicability must reference a governed portal source module and record type.",
            },
        )
    verification = verify_source_entity(
        db,
        tenant=tenant,
        source_module=source_module,
        entity_type=source_table,
        entity_id=target_id,
        metadata={},
    )
    criteria.update({
        "source_module": source_module,
        "source_table": verification["source_table"],
        "status_snapshot": verification.get("status"),
        "verified": True,
    })
    return payload.model_copy(update={
        "target_type": verification["source_table"],
        "target_id": target_id,
        "target_value": target_value or str(verification.get("label") or target_id),
        "source": f"PORTAL:{source_module}",
        "criteria": criteria,
    })


@router.post("/t/{tenant_slug}/applicability", include_in_schema=False)
def create_verified_applicability(
    tenant_slug: str,
    payload: schemas.ApplicabilityRuleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    if payload.revision_id:
        get_revision(db, manual, payload.revision_id)
    payload = _normalize_target(db, tenant=tenant, payload=payload)
    if payload.effective_from and payload.effective_to and payload.effective_to < payload.effective_from:
        raise HTTPException(status_code=422, detail="Applicability end date cannot precede its start date")
    row = dm.DocumentApplicabilityRule(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=payload.revision_id,
        rule_type=payload.rule_type,
        target_type=payload.target_type,
        target_id=payload.target_id,
        target_value=payload.target_value,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        source=payload.source,
        criteria_json=dict(payload.criteria),
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()
    audit(
        db,
        tenant,
        request,
        "document.applicability.created",
        "document_applicability_rule",
        row.id,
        _applicability_payload(row),
    )
    db.commit()
    return _applicability_payload(row)
