from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from .workspace_capabilities import document_control_capabilities, reader_capabilities
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
        "control_profiles_missing": 0,
        "document_owners_unassigned": 0,
        "review_dates_missing": 0,
        "documents_without_effective_issue": 0,
        "critical_acknowledgement_gaps": 0,
    }
    return {
        "default_workspace": "LIBRARY",
        "capabilities": reader_capabilities(),
        "metrics": metrics,
        "recent_activity": [],
    }


def _controller_control_gaps(
    db: Session,
    *,
    tenant: account_models.AMO,
) -> dict[str, int]:
    """Return evidence-control gaps without exposing them to ordinary readers."""
    profiles_missing = (
        db.query(manual_models.Manual)
        .outerjoin(
            dm.DocumentControlProfile,
            (dm.DocumentControlProfile.manual_id == manual_models.Manual.id)
            & (dm.DocumentControlProfile.tenant_id == tenant.amo_id),
        )
        .filter(
            manual_models.Manual.tenant_id == tenant.id,
            dm.DocumentControlProfile.id.is_(None),
        )
        .count()
    )
    owners_unassigned = (
        db.query(dm.DocumentControlProfile)
        .filter(
            dm.DocumentControlProfile.tenant_id == tenant.amo_id,
            dm.DocumentControlProfile.owner_user_id.is_(None),
        )
        .count()
    )
    review_dates_missing = (
        db.query(dm.DocumentControlProfile)
        .filter(
            dm.DocumentControlProfile.tenant_id == tenant.amo_id,
            dm.DocumentControlProfile.next_review_due.is_(None),
        )
        .count()
    )
    documents_without_effective_issue = (
        db.query(manual_models.Manual)
        .filter(
            manual_models.Manual.tenant_id == tenant.id,
            manual_models.Manual.current_published_rev_id.is_(None),
        )
        .count()
    )
    critical_acknowledgement_gaps = (
        db.query(dm.DocumentControlProfile)
        .filter(
            dm.DocumentControlProfile.tenant_id == tenant.amo_id,
            dm.DocumentControlProfile.criticality == "CRITICAL",
            dm.DocumentControlProfile.acknowledgement_required.is_(False),
        )
        .count()
    )
    return {
        "control_profiles_missing": profiles_missing,
        "document_owners_unassigned": owners_unassigned,
        "review_dates_missing": review_dates_missing,
        "documents_without_effective_issue": documents_without_effective_issue,
        "critical_acknowledgement_gaps": critical_acknowledgement_gaps,
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
    tenant = resolve_tenant(db, tenant_slug, current_user)
    dashboard = _get_full_dashboard(
        tenant_slug=tenant_slug,
        db=db,
        current_user=current_user,
    )
    dashboard["capabilities"] = document_control_capabilities(current_user)
    dashboard["metrics"].update(_controller_control_gaps(db, tenant=tenant))
    return dashboard
