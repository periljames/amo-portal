from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import governance_models as gm
from .workspace_service import audit, require_control_user, resolve_tenant, utcnow


router = APIRouter(prefix="/workspace", tags=["Document Control External Assessment"])
ASSESSMENT_REQUIRED_STATUSES = {"PENDING", "UNVERIFIED"}


class ExternalAssessmentIn(BaseModel):
    receipt_id: str = Field(min_length=1, max_length=36)
    applicability_status: Literal["APPLICABLE", "PARTIALLY_APPLICABLE", "NOT_APPLICABLE"]
    notes: str = Field(default="", max_length=4000)


def _source_or_404(db: Session, tenant_id: str, source_id: str) -> dm.ExternalDocumentSource:
    source = db.query(dm.ExternalDocumentSource).filter(
        dm.ExternalDocumentSource.id == source_id,
        dm.ExternalDocumentSource.tenant_id == tenant_id,
    ).first()
    if not source:
        raise HTTPException(status_code=404, detail="External document source not found")
    return source


def _affected_internal_documents(db: Session, tenant_id: str, external_manual_id: str) -> list[dict]:
    relationships = db.query(gm.DocumentGovernedRelationship).filter(
        gm.DocumentGovernedRelationship.tenant_id == tenant_id,
        gm.DocumentGovernedRelationship.resolution_status == "CONFIRMED",
        or_(
            gm.DocumentGovernedRelationship.source_manual_id == external_manual_id,
            gm.DocumentGovernedRelationship.target_manual_id == external_manual_id,
        ),
    ).all()
    candidate_ids: set[str] = set()
    for relationship in relationships:
        if relationship.source_manual_id and relationship.source_manual_id != external_manual_id:
            candidate_ids.add(relationship.source_manual_id)
        if relationship.target_manual_id and relationship.target_manual_id != external_manual_id:
            candidate_ids.add(relationship.target_manual_id)
    if not candidate_ids:
        return []
    rows = (
        db.query(manual_models.Manual, dm.DocumentControlProfile)
        .outerjoin(
            dm.DocumentControlProfile,
            (dm.DocumentControlProfile.manual_id == manual_models.Manual.id)
            & (dm.DocumentControlProfile.tenant_id == tenant_id),
        )
        .filter(manual_models.Manual.id.in_(candidate_ids))
        .order_by(manual_models.Manual.code.asc())
        .all()
    )
    return [
        {
            "id": manual.id,
            "code": manual.code,
            "title": manual.title,
            "document_class": profile.document_class if profile else "INTERNAL",
        }
        for manual, profile in rows
        if not profile or profile.document_class != "EXTERNAL"
    ]


def _context(db: Session, tenant_id: str, source: dm.ExternalDocumentSource) -> dict:
    receipts = (
        db.query(dm.ExternalRevisionReceipt)
        .filter(
            dm.ExternalRevisionReceipt.tenant_id == tenant_id,
            dm.ExternalRevisionReceipt.source_id == source.id,
        )
        .order_by(dm.ExternalRevisionReceipt.received_at.desc(), dm.ExternalRevisionReceipt.id.desc())
        .limit(25)
        .all()
    )
    latest = receipts[0] if receipts else None
    current = next((row for row in receipts if row.currency_status == "CURRENT"), None)
    affected = _affected_internal_documents(db, tenant_id, source.manual_id)
    assessment_required = bool(
        latest and (
            latest.applicability_status in ASSESSMENT_REQUIRED_STATUSES
            or latest.currency_status == "UNVERIFIED"
        )
    )
    return {
        "source": {
            "id": source.id,
            "manual_id": source.manual_id,
            "provider": source.provider,
            "authority": source.authority,
            "subscription_reference": source.subscription_reference,
            "access_url": source.access_url,
            "status": source.status,
            "last_checked_at": source.last_checked_at.isoformat() if source.last_checked_at else None,
            "next_check_due_at": source.next_check_due_at.isoformat() if source.next_check_due_at else None,
        },
        "received_revision": {
            "id": latest.id,
            "revision_label": latest.revision_label,
            "publication_date": latest.publication_date.isoformat() if latest.publication_date else None,
            "received_at": latest.received_at.isoformat() if latest.received_at else None,
            "currency_status": latest.currency_status,
            "applicability_status": latest.applicability_status,
            "checksum_sha256": latest.checksum_sha256,
            "notes": latest.notes,
            "evidence": latest.evidence_json or [],
        } if latest else None,
        "current_revision": {
            "id": current.id,
            "revision_label": current.revision_label,
            "publication_date": current.publication_date.isoformat() if current.publication_date else None,
            "currency_status": current.currency_status,
            "applicability_status": current.applicability_status,
        } if current else None,
        "affected_internal_documents": affected,
        "assessment_required": assessment_required,
        "work_item_status": "NEW_REVISION_REQUIRES_ASSESSMENT" if assessment_required else "ASSESSMENT_COMPLETE",
    }


@router.get("/t/{tenant_slug}/external-sources/{source_id}/assessment")
def get_external_assessment(
    tenant_slug: str,
    source_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    source = _source_or_404(db, tenant.amo_id, source_id)
    return _context(db, tenant.amo_id, source)


@router.post("/t/{tenant_slug}/external-sources/{source_id}/assessment")
def assess_external_revision(
    tenant_slug: str,
    source_id: str,
    payload: ExternalAssessmentIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    source = _source_or_404(db, tenant.amo_id, source_id)
    receipt = db.query(dm.ExternalRevisionReceipt).filter(
        dm.ExternalRevisionReceipt.id == payload.receipt_id,
        dm.ExternalRevisionReceipt.source_id == source.id,
        dm.ExternalRevisionReceipt.tenant_id == tenant.amo_id,
    ).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="External revision receipt not found")

    before = {
        "applicability_status": receipt.applicability_status,
        "notes": receipt.notes,
        "evidence": list(receipt.evidence_json or []),
    }
    evidence = list(receipt.evidence_json or [])
    evidence.append({
        "kind": "APPLICABILITY_ASSESSMENT",
        "status": payload.applicability_status,
        "assessed_by_user_id": str(current_user.id),
        "assessed_at": utcnow().isoformat(),
        "notes": payload.notes or None,
    })
    receipt.applicability_status = payload.applicability_status
    receipt.notes = payload.notes or receipt.notes
    receipt.evidence_json = evidence

    audit(
        db,
        tenant,
        request,
        "document.external_revision.assessed",
        "external_revision_receipt",
        receipt.id,
        {
            "source_id": source.id,
            "manual_id": source.manual_id,
            "revision_label": receipt.revision_label,
            "before": before,
            "after": {"applicability_status": receipt.applicability_status, "notes": receipt.notes},
            "affected_internal_document_ids": [item["id"] for item in _affected_internal_documents(db, tenant.amo_id, source.manual_id)],
        },
    )
    db.commit()
    return _context(db, tenant.amo_id, source)
