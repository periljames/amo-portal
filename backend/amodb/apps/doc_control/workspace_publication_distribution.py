from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.apps.realtime import messaging as realtime_messaging
from amodb.apps.realtime import models as realtime_models
from amodb.apps.realtime import schemas as realtime_schemas

from . import domain_models as dm
from .workspace_service import (
    active_tenant_users,
    audit,
    can_read_manual,
    get_profile,
    utcnow,
)


AUTO_AUDIENCE = "ALL_ELIGIBLE_USERS"
SELECTED_AUDIENCE = "SELECTED_USERS"
DEFAULT_ACK_DUE_DAYS = 10


def publication_distribution_policy(profile: dm.DocumentControlProfile | None) -> dict[str, object]:
    metadata = dict(getattr(profile, "metadata_json", None) or {})
    configured = metadata.get("distribution_policy")
    policy = dict(configured) if isinstance(configured, dict) else {}
    auto_issue = policy.get("auto_issue_on_publish", True)
    audience_mode = str(policy.get("audience_mode") or AUTO_AUDIENCE).upper()
    if audience_mode not in {AUTO_AUDIENCE, SELECTED_AUDIENCE}:
        audience_mode = AUTO_AUDIENCE
    try:
        due_days = int(policy.get("acknowledgement_due_days", DEFAULT_ACK_DUE_DAYS))
    except (TypeError, ValueError):
        due_days = DEFAULT_ACK_DUE_DAYS
    return {
        "auto_issue_on_publish": bool(auto_issue),
        "audience_mode": audience_mode,
        "acknowledgement_due_days": max(1, min(365, due_days)),
    }


def eligible_distribution_users(
    db: Session,
    *,
    tenant,
    profile: dm.DocumentControlProfile | None,
) -> list[account_models.User]:
    rows = (
        db.query(account_models.User)
        .filter(
            account_models.User.amo_id == tenant.amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .order_by(account_models.User.full_name.asc(), account_models.User.email.asc())
        .all()
    )
    return [row for row in rows if can_read_manual(row, profile)]


def resolve_distribution_users(
    db: Session,
    *,
    tenant,
    profile: dm.DocumentControlProfile | None,
    audience_mode: str,
    requested_user_ids: Iterable[str],
) -> list[account_models.User]:
    mode = str(audience_mode or SELECTED_AUDIENCE).upper()
    if mode == AUTO_AUDIENCE:
        return eligible_distribution_users(db, tenant=tenant, profile=profile)
    return active_tenant_users(db, tenant, list(dict.fromkeys(str(value) for value in requested_user_ids)))


def _notification_action_url(tenant_slug: str, manual_id: str, revision_id: str) -> str:
    return f"/maintenance/{tenant_slug.upper()}/publications/{manual_id}/rev/{revision_id}/read"


def notify_distribution_recipients(
    db: Session,
    *,
    tenant_slug: str,
    tenant_id: str,
    campaign: dm.DocumentDistributionCampaign,
    manual: manual_models.Manual,
    revision: manual_models.ManualRevision,
) -> int:
    recipients = (
        db.query(dm.DocumentDistributionRecipient)
        .filter(
            dm.DocumentDistributionRecipient.tenant_id == tenant_id,
            dm.DocumentDistributionRecipient.campaign_id == campaign.id,
            dm.DocumentDistributionRecipient.recipient_user_id.isnot(None),
        )
        .all()
    )
    notified = 0
    action_url = _notification_action_url(tenant_slug, manual.id, revision.id)
    title = f"Controlled publication issued: {manual.code}"
    revision_label = f"Issue {revision.issue_number or '—'} · Rev {revision.rev_number}"
    body = (
        f"{manual.title} ({revision_label}) is available. Read and acknowledge by "
        f"{campaign.due_at.isoformat() if campaign.due_at else 'the assigned due date'}."
        if campaign.acknowledgement_required
        else f"{manual.title} ({revision_label}) is now available for controlled use."
    )
    for recipient in recipients:
        user_id = str(recipient.recipient_user_id)
        dedupe_key = f"doc-control-distribution:{campaign.id}:{user_id}"
        existing = (
            db.query(realtime_models.PortalNotification)
            .filter(
                realtime_models.PortalNotification.amo_id == tenant_id,
                realtime_models.PortalNotification.user_id == user_id,
                realtime_models.PortalNotification.dedupe_key == dedupe_key,
            )
            .first()
        )
        if existing:
            continue
        row = realtime_models.PortalNotification(
            amo_id=tenant_id,
            user_id=user_id,
            kind="DOCUMENT_CONTROL",
            title=title[:255],
            body=body[:1000],
            entity_type="document_distribution_campaign",
            entity_id=campaign.id,
            action_url=action_url,
            dedupe_key=dedupe_key,
            metadata_json={
                "manual_id": manual.id,
                "revision_id": revision.id,
                "campaign_id": campaign.id,
                "acknowledgement_required": campaign.acknowledgement_required,
                "due_at": campaign.due_at.isoformat() if campaign.due_at else None,
            },
        )
        db.add(row)
        db.flush()
        realtime_messaging._queue_user_event(
            db,
            amo_id=tenant_id,
            user_id=user_id,
            kind=realtime_schemas.RealtimeKind.NOTIFICATION_CREATED,
            payload=realtime_messaging.notification_payload(row),
        )
        notified += 1
    return notified


def ensure_automatic_publication_distribution(
    db: Session,
    *,
    tenant_slug: str,
    tenant,
    workflow: dm.DocumentWorkflowInstance,
    manual: manual_models.Manual,
    revision: manual_models.ManualRevision,
    current_user: account_models.User,
    request: Request,
) -> dm.DocumentDistributionCampaign | None:
    profile = get_profile(db, tenant, manual.id)
    policy = publication_distribution_policy(profile)
    existing = (
        db.query(dm.DocumentDistributionCampaign)
        .filter(
            dm.DocumentDistributionCampaign.tenant_id == tenant.amo_id,
            dm.DocumentDistributionCampaign.revision_id == revision.id,
            dm.DocumentDistributionCampaign.status.in_(["ISSUED", "COMPLETED"]),
        )
        .order_by(dm.DocumentDistributionCampaign.issued_at.desc())
        .first()
    )
    if existing:
        workflow.distribution_readiness_status = "READY"
        notify_distribution_recipients(
            db,
            tenant_slug=tenant_slug,
            tenant_id=tenant.amo_id,
            campaign=existing,
            manual=manual,
            revision=revision,
        )
        db.flush()
        return existing

    if not bool(policy["auto_issue_on_publish"]):
        return None

    users = eligible_distribution_users(db, tenant=tenant, profile=profile)
    if not users:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Publication is blocked",
                "blockers": [
                    {
                        "code": "DISTRIBUTION_HAS_NO_ELIGIBLE_RECIPIENTS",
                        "message": "No active tenant user is eligible to receive this controlled publication.",
                    }
                ],
            },
        )

    issued_at = utcnow()
    due_at = issued_at + timedelta(days=int(policy["acknowledgement_due_days"]))
    acknowledgement_required = bool(profile.acknowledgement_required) if profile else True
    campaign = dm.DocumentDistributionCampaign(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=revision.id,
        title=f"Automatic publication distribution · {manual.code} · Rev {revision.rev_number}",
        audience_json={
            "mode": AUTO_AUDIENCE,
            "resolved_count": len(users),
            "trigger": "PUBLISH",
        },
        acknowledgement_required=acknowledgement_required,
        due_at=due_at,
        status="ISSUED" if acknowledgement_required else "COMPLETED",
        issued_at=issued_at,
        issued_by_user_id=current_user.id,
        metadata_json={"automatic": True, "trigger": "PUBLISH"},
    )
    db.add(campaign)
    db.flush()

    for user in users:
        status = "PENDING" if acknowledgement_required else "DELIVERED"
        db.add(
            dm.DocumentDistributionRecipient(
                tenant_id=tenant.amo_id,
                campaign_id=campaign.id,
                recipient_user_id=user.id,
                status=status,
                due_at=due_at,
                notified_at=issued_at,
            )
        )
        if acknowledgement_required:
            existing_ack = (
                db.query(manual_models.Acknowledgement)
                .filter(
                    manual_models.Acknowledgement.revision_id == revision.id,
                    manual_models.Acknowledgement.holder_user_id == user.id,
                    manual_models.Acknowledgement.status_enum == "PENDING",
                )
                .first()
            )
            if not existing_ack:
                db.add(
                    manual_models.Acknowledgement(
                        revision_id=revision.id,
                        holder_user_id=user.id,
                        due_at=due_at,
                        status_enum="PENDING",
                    )
                )

    workflow.distribution_readiness_status = "READY"
    db.flush()
    notified = notify_distribution_recipients(
        db,
        tenant_slug=tenant_slug,
        tenant_id=tenant.amo_id,
        campaign=campaign,
        manual=manual,
        revision=revision,
    )
    audit(
        db,
        tenant,
        request,
        "document.distribution.auto_issued",
        "document_distribution_campaign",
        campaign.id,
        {
            "manual_id": manual.id,
            "revision_id": revision.id,
            "recipient_count": len(users),
            "notification_count": notified,
            "acknowledgement_required": acknowledgement_required,
            "due_at": due_at.isoformat(),
        },
    )
    db.flush()
    return campaign
