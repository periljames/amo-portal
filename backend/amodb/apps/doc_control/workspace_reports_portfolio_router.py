from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from .workspace_service import require_control_user, resolve_tenant, serialize_revision, utcnow


router = APIRouter(prefix="/workspace", tags=["Document Control Reports Portfolio"])


def _pagination(page: int, per_page: int, total: int, returned: int) -> dict[str, int]:
    return {"page": page, "per_page": per_page, "total": total, "returned": returned}


def _overdue_summary(db: Session, tenant_id: str) -> dict[str, int]:
    now = utcnow()
    today = date.today()
    return {
        "acknowledgements": int(
            db.query(func.count(dm.DocumentDistributionRecipient.id)).filter(
                dm.DocumentDistributionRecipient.tenant_id == tenant_id,
                dm.DocumentDistributionRecipient.status == "PENDING",
                dm.DocumentDistributionRecipient.due_at.isnot(None),
                dm.DocumentDistributionRecipient.due_at < now,
            ).scalar() or 0
        ),
        "periodic_reviews": int(
            db.query(func.count(dm.DocumentReviewPlan.id)).filter(
                dm.DocumentReviewPlan.tenant_id == tenant_id,
                dm.DocumentReviewPlan.status.in_(["SCHEDULED", "IN_PROGRESS"]),
                dm.DocumentReviewPlan.due_at < now,
            ).scalar() or 0
        ),
        "external_currency": int(
            db.query(func.count(dm.ExternalDocumentSource.id)).filter(
                dm.ExternalDocumentSource.tenant_id == tenant_id,
                dm.ExternalDocumentSource.status == "ACTIVE",
                dm.ExternalDocumentSource.next_check_due_at.isnot(None),
                dm.ExternalDocumentSource.next_check_due_at < now,
            ).scalar() or 0
        ),
        "controlled_copy_returns": int(
            db.query(func.count(dm.DocumentControlledCopy.id)).filter(
                dm.DocumentControlledCopy.tenant_id == tenant_id,
                dm.DocumentControlledCopy.status == "ISSUED",
                dm.DocumentControlledCopy.due_back_at.isnot(None),
                dm.DocumentControlledCopy.due_back_at < now,
            ).scalar() or 0
        ),
        "document_reviews": int(
            db.query(func.count(dm.DocumentControlProfile.id)).filter(
                dm.DocumentControlProfile.tenant_id == tenant_id,
                dm.DocumentControlProfile.next_review_due.isnot(None),
                dm.DocumentControlProfile.next_review_due < today,
            ).scalar() or 0
        ),
    }


@router.get("/t/{tenant_slug}/reports-portfolio")
def get_reports_portfolio(
    tenant_slug: str,
    q: str | None = Query(default=None, max_length=255),
    document_class: str | None = Query(default=None, max_length=32),
    lifecycle_status: str | None = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Return a bounded master-register evidence view for Document Control.

    Deliberate exports may use separate report/export routes, but the interactive
    Reports workspace never loads the complete tenant document population.
    """
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    offset = (page - 1) * per_page

    query = db.query(manual_models.Manual).filter(manual_models.Manual.tenant_id == tenant.id)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        query = query.filter(or_(
            manual_models.Manual.code.ilike(needle),
            manual_models.Manual.title.ilike(needle),
            manual_models.Manual.manual_type.ilike(needle),
        ))
    if lifecycle_status:
        query = query.filter(manual_models.Manual.status == lifecycle_status.upper())
    if document_class:
        wanted_class = document_class.upper()
        query = query.outerjoin(
            dm.DocumentControlProfile,
            and_(
                dm.DocumentControlProfile.manual_id == manual_models.Manual.id,
                dm.DocumentControlProfile.tenant_id == tenant.amo_id,
            ),
        )
        if wanted_class == "INTERNAL":
            query = query.filter(or_(
                dm.DocumentControlProfile.id.is_(None),
                dm.DocumentControlProfile.document_class == "INTERNAL",
            ))
        else:
            query = query.filter(dm.DocumentControlProfile.document_class == wanted_class)

    total = int(query.order_by(None).count())
    manuals = query.order_by(manual_models.Manual.code.asc()).offset(offset).limit(per_page).all()
    manual_ids = [manual.id for manual in manuals]

    profiles = {
        row.manual_id: row
        for row in db.query(dm.DocumentControlProfile).filter(
            dm.DocumentControlProfile.tenant_id == tenant.amo_id,
            dm.DocumentControlProfile.manual_id.in_(manual_ids or ["-"]),
        ).all()
    }
    revisions = (
        db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.manual_id.in_(manual_ids or ["-"]))
        .order_by(manual_models.ManualRevision.created_at.desc(), manual_models.ManualRevision.id.desc())
        .all()
    )
    latest_by_manual: dict[str, manual_models.ManualRevision] = {}
    revision_by_id: dict[str, manual_models.ManualRevision] = {}
    for revision in revisions:
        latest_by_manual.setdefault(revision.manual_id, revision)
        revision_by_id[revision.id] = revision

    items: list[dict[str, Any]] = []
    for manual in manuals:
        profile = profiles.get(manual.id)
        latest = latest_by_manual.get(manual.id)
        effective = revision_by_id.get(manual.current_published_rev_id or "")
        items.append({
            "manual_id": manual.id,
            "code": manual.code,
            "title": manual.title,
            "manual_type": manual.manual_type,
            "lifecycle_status": manual.status,
            "document_class": profile.document_class if profile else "INTERNAL",
            "owner_department": profile.owner_department if profile else manual.owner_role,
            "regulated": bool(profile and profile.regulated_flag),
            "restricted": bool(profile and profile.restricted_flag),
            "latest_revision": serialize_revision(latest),
            "effective_revision": serialize_revision(effective),
            "next_review_due": profile.next_review_due.isoformat() if profile and profile.next_review_due else None,
        })

    return {
        "generated_at": utcnow().isoformat(),
        "tenant": tenant.slug,
        "summary": _overdue_summary(db, tenant.amo_id),
        "items": items,
        "pagination": _pagination(page, per_page, total, len(items)),
    }
