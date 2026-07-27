from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from .workspace_router import dashboard as _get_full_dashboard
from .workspace_service import can_read_manual, is_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Dashboard"])


def _reader_dashboard(
    db: Session,
    *,
    tenant_slug: str,
    current_user: account_models.User,
) -> dict:
    tenant = resolve_tenant(db, tenant_slug, current_user)
    candidates = (
        db.query(manual_models.Manual, dm.DocumentControlProfile)
        .outerjoin(
            dm.DocumentControlProfile,
            (dm.DocumentControlProfile.manual_id == manual_models.Manual.id)
            & (dm.DocumentControlProfile.tenant_id == tenant.amo_id),
        )
        .filter(manual_models.Manual.tenant_id == tenant.id)
        .all()
    )
    visible = [
        manual
        for manual, profile in candidates
        if can_read_manual(current_user, profile)
    ]
    effective = [
        manual
        for manual in visible
        if manual.current_published_rev_id is not None
    ]
    metrics = {
        "document_records": len(visible),
        "revision_records": len(effective),
        "draft_revisions": 0,
        "effective_publications": len(effective),
        "open_change_requests": 0,
        "active_workflows": 0,
        "authority_pending": 0,
        "temporary_revisions_in_force": 0,
        "temporary_revisions_expiring_30_days": 0,
        "pending_acknowledgements": 0,
        "overdue_acknowledgements": 0,
        "reviews_due_60_days": 0,
        "external_currency_checks_due": 0,
        "issued_controlled_copies": 0,
    }
    return {
        "default_workspace": "LIBRARY",
        "capabilities": {"read": True, "control": False, "approve": False},
        "metrics": metrics,
        "recent_activity": [],
    }


@router.get("/t/{tenant_slug}/dashboard", include_in_schema=False)
def get_role_appropriate_dashboard(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Return operational metrics only to Document Control personnel.

    Reader metrics are calculated directly from documents visible to that user.
    Restricted-document counts and controller activity are never loaded into a
    reader response and cannot be inferred from tenant-wide totals.
    """
    if not is_control_user(current_user):
        return _reader_dashboard(
            db,
            tenant_slug=tenant_slug,
            current_user=current_user,
        )
    return _get_full_dashboard(
        tenant_slug=tenant_slug,
        db=db,
        current_user=current_user,
    )
