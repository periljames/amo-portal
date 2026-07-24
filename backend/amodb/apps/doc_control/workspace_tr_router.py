from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_router import transition_temporary_revision as _transition_temporary_revision
from .workspace_service import require_approver, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Temporary Revisions"])

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"IN_REVIEW", "WITHDRAWN"},
    "IN_REVIEW": {"DRAFT", "APPROVED", "WITHDRAWN"},
    "APPROVED": {"IN_FORCE", "WITHDRAWN"},
    "IN_FORCE": {"EXPIRED", "WITHDRAWN", "INCORPORATED"},
    "EXPIRED": {"INCORPORATED", "WITHDRAWN"},
    "WITHDRAWN": set(),
    "INCORPORATED": set(),
}


def _validate_campaign(
    db: Session,
    *,
    tenant_id: str,
    tr: dm.DocumentTemporaryRevision,
    campaign_id: str,
) -> None:
    campaign = (
        db.query(dm.DocumentDistributionCampaign)
        .filter(
            dm.DocumentDistributionCampaign.id == campaign_id,
            dm.DocumentDistributionCampaign.tenant_id == tenant_id,
            dm.DocumentDistributionCampaign.manual_id == tr.manual_id,
            dm.DocumentDistributionCampaign.temporary_revision_id == tr.id,
            dm.DocumentDistributionCampaign.status.in_(["ISSUED", "COMPLETED"]),
        )
        .first()
    )
    if not campaign:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TR_DISTRIBUTION_INVALID",
                "message": "The campaign must be issued for this temporary revision, document, and tenant.",
            },
        )
    expected_revision = tr.revision_id or tr.base_revision_id
    if campaign.revision_id != expected_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TR_DISTRIBUTION_REVISION_MISMATCH",
                "message": "The campaign does not distribute the temporary revision source in force.",
            },
        )


def _validate_incorporating_revision(
    db: Session,
    *,
    tr: dm.DocumentTemporaryRevision,
    revision_id: str,
) -> None:
    revision = (
        db.query(manual_models.ManualRevision)
        .filter(
            manual_models.ManualRevision.id == revision_id,
            manual_models.ManualRevision.manual_id == tr.manual_id,
        )
        .first()
    )
    if not revision:
        raise HTTPException(status_code=404, detail="The incorporating revision does not exist")
    status = str(getattr(revision.status_enum, "value", revision.status_enum))
    if status not in {"PUBLISHED", "SUPERSEDED"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TR_INCORPORATING_REVISION_NOT_EFFECTIVE",
                "message": "The incorporating permanent revision must be published before incorporation is closed.",
            },
        )
    if revision.id in {tr.base_revision_id, tr.revision_id}:
        raise HTTPException(
            status_code=409,
            detail="The temporary or base revision cannot be used as its own incorporating revision",
        )


@router.post(
    "/t/{tenant_slug}/temporary-revisions/{tr_id}/transition",
    include_in_schema=False,
)
def transition_temporary_revision_with_guards(
    tenant_slug: str,
    tr_id: str,
    payload: schemas.TemporaryRevisionTransition,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_approver(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = (
        db.query(dm.DocumentTemporaryRevision)
        .filter(
            dm.DocumentTemporaryRevision.tenant_id == tenant.amo_id,
            dm.DocumentTemporaryRevision.id == tr_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Temporary revision not found")

    allowed = _ALLOWED_TRANSITIONS.get(row.status, set())
    if payload.status != row.status and payload.status not in allowed:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TR_TRANSITION_INVALID",
                "message": f"Temporary revision cannot move from {row.status} to {payload.status}.",
                "allowed_statuses": sorted(allowed),
            },
        )

    if payload.status == "APPROVED" and payload.approval_status not in {None, "APPROVED"}:
        raise HTTPException(status_code=409, detail="Approved temporary revisions require approved approval status")

    if payload.status == "IN_FORCE":
        if row.effective_date > date.today():
            raise HTTPException(status_code=409, detail="The temporary revision effective date has not been reached")
        if row.expiry_date < date.today():
            raise HTTPException(status_code=409, detail="An expired temporary revision cannot be placed in force")
        campaign_id = payload.distribution_campaign_id or row.distribution_campaign_id
        if not campaign_id:
            raise HTTPException(status_code=409, detail="An issued distribution campaign is required")
        _validate_campaign(db, tenant_id=tenant.amo_id, tr=row, campaign_id=campaign_id)

    if payload.status == "INCORPORATED":
        revision_id = payload.incorporated_revision_id or row.incorporated_revision_id
        if not revision_id:
            raise HTTPException(status_code=409, detail="The incorporating permanent revision is required")
        _validate_incorporating_revision(db, tr=row, revision_id=revision_id)

    return _transition_temporary_revision(
        tenant_slug=tenant_slug,
        tr_id=tr_id,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )
