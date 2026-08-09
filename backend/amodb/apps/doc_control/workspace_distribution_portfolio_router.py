from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from .workspace_service import require_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Distribution Portfolio"])

DistributionPortfolioView = Literal[
    "campaigns",
    "pending-acknowledgements",
    "overdue-acknowledgements",
    "physical-copies",
    "recalls",
]


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _document(manual: manual_models.Manual) -> dict[str, str]:
    return {"id": manual.id, "code": manual.code, "title": manual.title}


def _pagination(page: int, per_page: int, total: int, returned: int) -> dict[str, int]:
    return {"page": page, "per_page": per_page, "total": total, "returned": returned}


def _apply_document_search(query, q: str | None):
    if not q or not q.strip():
        return query
    needle = f"%{q.strip()}%"
    return query.filter(
        (manual_models.Manual.code.ilike(needle))
        | (manual_models.Manual.title.ilike(needle))
    )


def _facets(db: Session, tenant_id: str, now: datetime) -> dict[str, int]:
    pending_base = db.query(func.count(dm.DocumentDistributionRecipient.id)).filter(
        dm.DocumentDistributionRecipient.tenant_id == tenant_id,
        dm.DocumentDistributionRecipient.status == "PENDING",
    )
    campaign_count = db.query(func.count(dm.DocumentDistributionCampaign.id)).filter(
        dm.DocumentDistributionCampaign.tenant_id == tenant_id,
        dm.DocumentDistributionCampaign.status.in_(["DRAFT", "ISSUED"]),
    ).scalar() or 0
    overdue_count = pending_base.filter(
        dm.DocumentDistributionRecipient.due_at.isnot(None),
        dm.DocumentDistributionRecipient.due_at < now,
    ).scalar() or 0
    pending_count = pending_base.filter(
        (dm.DocumentDistributionRecipient.due_at.is_(None))
        | (dm.DocumentDistributionRecipient.due_at >= now),
    ).scalar() or 0
    physical_count = db.query(func.count(dm.DocumentControlledCopy.id)).filter(
        dm.DocumentControlledCopy.tenant_id == tenant_id,
        dm.DocumentControlledCopy.status.notin_(["DESTROYED"]),
    ).scalar() or 0
    recall_count = db.query(func.count(dm.DocumentControlledCopy.id)).filter(
        dm.DocumentControlledCopy.tenant_id == tenant_id,
        dm.DocumentControlledCopy.status == "RECALLED",
    ).scalar() or 0
    return {
        "campaigns": campaign_count,
        "pending-acknowledgements": pending_count,
        "overdue-acknowledgements": overdue_count,
        "physical-copies": physical_count,
        "recalls": recall_count,
    }


@router.get("/t/{tenant_slug}/distribution-portfolio")
def get_distribution_portfolio(
    tenant_slug: str,
    view: DistributionPortfolioView = "campaigns",
    q: str | None = Query(default=None, max_length=255),
    status: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Return a bounded distribution/custody operating view.

    Campaign, acknowledgement and physical-custody state is normalized for the
    daily-use DMS while existing mutation endpoints remain authoritative.
    """
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    now = datetime.utcnow()
    offset = (page - 1) * per_page
    items: list[dict[str, Any]] = []

    if view == "campaigns":
        query = db.query(dm.DocumentDistributionCampaign, manual_models.Manual).join(
            manual_models.Manual,
            manual_models.Manual.id == dm.DocumentDistributionCampaign.manual_id,
        ).filter(
            dm.DocumentDistributionCampaign.tenant_id == tenant.amo_id,
            manual_models.Manual.tenant_id == tenant.id,
        )
        if status:
            query = query.filter(dm.DocumentDistributionCampaign.status == status.upper())
        query = _apply_document_search(query, q)
        total = query.count()
        rows = query.order_by(
            dm.DocumentDistributionCampaign.updated_at.desc(),
            dm.DocumentDistributionCampaign.id.desc(),
        ).offset(offset).limit(per_page).all()
        campaign_ids = [row.id for row, _manual in rows]
        recipient_counts: dict[str, dict[str, int]] = {}
        if campaign_ids:
            grouped = db.query(
                dm.DocumentDistributionRecipient.campaign_id,
                func.count(dm.DocumentDistributionRecipient.id).label("total"),
                func.sum(case((dm.DocumentDistributionRecipient.status == "ACKNOWLEDGED", 1), else_=0)).label("acknowledged"),
                func.sum(case((dm.DocumentDistributionRecipient.status == "PENDING", 1), else_=0)).label("pending"),
                func.sum(case((
                    (dm.DocumentDistributionRecipient.status == "PENDING")
                    & dm.DocumentDistributionRecipient.due_at.isnot(None)
                    & (dm.DocumentDistributionRecipient.due_at < now),
                    1,
                ), else_=0)).label("overdue"),
            ).filter(
                dm.DocumentDistributionRecipient.tenant_id == tenant.amo_id,
                dm.DocumentDistributionRecipient.campaign_id.in_(campaign_ids),
            ).group_by(dm.DocumentDistributionRecipient.campaign_id).all()
            recipient_counts = {
                campaign_id: {
                    "total": int(total_count or 0),
                    "acknowledged": int(acknowledged or 0),
                    "pending": int(pending or 0),
                    "overdue": int(overdue or 0),
                }
                for campaign_id, total_count, acknowledged, pending, overdue in grouped
            }
        for row, manual in rows:
            items.append({
                "id": row.id,
                "kind": "CAMPAIGN",
                "document": _document(manual),
                "revision_id": row.revision_id,
                "title": row.title,
                "status": row.status,
                "due_at": _iso(row.due_at),
                "issued_at": _iso(row.issued_at),
                "acknowledgement_required": bool(row.acknowledgement_required),
                "recipients": recipient_counts.get(row.id, {"total": 0, "acknowledged": 0, "pending": 0, "overdue": 0}),
                "target_path": f"/maintenance/{tenant_slug}/document-control/distribution/{row.id}",
            })
    elif view in {"pending-acknowledgements", "overdue-acknowledgements"}:
        query = db.query(
            dm.DocumentDistributionRecipient,
            dm.DocumentDistributionCampaign,
            manual_models.Manual,
            account_models.User,
        ).join(
            dm.DocumentDistributionCampaign,
            dm.DocumentDistributionCampaign.id == dm.DocumentDistributionRecipient.campaign_id,
        ).join(
            manual_models.Manual,
            manual_models.Manual.id == dm.DocumentDistributionCampaign.manual_id,
        ).outerjoin(
            account_models.User,
            account_models.User.id == dm.DocumentDistributionRecipient.recipient_user_id,
        ).filter(
            dm.DocumentDistributionRecipient.tenant_id == tenant.amo_id,
            dm.DocumentDistributionRecipient.status == "PENDING",
            manual_models.Manual.tenant_id == tenant.id,
        )
        if view == "overdue-acknowledgements":
            query = query.filter(
                dm.DocumentDistributionRecipient.due_at.isnot(None),
                dm.DocumentDistributionRecipient.due_at < now,
            )
        else:
            query = query.filter(
                (dm.DocumentDistributionRecipient.due_at.is_(None))
                | (dm.DocumentDistributionRecipient.due_at >= now),
            )
        if status:
            query = query.filter(dm.DocumentDistributionRecipient.status == status.upper())
        query = _apply_document_search(query, q)
        total = query.count()
        rows = query.order_by(
            dm.DocumentDistributionRecipient.due_at.asc().nullslast(),
            dm.DocumentDistributionRecipient.id.asc(),
        ).offset(offset).limit(per_page).all()
        for recipient, campaign, manual, user in rows:
            items.append({
                "id": recipient.id,
                "kind": "ACKNOWLEDGEMENT",
                "document": _document(manual),
                "revision_id": campaign.revision_id,
                "campaign_id": campaign.id,
                "title": campaign.title,
                "status": "OVERDUE" if recipient.due_at and recipient.due_at.replace(tzinfo=None) < now else recipient.status,
                "due_at": _iso(recipient.due_at),
                "notified_at": _iso(recipient.notified_at),
                "recipient": {
                    "id": recipient.recipient_user_id,
                    "name": (user.full_name or user.email) if user else "Recipient unavailable",
                },
                "reminder_count": int(recipient.reminder_count or 0),
                "target_path": f"/maintenance/{tenant_slug}/document-control/distribution/{campaign.id}",
            })
    else:
        query = db.query(dm.DocumentControlledCopy, manual_models.Manual).join(
            manual_models.Manual,
            manual_models.Manual.id == dm.DocumentControlledCopy.manual_id,
        ).filter(
            dm.DocumentControlledCopy.tenant_id == tenant.amo_id,
            manual_models.Manual.tenant_id == tenant.id,
        )
        if view == "recalls":
            query = query.filter(dm.DocumentControlledCopy.status == "RECALLED")
        elif status:
            query = query.filter(dm.DocumentControlledCopy.status == status.upper())
        else:
            query = query.filter(dm.DocumentControlledCopy.status.notin_(["DESTROYED"]))
        if q and q.strip():
            needle = f"%{q.strip()}%"
            query = query.filter(
                (manual_models.Manual.code.ilike(needle))
                | (manual_models.Manual.title.ilike(needle))
                | (dm.DocumentControlledCopy.copy_number.ilike(needle))
                | (dm.DocumentControlledCopy.location_text.ilike(needle))
                | (dm.DocumentControlledCopy.holder_name.ilike(needle))
            )
        total = query.count()
        rows = query.order_by(
            dm.DocumentControlledCopy.due_back_at.asc().nullslast(),
            dm.DocumentControlledCopy.copy_number.asc(),
        ).offset(offset).limit(per_page).all()
        for row, manual in rows:
            due = row.due_back_at.replace(tzinfo=None) if row.due_back_at and row.due_back_at.tzinfo else row.due_back_at
            display_status = "OVERDUE" if row.status == "ISSUED" and due and due < now else row.status
            items.append({
                "id": row.id,
                "kind": "CONTROLLED_COPY",
                "document": _document(manual),
                "revision_id": row.revision_id,
                "copy_number": row.copy_number,
                "format": row.format,
                "status": display_status,
                "custody_status": row.status,
                "holder": row.holder_name or row.holder_user_id,
                "location": row.location_text,
                "due_at": _iso(row.due_back_at),
                "issued_at": _iso(row.issued_at),
                "target_path": f"/maintenance/{tenant_slug}/document-control/controlled-copies?copy={row.id}",
            })

    return {
        "view": view,
        "items": items,
        "pagination": _pagination(page, per_page, total, len(items)),
        "facets": _facets(db, tenant.amo_id, now),
        "generated_at": now.isoformat(),
    }
