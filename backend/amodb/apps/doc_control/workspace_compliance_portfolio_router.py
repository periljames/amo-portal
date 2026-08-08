from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, aliased

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import governance_models as gm
from .workspace_service import require_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Compliance Portfolio"])

CompliancePortfolioView = Literal[
    "reviews",
    "external-sources",
    "relationships",
    "applicability",
    "superseded-references",
]


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _document(manual: manual_models.Manual) -> dict[str, str]:
    return {"id": manual.id, "code": manual.code, "title": manual.title}


def _pagination(page: int, per_page: int, total: int, returned: int) -> dict[str, int]:
    return {"page": page, "per_page": per_page, "total": total, "returned": returned}


def _facets(db: Session, tenant_id: str, tenant_pk: str, now: datetime) -> dict[str, int]:
    target_manual = aliased(manual_models.Manual)
    return {
        "reviews": db.query(func.count(dm.DocumentReviewPlan.id)).filter(
            dm.DocumentReviewPlan.tenant_id == tenant_id,
            dm.DocumentReviewPlan.status.in_(["SCHEDULED", "IN_PROGRESS"]),
        ).scalar() or 0,
        "external-sources": db.query(func.count(dm.ExternalDocumentSource.id)).filter(
            dm.ExternalDocumentSource.tenant_id == tenant_id,
            dm.ExternalDocumentSource.status != "ARCHIVED",
        ).scalar() or 0,
        "relationships": db.query(func.count(gm.DocumentGovernedRelationship.id)).filter(
            gm.DocumentGovernedRelationship.tenant_id == tenant_id,
            gm.DocumentGovernedRelationship.resolution_status != "CONFIRMED",
        ).scalar() or 0,
        "applicability": db.query(func.count(dm.DocumentApplicabilityRule.id)).filter(
            dm.DocumentApplicabilityRule.tenant_id == tenant_id,
            dm.DocumentApplicabilityRule.status != "ARCHIVED",
        ).scalar() or 0,
        "superseded-references": db.query(func.count(gm.DocumentGovernedRelationship.id)).join(
            target_manual,
            target_manual.id == gm.DocumentGovernedRelationship.target_manual_id,
        ).filter(
            gm.DocumentGovernedRelationship.tenant_id == tenant_id,
            target_manual.tenant_id == tenant_pk,
            gm.DocumentGovernedRelationship.target_revision_id.isnot(None),
            target_manual.current_published_rev_id.isnot(None),
            gm.DocumentGovernedRelationship.target_revision_id != target_manual.current_published_rev_id,
            gm.DocumentGovernedRelationship.resolution_status == "CONFIRMED",
        ).scalar() or 0,
    }


def _document_search(query, q: str | None, manual):
    if not q or not q.strip():
        return query
    needle = f"%{q.strip()}%"
    return query.filter((manual.code.ilike(needle)) | (manual.title.ilike(needle)))


@router.get("/t/{tenant_slug}/compliance-portfolio")
def get_compliance_portfolio(
    tenant_slug: str,
    view: CompliancePortfolioView = "reviews",
    q: str | None = Query(default=None, max_length=255),
    status: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Return bounded document-assurance work without inventing compliance scores."""
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    now = datetime.utcnow()
    offset = (page - 1) * per_page
    items: list[dict[str, Any]] = []

    if view == "reviews":
        query = db.query(dm.DocumentReviewPlan, manual_models.Manual, account_models.User).join(
            manual_models.Manual,
            manual_models.Manual.id == dm.DocumentReviewPlan.manual_id,
        ).outerjoin(
            account_models.User,
            account_models.User.id == dm.DocumentReviewPlan.owner_user_id,
        ).filter(
            dm.DocumentReviewPlan.tenant_id == tenant.amo_id,
            manual_models.Manual.tenant_id == tenant.id,
        )
        if status:
            query = query.filter(dm.DocumentReviewPlan.status == status.upper())
        else:
            query = query.filter(dm.DocumentReviewPlan.status.in_(["SCHEDULED", "IN_PROGRESS"]));
        query = _document_search(query, q, manual_models.Manual)
        total = query.count()
        rows = query.order_by(dm.DocumentReviewPlan.due_at.asc(), dm.DocumentReviewPlan.id.asc()).offset(offset).limit(per_page).all()
        for row, manual, owner in rows:
            due = row.due_at.replace(tzinfo=None) if row.due_at.tzinfo else row.due_at
            items.append({
                "id": row.id,
                "kind": "PERIODIC_REVIEW",
                "document": _document(manual),
                "revision_id": row.revision_id,
                "status": "OVERDUE" if row.status != "COMPLETED" and due < now else row.status,
                "due_at": _iso(row.due_at),
                "owner": (owner.full_name or owner.email) if owner else "Unassigned",
                "outcome": row.outcome,
                "target_path": f"/maintenance/{tenant_slug}/document-control/library/{manual.id}?tab=compliance",
            })
    elif view == "external-sources":
        latest_receipt_id = db.query(dm.ExternalRevisionReceipt.id).filter(
            dm.ExternalRevisionReceipt.tenant_id == tenant.amo_id,
            dm.ExternalRevisionReceipt.source_id == dm.ExternalDocumentSource.id,
        ).order_by(
            dm.ExternalRevisionReceipt.received_at.desc(),
            dm.ExternalRevisionReceipt.id.desc(),
        ).limit(1).correlate(dm.ExternalDocumentSource).scalar_subquery()
        query = db.query(dm.ExternalDocumentSource, manual_models.Manual, dm.ExternalRevisionReceipt).join(
            manual_models.Manual,
            manual_models.Manual.id == dm.ExternalDocumentSource.manual_id,
        ).outerjoin(
            dm.ExternalRevisionReceipt,
            dm.ExternalRevisionReceipt.id == latest_receipt_id,
        ).filter(
            dm.ExternalDocumentSource.tenant_id == tenant.amo_id,
            manual_models.Manual.tenant_id == tenant.id,
        )
        if status:
            query = query.filter(dm.ExternalDocumentSource.status == status.upper())
        if q and q.strip():
            needle = f"%{q.strip()}%"
            query = query.filter(
                (manual_models.Manual.code.ilike(needle))
                | (manual_models.Manual.title.ilike(needle))
                | (dm.ExternalDocumentSource.provider.ilike(needle))
                | (dm.ExternalDocumentSource.authority.ilike(needle))
            )
        total = query.count()
        rows = query.order_by(dm.ExternalDocumentSource.next_check_due_at.asc().nullslast(), dm.ExternalDocumentSource.updated_at.desc()).offset(offset).limit(per_page).all()
        for source, manual, receipt in rows:
            due = source.next_check_due_at.replace(tzinfo=None) if source.next_check_due_at and source.next_check_due_at.tzinfo else source.next_check_due_at
            assessment_required = bool(receipt and (receipt.currency_status == "UNVERIFIED" or receipt.applicability_status == "PENDING"))
            display_status = "ASSESSMENT_REQUIRED" if assessment_required else "DUE" if due and due < now else (receipt.currency_status if receipt else source.status)
            items.append({
                "id": source.id,
                "kind": "EXTERNAL_SOURCE",
                "document": _document(manual),
                "provider": source.provider,
                "authority": source.authority,
                "update_method": source.update_method,
                "status": display_status,
                "source_status": source.status,
                "last_checked_at": _iso(source.last_checked_at),
                "next_check_due_at": _iso(source.next_check_due_at),
                "received_revision": receipt.revision_label if receipt else None,
                "received_at": _iso(receipt.received_at) if receipt else None,
                "currency_status": receipt.currency_status if receipt else None,
                "applicability_status": receipt.applicability_status if receipt else None,
                "target_path": f"/maintenance/{tenant_slug}/document-control/library/{manual.id}?tab=compliance",
            })
    elif view == "relationships":
        query = db.query(gm.DocumentGovernedRelationship, manual_models.Manual).join(
            manual_models.Manual,
            manual_models.Manual.id == gm.DocumentGovernedRelationship.source_manual_id,
        ).filter(
            gm.DocumentGovernedRelationship.tenant_id == tenant.amo_id,
            manual_models.Manual.tenant_id == tenant.id,
        )
        if status:
            query = query.filter(gm.DocumentGovernedRelationship.resolution_status == status.upper())
        else:
            query = query.filter(gm.DocumentGovernedRelationship.resolution_status != "CONFIRMED")
        if q and q.strip():
            needle = f"%{q.strip()}%"
            query = query.filter(
                (manual_models.Manual.code.ilike(needle))
                | (manual_models.Manual.title.ilike(needle))
                | (gm.DocumentGovernedRelationship.exact_token.ilike(needle))
                | (gm.DocumentGovernedRelationship.relationship_type.ilike(needle))
                | (gm.DocumentGovernedRelationship.target_entity_type.ilike(needle))
            )
        total = query.count()
        rows = query.order_by(gm.DocumentGovernedRelationship.updated_at.desc()).offset(offset).limit(per_page).all()
        for row, manual in rows:
            items.append({
                "id": row.id,
                "kind": "RELATIONSHIP",
                "document": _document(manual),
                "relationship_type": row.relationship_type,
                "relationship_source": row.relationship_source,
                "status": row.resolution_status,
                "target": row.target_entity_type,
                "target_id": row.target_entity_id or row.target_manual_id,
                "page_number": row.page_number,
                "section_label": row.section_label,
                "confidence_percent": row.confidence_percent,
                "exact_token": row.exact_token,
                "target_path": f"/maintenance/{tenant_slug}/document-control/library/{manual.id}?tab=relationships",
            })
    elif view == "applicability":
        query = db.query(dm.DocumentApplicabilityRule, manual_models.Manual).join(
            manual_models.Manual,
            manual_models.Manual.id == dm.DocumentApplicabilityRule.manual_id,
        ).filter(
            dm.DocumentApplicabilityRule.tenant_id == tenant.amo_id,
            manual_models.Manual.tenant_id == tenant.id,
        )
        if status:
            query = query.filter(dm.DocumentApplicabilityRule.status == status.upper())
        else:
            query = query.filter(dm.DocumentApplicabilityRule.status != "ARCHIVED")
        query = _document_search(query, q, manual_models.Manual)
        total = query.count()
        rows = query.order_by(dm.DocumentApplicabilityRule.updated_at.desc()).offset(offset).limit(per_page).all()
        for row, manual in rows:
            items.append({
                "id": row.id,
                "kind": "APPLICABILITY",
                "document": _document(manual),
                "revision_id": row.revision_id,
                "rule_type": row.rule_type,
                "target_type": row.target_type,
                "target": row.target_value or row.target_id,
                "status": row.status,
                "source": row.source,
                "effective_from": _iso(row.effective_from),
                "effective_to": _iso(row.effective_to),
                "target_path": f"/maintenance/{tenant_slug}/document-control/library/{manual.id}?tab=compliance",
            })
    else:
        source_manual = aliased(manual_models.Manual)
        target_manual = aliased(manual_models.Manual)
        query = db.query(gm.DocumentGovernedRelationship, source_manual, target_manual).join(
            source_manual,
            source_manual.id == gm.DocumentGovernedRelationship.source_manual_id,
        ).join(
            target_manual,
            target_manual.id == gm.DocumentGovernedRelationship.target_manual_id,
        ).filter(
            gm.DocumentGovernedRelationship.tenant_id == tenant.amo_id,
            source_manual.tenant_id == tenant.id,
            target_manual.tenant_id == tenant.id,
            gm.DocumentGovernedRelationship.target_revision_id.isnot(None),
            target_manual.current_published_rev_id.isnot(None),
            gm.DocumentGovernedRelationship.target_revision_id != target_manual.current_published_rev_id,
            gm.DocumentGovernedRelationship.resolution_status == "CONFIRMED",
        )
        if q and q.strip():
            needle = f"%{q.strip()}%"
            query = query.filter(
                (source_manual.code.ilike(needle))
                | (source_manual.title.ilike(needle))
                | (target_manual.code.ilike(needle))
                | (target_manual.title.ilike(needle))
                | (gm.DocumentGovernedRelationship.exact_token.ilike(needle))
            )
        total = query.count()
        rows = query.order_by(gm.DocumentGovernedRelationship.updated_at.desc()).offset(offset).limit(per_page).all()
        for row, source, target in rows:
            items.append({
                "id": row.id,
                "kind": "SUPERSEDED_REFERENCE",
                "document": _document(source),
                "relationship_type": row.relationship_type,
                "status": "SUPERSEDED_REFERENCE",
                "referenced_document": _document(target),
                "referenced_revision_id": row.target_revision_id,
                "current_revision_id": target.current_published_rev_id,
                "page_number": row.page_number,
                "section_label": row.section_label,
                "exact_token": row.exact_token,
                "target_path": f"/maintenance/{tenant_slug}/document-control/library/{source.id}?tab=relationships",
            })

    return {
        "view": view,
        "items": items,
        "pagination": _pagination(page, per_page, total, len(items)),
        "facets": _facets(db, tenant.amo_id, tenant.id, now),
        "generated_at": now.isoformat(),
    }
