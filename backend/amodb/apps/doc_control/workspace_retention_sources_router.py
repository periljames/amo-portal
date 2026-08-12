from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import evidence_models as em
from .workspace_service import get_manual, require_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Retention Sources"])


@router.get("/t/{tenant_slug}/documents/{manual_id}/retention-sources")
def retention_sources(
    tenant_slug: str,
    manual_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Return human-selectable controlled sources that may receive retention governance."""
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)

    revisions = (
        db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.manual_id == manual.id)
        .order_by(manual_models.ManualRevision.created_at.desc(), manual_models.ManualRevision.id.desc())
        .limit(500)
        .all()
    )
    evidence = (
        db.query(em.DocumentEvidenceAsset)
        .filter(
            em.DocumentEvidenceAsset.tenant_id == tenant.amo_id,
            em.DocumentEvidenceAsset.manual_id == manual.id,
        )
        .order_by(em.DocumentEvidenceAsset.created_at.desc(), em.DocumentEvidenceAsset.id.desc())
        .limit(500)
        .all()
    )

    generated_items: list[dict] = []
    generated_model = getattr(dm, "DocumentGeneratedRecord", None)
    if generated_model is not None:
        generated = (
            db.query(generated_model)
            .filter(
                generated_model.tenant_id == tenant.amo_id,
                generated_model.manual_id == manual.id,
            )
            .order_by(generated_model.id.desc())
            .limit(500)
            .all()
        )
        for row in generated:
            label = (
                getattr(row, "title", None)
                or getattr(row, "record_type", None)
                or getattr(row, "reference", None)
                or f"Generated record {row.id}"
            )
            generated_items.append({
                "id": str(row.id),
                "label": str(label),
                "revision_id": getattr(row, "revision_id", None),
                "status": str(getattr(row, "status", "CONTROLLED")),
            })

    return {
        "document": {"id": manual.id, "label": f"{manual.code} — {manual.title}"},
        "revisions": [
            {
                "id": row.id,
                "label": f"Revision {row.revision_number}",
                "status": row.status,
                "revision_id": row.id,
            }
            for row in revisions
        ],
        "evidence_assets": [
            {
                "id": row.id,
                "label": row.filename,
                "status": row.category,
                "revision_id": row.revision_id,
                "sha256": row.sha256,
            }
            for row in evidence
        ],
        "generated_records": generated_items,
        "bounded": True,
        "per_type_limit": 500,
    }
