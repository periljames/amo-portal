from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_router import (
    acknowledge_distribution_campaign as _acknowledge_distribution_campaign,
    create_distribution_campaign as _create_distribution_campaign,
    issue_distribution_campaign as _issue_distribution_campaign,
)
from .workspace_service import (
    active_tenant_users,
    audit,
    get_manual,
    get_profile,
    get_revision,
    require_control_user,
    resolve_tenant,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Distribution"])


@router.post("/t/{tenant_slug}/distribution-campaigns", include_in_schema=False)
def create_guarded_distribution_campaign(
    tenant_slug: str,
    payload: schemas.DistributionCampaignCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    get_revision(db, manual, payload.revision_id)
    profile = get_profile(db, tenant, manual.id)

    if payload.temporary_revision_id:
        tr = (
            db.query(dm.DocumentTemporaryRevision)
            .filter(
                dm.DocumentTemporaryRevision.tenant_id == tenant.amo_id,
                dm.DocumentTemporaryRevision.id == payload.temporary_revision_id,
                dm.DocumentTemporaryRevision.manual_id == manual.id,
            )
            .first()
        )
        if not tr:
            raise HTTPException(
                status_code=400,
                detail="Temporary revision does not match the document and tenant",
            )
        expected_revision_id = tr.revision_id or tr.base_revision_id
        if payload.revision_id != expected_revision_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "TR_DISTRIBUTION_REVISION_MISMATCH",
                    "message": "The campaign revision must be the temporary revision source or its controlled base revision.",
                },
            )

    guarded_payload = payload.model_copy(
        update={
            "acknowledgement_required": bool(
                payload.acknowledgement_required
                or (profile and profile.acknowledgement_required)
            )
        }
    )
    return _create_distribution_campaign(
        tenant_slug=tenant_slug,
        payload=guarded_payload,
        request=request,
        db=db,
        current_user=current_user,
    )


@router.post(
    "/t/{tenant_slug}/distribution-campaigns/{campaign_id}/issue",
    include_in_schema=False,
)
def issue_guarded_distribution_campaign(
    tenant_slug: str,
    campaign_id: str,
    payload: schemas.DistributionIssueRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    campaign = (
        db.query(dm.DocumentDistributionCampaign)
        .filter(
            dm.DocumentDistributionCampaign.tenant_id == tenant.amo_id,
            dm.DocumentDistributionCampaign.id == campaign_id,
        )
        .first()
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="Distribution campaign not found")

    profile = get_profile(db, tenant, campaign.manual_id)
    if profile and profile.acknowledgement_required and not campaign.acknowledgement_required:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ACKNOWLEDGEMENT_REQUIRED_BY_PROFILE",
                "message": "This controlled document requires recipient acknowledgement.",
            },
        )

    existing_rows = (
        db.query(dm.DocumentDistributionRecipient)
        .filter(dm.DocumentDistributionRecipient.campaign_id == campaign.id)
        .all()
    )
    if any(not row.recipient_user_id for row in existing_rows):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DISTRIBUTION_RECIPIENT_NO_LONGER_ACTIVE",
                "message": "A campaign recipient no longer resolves to an active tenant user. Remove or replace the recipient before issue.",
            },
        )
    existing_ids = [str(row.recipient_user_id) for row in existing_rows]
    active_tenant_users(
        db,
        tenant,
        list(dict.fromkeys(existing_ids + list(payload.recipient_user_ids))),
    )

    if campaign.temporary_revision_id:
        tr = (
            db.query(dm.DocumentTemporaryRevision)
            .filter(
                dm.DocumentTemporaryRevision.tenant_id == tenant.amo_id,
                dm.DocumentTemporaryRevision.id == campaign.temporary_revision_id,
                dm.DocumentTemporaryRevision.manual_id == campaign.manual_id,
            )
            .first()
        )
        if not tr:
            raise HTTPException(
                status_code=409,
                detail="The temporary revision linked to this campaign is unavailable",
            )
        if campaign.revision_id != (tr.revision_id or tr.base_revision_id):
            raise HTTPException(
                status_code=409,
                detail="The campaign no longer matches its temporary revision source",
            )

    result = _issue_distribution_campaign(
        tenant_slug=tenant_slug,
        campaign_id=campaign_id,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )

    if not campaign.acknowledgement_required:
        campaign = (
            db.query(dm.DocumentDistributionCampaign)
            .filter(
                dm.DocumentDistributionCampaign.tenant_id == tenant.amo_id,
                dm.DocumentDistributionCampaign.id == campaign_id,
            )
            .first()
        )
        if campaign and campaign.status == "ISSUED":
            campaign.status = "COMPLETED"
            audit(
                db,
                tenant,
                request,
                "document.distribution.completed",
                "document_distribution_campaign",
                campaign.id,
                {"reason": "Acknowledgement not required"},
            )
            db.commit()
            result["status"] = "COMPLETED"
    return result


@router.post(
    "/t/{tenant_slug}/distribution-campaigns/{campaign_id}/acknowledge",
    include_in_schema=False,
)
def acknowledge_issued_distribution_campaign(
    tenant_slug: str,
    campaign_id: str,
    payload: schemas.DistributionAcknowledgeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    campaign = (
        db.query(dm.DocumentDistributionCampaign)
        .filter(
            dm.DocumentDistributionCampaign.tenant_id == tenant.amo_id,
            dm.DocumentDistributionCampaign.id == campaign_id,
        )
        .first()
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="Distribution campaign not found")
    if campaign.status not in {"ISSUED", "COMPLETED"}:
        raise HTTPException(
            status_code=409,
            detail="A distribution campaign must be issued before it can be acknowledged",
        )
    if not campaign.acknowledgement_required:
        raise HTTPException(
            status_code=409,
            detail="This campaign records delivery only and does not require acknowledgement",
        )

    recipient = (
        db.query(dm.DocumentDistributionRecipient)
        .filter(
            dm.DocumentDistributionRecipient.tenant_id == tenant.amo_id,
            dm.DocumentDistributionRecipient.campaign_id == campaign.id,
            dm.DocumentDistributionRecipient.recipient_user_id == current_user.id,
        )
        .first()
    )
    if not recipient:
        raise HTTPException(
            status_code=403,
            detail="The current user is not a recipient of this campaign",
        )
    if not recipient.notified_at:
        raise HTTPException(
            status_code=409,
            detail="This recipient has not been issued the controlled revision",
        )
    if recipient.status not in {"PENDING", "ACKNOWLEDGED"}:
        raise HTTPException(
            status_code=409,
            detail=f"Recipient status {recipient.status} cannot be acknowledged",
        )

    return _acknowledge_distribution_campaign(
        tenant_slug=tenant_slug,
        campaign_id=campaign_id,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )
