"""Validated controller resolution of governed document references."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import knowledge_models as km
from .workspace_service import require_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Knowledge Graph"])


class ValidatedReferenceResolution(BaseModel):
    target_manual_id: str
    target_revision_id: str | None = None
    relationship_type: Literal[
        "REFERENCES",
        "IMPLEMENTS",
        "USES_FORM",
        "USES_CHECKLIST",
        "UPDATES_REGISTER",
        "CREATES_RECORD",
    ] = "REFERENCES"
    resolution_policy: Literal["CURRENT_EFFECTIVE", "PINNED_REVISION"] = "CURRENT_EFFECTIVE"
    comments: str = Field(min_length=3, max_length=2000)


def _revision_is_approved_immutable(revision: manual_models.ManualRevision | None) -> bool:
    if not revision:
        return False
    status = str(getattr(revision.status_enum, "value", revision.status_enum or "")).upper()
    return status == "PUBLISHED" and bool(revision.immutable_locked)


def _audit(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    user: account_models.User,
    request: Request,
    entity_id: str,
    diff: dict[str, Any],
) -> None:
    db.add(
        manual_models.ManualAuditLog(
            tenant_id=tenant.id,
            actor_id=user.id,
            action="documentation.reference.verified",
            entity_type="documentation_reference",
            entity_id=entity_id,
            ip_device=(
                f"{request.client.host if request.client else 'unknown'}::"
                f"{request.headers.get('user-agent', 'n/a')}"
            ),
            diff_json=diff,
        )
    )


@router.post("/t/{tenant_slug}/knowledge/references/{reference_id}/resolve")
def resolve_reference_with_revision_validation(
    tenant_slug: str,
    reference_id: str,
    payload: ValidatedReferenceResolution,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = (
        db.query(km.DocumentationReference)
        .filter(
            km.DocumentationReference.id == reference_id,
            km.DocumentationReference.tenant_id == tenant.amo_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Reference occurrence not found")

    target = (
        db.query(manual_models.Manual)
        .filter(
            manual_models.Manual.id == payload.target_manual_id,
            manual_models.Manual.tenant_id == tenant.id,
        )
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Target document not found")

    if payload.resolution_policy == "CURRENT_EFFECTIVE":
        target_revision_id = target.current_published_rev_id
        if not target_revision_id:
            raise HTTPException(status_code=409, detail="The target has no effective published revision")
    else:
        target_revision_id = payload.target_revision_id
        if not target_revision_id:
            raise HTTPException(status_code=422, detail="A pinned resolution requires a target revision")

    revision = (
        db.query(manual_models.ManualRevision)
        .filter(
            manual_models.ManualRevision.id == target_revision_id,
            manual_models.ManualRevision.manual_id == target.id,
        )
        .first()
    )
    if not revision:
        raise HTTPException(status_code=404, detail="Target revision not found")
    if not _revision_is_approved_immutable(revision):
        raise HTTPException(
            status_code=409,
            detail="A verified reference may target only a published immutable revision",
        )

    now = datetime.utcnow()
    row.target_manual_id = target.id
    row.target_revision_id = revision.id
    row.relationship_type = payload.relationship_type
    row.resolution_policy = payload.resolution_policy
    row.status = "VERIFIED"
    row.confidence_percent = 100
    row.verified_by_user_id = current_user.id
    row.verified_at = now
    row.last_checked_at = now
    row.candidates_json = []
    _audit(
        db,
        tenant=tenant,
        user=current_user,
        request=request,
        entity_id=row.id,
        diff={
            "target_manual_id": target.id,
            "target_revision_id": revision.id,
            "relationship_type": row.relationship_type,
            "resolution_policy": row.resolution_policy,
            "comments": payload.comments,
        },
    )
    db.commit()
    return {
        "id": row.id,
        "status": row.status,
        "target_manual_id": row.target_manual_id,
        "target_revision_id": row.target_revision_id,
    }


__all__ = ["_revision_is_approved_immutable", "router"]
