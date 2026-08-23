from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from .workspace_service import require_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Portfolios"])

ChangePortfolioView = Literal[
    "my-changes",
    "requests",
    "draft",
    "in-review",
    "awaiting-quality",
    "awaiting-management",
    "authority",
    "temporary-revisions",
    "ready-for-release",
    "closed",
]

VIEW_STATES: dict[str, tuple[str, ...]] = {
    "draft": ("DRAFT", "CORRECTIONS_REQUIRED"),
    "in-review": ("TECHNICAL_REVIEW", "TECHNICAL_APPROVED", "QUALITY_REVIEW", "QUALITY_APPROVED"),
    "awaiting-quality": ("QUALITY_REVIEW",),
    "awaiting-management": ("ACCOUNTABLE_MANAGER_APPROVAL",),
    "ready-for-release": ("AUTHORITY_APPROVED", "SCHEDULED_FOR_EFFECTIVITY"),
    "closed": ("PUBLISHED", "ARCHIVED"),
}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _document(manual: manual_models.Manual) -> dict[str, str]:
    return {"id": manual.id, "code": manual.code, "title": manual.title}


def _pagination(page: int, per_page: int, total: int, returned: int) -> dict[str, int]:
    return {"page": page, "per_page": per_page, "total": total, "returned": returned}


def _search_filter(q: str | None, *columns):
    if not q or not q.strip():
        return None
    needle = f"%{q.strip()}%"
    return or_(*(column.ilike(needle) for column in columns))


def _portfolio_counts(db: Session, tenant_id: str, current_user_id: str) -> dict[str, int]:
    counts: dict[str, int] = {
        "my-changes": db.query(func.count(dm.DocumentChangeRequest.id)).filter(
            dm.DocumentChangeRequest.tenant_id == tenant_id,
            or_(
                dm.DocumentChangeRequest.owner_user_id == current_user_id,
                dm.DocumentChangeRequest.proposer_user_id == current_user_id,
            ),
            dm.DocumentChangeRequest.status.notin_(["CLOSED", "REJECTED", "CANCELLED"]),
        ).scalar() or 0,
        "requests": db.query(func.count(dm.DocumentChangeRequest.id)).filter(
            dm.DocumentChangeRequest.tenant_id == tenant_id,
            dm.DocumentChangeRequest.status.notin_(["CLOSED", "REJECTED", "CANCELLED"]),
        ).scalar() or 0,
        "authority": db.query(func.count(dm.DocumentAuthoritySubmission.id)).filter(
            dm.DocumentAuthoritySubmission.tenant_id == tenant_id,
            dm.DocumentAuthoritySubmission.status.notin_(["APPROVED", "ACCEPTED", "CLOSED", "REJECTED"]),
        ).scalar() or 0,
        "temporary-revisions": db.query(func.count(dm.DocumentTemporaryRevision.id)).filter(
            dm.DocumentTemporaryRevision.tenant_id == tenant_id,
            dm.DocumentTemporaryRevision.status.notin_(["WITHDRAWN", "INCORPORATED", "EXPIRED"]),
        ).scalar() or 0,
    }
    for view, states in VIEW_STATES.items():
        counts[view] = db.query(func.count(dm.DocumentWorkflowInstance.id)).filter(
            dm.DocumentWorkflowInstance.tenant_id == tenant_id,
            dm.DocumentWorkflowInstance.state.in_(states),
        ).scalar() or 0
    return counts


@router.get("/t/{tenant_slug}/changes-portfolio")
def get_changes_portfolio(
    tenant_slug: str,
    view: ChangePortfolioView = "my-changes",
    q: str | None = Query(default=None, max_length=255),
    status: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Return one bounded operational slice of the document-change lifecycle.

    This endpoint is intentionally separate from legacy register list routes so
    existing compatibility screens keep their response contracts while the new
    DMS portfolio remains server-paginated and bounded.
    """
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    offset = (page - 1) * per_page
    items: list[dict[str, Any]] = []

    if view in {"my-changes", "requests"}:
        query = db.query(dm.DocumentChangeRequest, manual_models.Manual).join(
            manual_models.Manual, manual_models.Manual.id == dm.DocumentChangeRequest.manual_id
        ).filter(
            dm.DocumentChangeRequest.tenant_id == tenant.amo_id,
            manual_models.Manual.tenant_id == tenant.id,
        )
        if view == "my-changes":
            query = query.filter(
                or_(
                    dm.DocumentChangeRequest.owner_user_id == current_user.id,
                    dm.DocumentChangeRequest.proposer_user_id == current_user.id,
                )
            )
            if status:
                query = query.filter(dm.DocumentChangeRequest.status == status.upper())
            else:
                query = query.filter(dm.DocumentChangeRequest.status.notin_(["CLOSED", "REJECTED", "CANCELLED"]))
        elif status:
            query = query.filter(dm.DocumentChangeRequest.status == status.upper())
        search = _search_filter(q, dm.DocumentChangeRequest.title, dm.DocumentChangeRequest.description, manual_models.Manual.code, manual_models.Manual.title)
        if search is not None:
            query = query.filter(search)
        total = query.count()
        rows = query.order_by(dm.DocumentChangeRequest.updated_at.desc()).offset(offset).limit(per_page).all()
        for row, manual in rows:
            items.append({
                "id": row.id,
                "kind": "CHANGE_REQUEST",
                "document": _document(manual),
                "revision_id": row.revision_id,
                "title": row.title,
                "subtitle": row.description,
                "status": row.status,
                "priority": row.priority,
                "due_at": _iso(row.due_at),
                "updated_at": _iso(row.updated_at),
                "source": row.source_module,
                "training_impact_required": bool(row.training_impact_required),
                "qms_blocking": bool(row.qms_blocking),
                "target_path": f"/maintenance/{tenant_slug}/document-control/library/{manual.id}?tab=changes&change={row.id}",
            })
    elif view == "authority":
        query = db.query(dm.DocumentAuthoritySubmission, manual_models.Manual).join(
            manual_models.Manual, manual_models.Manual.id == dm.DocumentAuthoritySubmission.manual_id
        ).filter(
            dm.DocumentAuthoritySubmission.tenant_id == tenant.amo_id,
            manual_models.Manual.tenant_id == tenant.id,
        )
        if status:
            query = query.filter(dm.DocumentAuthoritySubmission.status == status.upper())
        search = _search_filter(q, dm.DocumentAuthoritySubmission.authority_name, dm.DocumentAuthoritySubmission.submission_reference, manual_models.Manual.code, manual_models.Manual.title)
        if search is not None:
            query = query.filter(search)
        total = query.count()
        rows = query.order_by(dm.DocumentAuthoritySubmission.updated_at.desc()).offset(offset).limit(per_page).all()
        for row, manual in rows:
            items.append({
                "id": row.id,
                "kind": "AUTHORITY_SUBMISSION",
                "document": _document(manual),
                "revision_id": row.revision_id,
                "title": row.authority_name,
                "subtitle": row.submission_reference,
                "status": row.status,
                "priority": "DUE" if row.response_due_at else "NORMAL",
                "due_at": _iso(row.response_due_at),
                "updated_at": _iso(row.updated_at),
                "source": "AUTHORITY",
                "target_path": f"/maintenance/{tenant_slug}/document-control/library/{manual.id}?tab=workflow",
            })
    elif view == "temporary-revisions":
        query = db.query(dm.DocumentTemporaryRevision, manual_models.Manual).join(
            manual_models.Manual, manual_models.Manual.id == dm.DocumentTemporaryRevision.manual_id
        ).filter(
            dm.DocumentTemporaryRevision.tenant_id == tenant.amo_id,
            manual_models.Manual.tenant_id == tenant.id,
        )
        if status:
            query = query.filter(dm.DocumentTemporaryRevision.status == status.upper())
        search = _search_filter(q, dm.DocumentTemporaryRevision.tr_number, dm.DocumentTemporaryRevision.title, dm.DocumentTemporaryRevision.reason, manual_models.Manual.code, manual_models.Manual.title)
        if search is not None:
            query = query.filter(search)
        total = query.count()
        rows = query.order_by(dm.DocumentTemporaryRevision.expiry_date.asc(), dm.DocumentTemporaryRevision.updated_at.desc()).offset(offset).limit(per_page).all()
        for row, manual in rows:
            items.append({
                "id": row.id,
                "kind": "TEMPORARY_REVISION",
                "document": _document(manual),
                "revision_id": row.revision_id or row.base_revision_id,
                "title": f"{row.tr_number} — {row.title}",
                "subtitle": row.reason,
                "status": row.status,
                "priority": row.approval_status,
                "due_at": _iso(row.expiry_date),
                "updated_at": _iso(row.updated_at),
                "source": "TEMPORARY_REVISION",
                "target_path": f"/maintenance/{tenant_slug}/document-control/library/{manual.id}?tab=changes",
            })
    else:
        states = VIEW_STATES[view]
        query = db.query(dm.DocumentWorkflowInstance, manual_models.Manual, manual_models.ManualRevision).join(
            manual_models.Manual, manual_models.Manual.id == dm.DocumentWorkflowInstance.manual_id
        ).join(
            manual_models.ManualRevision, manual_models.ManualRevision.id == dm.DocumentWorkflowInstance.revision_id
        ).filter(
            dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id,
            dm.DocumentWorkflowInstance.state.in_(states),
            manual_models.Manual.tenant_id == tenant.id,
        )
        if status:
            query = query.filter(dm.DocumentWorkflowInstance.state == status.upper())
        search = _search_filter(q, manual_models.Manual.code, manual_models.Manual.title, manual_models.ManualRevision.rev_number, manual_models.ManualRevision.issue_number)
        if search is not None:
            query = query.filter(search)
        total = query.count()
        rows = query.order_by(dm.DocumentWorkflowInstance.updated_at.desc()).offset(offset).limit(per_page).all()
        for row, manual, revision in rows:
            items.append({
                "id": row.id,
                "kind": "WORKFLOW",
                "document": _document(manual),
                "revision_id": row.revision_id,
                "title": f"Issue {revision.issue_number or '—'} · Rev {revision.rev_number or '—'}",
                "subtitle": row.state.replace("_", " ").title(),
                "status": row.state,
                "priority": "BLOCKED" if row.state == "CORRECTIONS_REQUIRED" else "ACTION",
                "due_at": _iso(row.effective_at),
                "updated_at": _iso(row.updated_at),
                "source": "REVISION_WORKFLOW",
                "requires_authority": bool(row.requires_authority),
                "training_impact_required": bool(row.training_impact_required),
                "target_path": f"/maintenance/{tenant_slug}/document-control/library/{manual.id}?tab=workflow",
            })

    return {
        "view": view,
        "items": items,
        "pagination": _pagination(page, per_page, total, len(items)),
        "facets": _portfolio_counts(db, tenant.amo_id, str(current_user.id)),
        "generated_at": datetime.utcnow().isoformat(),
    }
