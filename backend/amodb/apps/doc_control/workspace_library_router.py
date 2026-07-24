from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from .workspace_service import (
    can_read_manual,
    readable_revision,
    resolve_tenant,
    serialize_manual,
    serialize_workflow,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Library"])
OPEN_CHANGE_STATUSES = {"OPEN", "ASSESSING", "ACCEPTED", "IMPLEMENTING"}


@router.get("/t/{tenant_slug}/documents", include_in_schema=False)
def list_visible_documents(
    tenant_slug: str,
    q: str | None = Query(default=None, max_length=255),
    document_class: str | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Return a correctly paginated, access-filtered Document Control library.

    The first workspace implementation paginated manuals before applying document
    class and restricted-document access rules. That could produce short pages,
    inaccurate totals, and skip permitted documents on later pages. This route is
    intentionally registered before the compatibility endpoint and keeps the same
    response contract while filtering before pagination.
    """
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = (
        db.query(manual_models.Manual, dm.DocumentControlProfile)
        .outerjoin(
            dm.DocumentControlProfile,
            (dm.DocumentControlProfile.manual_id == manual_models.Manual.id)
            & (dm.DocumentControlProfile.tenant_id == tenant.amo_id),
        )
        .filter(manual_models.Manual.tenant_id == tenant.id)
    )
    if q and q.strip():
        needle = f"%{q.strip()}%"
        query = query.filter(
            or_(
                manual_models.Manual.code.ilike(needle),
                manual_models.Manual.title.ilike(needle),
                manual_models.Manual.manual_type.ilike(needle),
            )
        )
    if status:
        query = query.filter(manual_models.Manual.status == status)
    if document_class:
        query = query.filter(
            func.coalesce(dm.DocumentControlProfile.document_class, "INTERNAL")
            == document_class.strip().upper()
        )

    candidates = query.order_by(manual_models.Manual.code.asc()).all()
    visible = [
        (manual, profile)
        for manual, profile in candidates
        if can_read_manual(current_user, profile)
    ]
    total = len(visible)
    start = (page - 1) * per_page
    selected = visible[start : start + per_page]
    manuals = [manual for manual, _profile in selected]
    profiles = {manual.id: profile for manual, profile in selected}
    manual_ids = [manual.id for manual in manuals]

    revisions = (
        db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.manual_id.in_(manual_ids or ["-"]))
        .order_by(
            manual_models.ManualRevision.created_at.desc(),
            manual_models.ManualRevision.id.desc(),
        )
        .all()
    )
    latest_by_manual: dict[str, manual_models.ManualRevision] = {}
    for revision in revisions:
        latest_by_manual.setdefault(revision.manual_id, revision)

    workflows = {
        row.revision_id: row
        for row in db.query(dm.DocumentWorkflowInstance)
        .filter(
            dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id,
            dm.DocumentWorkflowInstance.manual_id.in_(manual_ids or ["-"]),
        )
        .all()
    }
    open_change_counts = dict(
        db.query(
            dm.DocumentChangeRequest.manual_id,
            func.count(dm.DocumentChangeRequest.id),
        )
        .filter(
            dm.DocumentChangeRequest.tenant_id == tenant.amo_id,
            dm.DocumentChangeRequest.manual_id.in_(manual_ids or ["-"]),
            dm.DocumentChangeRequest.status.in_(OPEN_CHANGE_STATUSES),
        )
        .group_by(dm.DocumentChangeRequest.manual_id)
        .all()
    )
    pending_ack_counts = dict(
        db.query(
            dm.DocumentDistributionCampaign.manual_id,
            func.count(dm.DocumentDistributionRecipient.id),
        )
        .join(
            dm.DocumentDistributionRecipient,
            dm.DocumentDistributionRecipient.campaign_id
            == dm.DocumentDistributionCampaign.id,
        )
        .filter(
            dm.DocumentDistributionCampaign.tenant_id == tenant.amo_id,
            dm.DocumentDistributionCampaign.manual_id.in_(manual_ids or ["-"]),
            dm.DocumentDistributionRecipient.status == "PENDING",
        )
        .group_by(dm.DocumentDistributionCampaign.manual_id)
        .all()
    )

    items: list[dict] = []
    for manual in manuals:
        profile = profiles.get(manual.id)
        target, target_kind = readable_revision(db, manual, current_user)
        latest = latest_by_manual.get(manual.id)
        payload = serialize_manual(manual, profile, target, target_kind, latest)
        workflow = workflows.get(latest.id) if latest else None
        payload["workflow"] = serialize_workflow(workflow) if workflow else None
        payload["open_change_requests"] = int(open_change_counts.get(manual.id, 0))
        payload["pending_acknowledgements"] = int(
            pending_ack_counts.get(manual.id, 0)
        )
        items.append(payload)

    return {
        "items": items,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "returned": len(items),
        },
    }
