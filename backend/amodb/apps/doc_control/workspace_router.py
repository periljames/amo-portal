from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.events.broker import EventEnvelope, publish_event
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_service import (
    active_tenant_users,
    audit,
    can_read_manual,
    get_manual,
    get_profile,
    get_revision,
    get_workflow,
    is_control_user,
    latest_revision,
    next_workflow_state,
    profile_defaults,
    publish_revision,
    readable_revision,
    require_approver,
    require_control_user,
    require_manual_access,
    resolve_tenant,
    role_value,
    serialize_manual,
    serialize_profile,
    serialize_revision,
    serialize_workflow,
    status_value,
    sync_revision_status,
    utcnow,
    workflow_blockers,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Workspace"])


OPEN_CHANGE_STATUSES = {"OPEN", "ASSESSING", "ACCEPTED", "IMPLEMENTING"}
OPEN_WORKFLOW_STATES = {
    "DRAFT",
    "TECHNICAL_REVIEW",
    "CORRECTIONS_REQUIRED",
    "TECHNICAL_APPROVED",
    "QUALITY_REVIEW",
    "QUALITY_APPROVED",
    "ACCOUNTABLE_MANAGER_APPROVAL",
    "AUTHORITY_SUBMITTED",
    "AUTHORITY_APPROVED",
    "SCHEDULED_FOR_EFFECTIVITY",
}


def _event(
    *,
    event_type: str,
    entity_type: str,
    entity_id: str,
    action: str,
    user: account_models.User,
    tenant_id: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    publish_event(
        EventEnvelope(
            id=str(uuid.uuid4()),
            type=event_type,
            entityType=entity_type,
            entityId=entity_id,
            action=action,
            timestamp=utcnow().isoformat(),
            actor={"userId": user.id, "role": role_value(user)},
            metadata={"amoId": tenant_id, **(metadata or {})},
        )
    )


def _user_summary(user: account_models.User | None) -> dict[str, Any] | None:
    if not user:
        return None
    department = getattr(user, "department", None)
    return {
        "id": user.id,
        "name": user.full_name,
        "email": user.email,
        "role": role_value(user),
        "department": getattr(department, "code", None),
        "active": bool(user.is_active and not user.is_system_account),
    }


def _load_users(db: Session, ids: set[str]) -> dict[str, account_models.User]:
    if not ids:
        return {}
    return {
        row.id: row
        for row in db.query(account_models.User).filter(account_models.User.id.in_(list(ids))).all()
    }


def _profile_payload(profile: dm.DocumentControlProfile | None, manual: manual_models.Manual) -> dict[str, Any]:
    return serialize_profile(profile, manual)


def _change_payload(row: dm.DocumentChangeRequest, users: dict[str, account_models.User] | None = None) -> dict[str, Any]:
    users = users or {}
    return {
        "id": row.id,
        "manual_id": row.manual_id,
        "revision_id": row.revision_id,
        "source_module": row.source_module,
        "source_entity_type": row.source_entity_type,
        "source_entity_id": row.source_entity_id,
        "title": row.title,
        "description": row.description,
        "priority": row.priority,
        "status": row.status,
        "proposer": _user_summary(users.get(row.proposer_user_id or "")),
        "owner": _user_summary(users.get(row.owner_user_id or "")),
        "due_at": row.due_at.isoformat() if row.due_at else None,
        "impact": dict(row.impact_json or {}),
        "training_impact_required": row.training_impact_required,
        "qms_blocking": row.qms_blocking,
        "resolution": row.resolution,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
    }


def _authority_payload(row: dm.DocumentAuthoritySubmission) -> dict[str, Any]:
    return {
        "id": row.id,
        "manual_id": row.manual_id,
        "revision_id": row.revision_id,
        "workflow_id": row.workflow_id,
        "authority_name": row.authority_name,
        "submission_reference": row.submission_reference,
        "status": row.status,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "submitted_by_user_id": row.submitted_by_user_id,
        "response_due_at": row.response_due_at.isoformat() if row.response_due_at else None,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "response_summary": row.response_summary,
        "evidence": list(row.evidence_json or []),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _tr_payload(row: dm.DocumentTemporaryRevision) -> dict[str, Any]:
    return {
        "id": row.id,
        "manual_id": row.manual_id,
        "base_revision_id": row.base_revision_id,
        "revision_id": row.revision_id,
        "tr_number": row.tr_number,
        "title": row.title,
        "reason": row.reason,
        "affected_sections": list(row.affected_sections_json or []),
        "filing_instructions": row.filing_instructions,
        "effective_date": row.effective_date.isoformat(),
        "expiry_date": row.expiry_date.isoformat(),
        "status": row.status,
        "approval_status": row.approval_status,
        "distribution_campaign_id": row.distribution_campaign_id,
        "incorporated_revision_id": row.incorporated_revision_id,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _campaign_payload(
    row: dm.DocumentDistributionCampaign,
    recipient_counts: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    counts = (recipient_counts or {}).get(row.id, {})
    return {
        "id": row.id,
        "manual_id": row.manual_id,
        "revision_id": row.revision_id,
        "temporary_revision_id": row.temporary_revision_id,
        "title": row.title,
        "audience": dict(row.audience_json or {}),
        "acknowledgement_required": row.acknowledgement_required,
        "due_at": row.due_at.isoformat() if row.due_at else None,
        "status": row.status,
        "issued_at": row.issued_at.isoformat() if row.issued_at else None,
        "issued_by_user_id": row.issued_by_user_id,
        "metadata": dict(row.metadata_json or {}),
        "recipients": counts,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _review_payload(row: dm.DocumentReviewPlan) -> dict[str, Any]:
    return {
        "id": row.id,
        "manual_id": row.manual_id,
        "revision_id": row.revision_id,
        "owner_user_id": row.owner_user_id,
        "due_at": row.due_at.isoformat(),
        "status": row.status,
        "outcome": row.outcome,
        "findings": list(row.findings_json or []),
        "actions": list(row.actions_json or []),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "completed_by_user_id": row.completed_by_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _copy_payload(row: dm.DocumentControlledCopy) -> dict[str, Any]:
    return {
        "id": row.id,
        "manual_id": row.manual_id,
        "revision_id": row.revision_id,
        "copy_number": row.copy_number,
        "format": row.format,
        "holder_user_id": row.holder_user_id,
        "holder_name": row.holder_name,
        "location_text": row.location_text,
        "status": row.status,
        "issued_at": row.issued_at.isoformat() if row.issued_at else None,
        "issued_by_user_id": row.issued_by_user_id,
        "due_back_at": row.due_back_at.isoformat() if row.due_back_at else None,
        "withdrawn_at": row.withdrawn_at.isoformat() if row.withdrawn_at else None,
        "metadata": dict(row.metadata_json or {}),
    }


def _external_source_payload(row: dm.ExternalDocumentSource) -> dict[str, Any]:
    return {
        "id": row.id,
        "manual_id": row.manual_id,
        "provider": row.provider,
        "authority": row.authority,
        "subscription_reference": row.subscription_reference,
        "access_url": row.access_url,
        "update_method": row.update_method,
        "status": row.status,
        "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None,
        "next_check_due_at": row.next_check_due_at.isoformat() if row.next_check_due_at else None,
        "metadata": dict(row.metadata_json or {}),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _applicability_payload(row: dm.DocumentApplicabilityRule) -> dict[str, Any]:
    return {
        "id": row.id,
        "manual_id": row.manual_id,
        "revision_id": row.revision_id,
        "rule_type": row.rule_type,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "target_value": row.target_value,
        "effective_from": row.effective_from.isoformat() if row.effective_from else None,
        "effective_to": row.effective_to.isoformat() if row.effective_to else None,
        "status": row.status,
        "source": row.source,
        "criteria": dict(row.criteria_json or {}),
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _integration_payload(row: dm.DocumentIntegrationLink) -> dict[str, Any]:
    return {
        "id": row.id,
        "manual_id": row.manual_id,
        "revision_id": row.revision_id,
        "change_request_id": row.change_request_id,
        "workflow_id": row.workflow_id,
        "source_module": row.source_module,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "relation_type": row.relation_type,
        "blocking": row.blocking,
        "status_snapshot": row.status_snapshot,
        "metadata": dict(row.metadata_json or {}),
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/t/{tenant_slug}/dashboard")
def dashboard(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    now = utcnow()
    today = date.today()
    manual_count = db.query(manual_models.Manual).filter(manual_models.Manual.tenant_id == tenant.id).count()
    revision_count = (
        db.query(manual_models.ManualRevision)
        .join(manual_models.Manual, manual_models.Manual.id == manual_models.ManualRevision.manual_id)
        .filter(manual_models.Manual.tenant_id == tenant.id)
        .count()
    )
    draft_revision_count = (
        db.query(manual_models.ManualRevision)
        .join(manual_models.Manual, manual_models.Manual.id == manual_models.ManualRevision.manual_id)
        .filter(
            manual_models.Manual.tenant_id == tenant.id,
            manual_models.ManualRevision.status_enum.in_([
                manual_models.ManualRevisionStatus.DRAFT,
                manual_models.ManualRevisionStatus.DEPARTMENT_REVIEW,
                manual_models.ManualRevisionStatus.QUALITY_APPROVAL,
                manual_models.ManualRevisionStatus.REGULATOR_SIGNOFF,
            ]),
        )
        .count()
    )
    effective_publications = (
        db.query(manual_models.Manual)
        .filter(
            manual_models.Manual.tenant_id == tenant.id,
            manual_models.Manual.current_published_rev_id.isnot(None),
        )
        .count()
    )
    open_changes = (
        db.query(dm.DocumentChangeRequest)
        .filter(dm.DocumentChangeRequest.tenant_id == tenant.amo_id, dm.DocumentChangeRequest.status.in_(OPEN_CHANGE_STATUSES))
        .count()
    )
    active_workflows = (
        db.query(dm.DocumentWorkflowInstance)
        .filter(dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id, dm.DocumentWorkflowInstance.state.in_(OPEN_WORKFLOW_STATES))
        .count()
    )
    authority_pending = (
        db.query(dm.DocumentAuthoritySubmission)
        .filter(
            dm.DocumentAuthoritySubmission.tenant_id == tenant.amo_id,
            dm.DocumentAuthoritySubmission.status.in_(["DRAFT", "SUBMITTED", "IN_REVIEW", "QUERY_RECEIVED"]),
        )
        .count()
    )
    tr_in_force = (
        db.query(dm.DocumentTemporaryRevision)
        .filter(dm.DocumentTemporaryRevision.tenant_id == tenant.amo_id, dm.DocumentTemporaryRevision.status == "IN_FORCE")
        .count()
    )
    tr_expiring = (
        db.query(dm.DocumentTemporaryRevision)
        .filter(
            dm.DocumentTemporaryRevision.tenant_id == tenant.amo_id,
            dm.DocumentTemporaryRevision.status == "IN_FORCE",
            dm.DocumentTemporaryRevision.expiry_date <= today + timedelta(days=30),
        )
        .count()
    )
    pending_acks = (
        db.query(dm.DocumentDistributionRecipient)
        .filter(
            dm.DocumentDistributionRecipient.tenant_id == tenant.amo_id,
            dm.DocumentDistributionRecipient.status == "PENDING",
        )
        .count()
    )
    overdue_acks = (
        db.query(dm.DocumentDistributionRecipient)
        .filter(
            dm.DocumentDistributionRecipient.tenant_id == tenant.amo_id,
            dm.DocumentDistributionRecipient.status == "PENDING",
            dm.DocumentDistributionRecipient.due_at.isnot(None),
            dm.DocumentDistributionRecipient.due_at < now,
        )
        .count()
    )
    reviews_due = (
        db.query(dm.DocumentReviewPlan)
        .filter(
            dm.DocumentReviewPlan.tenant_id == tenant.amo_id,
            dm.DocumentReviewPlan.status.in_(["SCHEDULED", "IN_PROGRESS"]),
            dm.DocumentReviewPlan.due_at <= now + timedelta(days=60),
        )
        .count()
    )
    external_checks_due = (
        db.query(dm.ExternalDocumentSource)
        .filter(
            dm.ExternalDocumentSource.tenant_id == tenant.amo_id,
            dm.ExternalDocumentSource.status == "ACTIVE",
            dm.ExternalDocumentSource.next_check_due_at.isnot(None),
            dm.ExternalDocumentSource.next_check_due_at <= now,
        )
        .count()
    )
    issued_copies = (
        db.query(dm.DocumentControlledCopy)
        .filter(dm.DocumentControlledCopy.tenant_id == tenant.amo_id, dm.DocumentControlledCopy.status == "ISSUED")
        .count()
    )
    activity = (
        db.query(manual_models.ManualAuditLog)
        .filter(manual_models.ManualAuditLog.tenant_id == tenant.id)
        .order_by(manual_models.ManualAuditLog.at.desc())
        .limit(12)
        .all()
    )
    return {
        "default_workspace": "CONTROL_DESK" if is_control_user(current_user) else "LIBRARY",
        "capabilities": {
            "read": True,
            "control": is_control_user(current_user),
            "approve": role_value(current_user) in {"SUPERUSER", "AMO_ADMIN", "QUALITY_MANAGER", "QUALITY_INSPECTOR"},
        },
        "metrics": {
            "document_records": manual_count,
            "revision_records": revision_count,
            "draft_revisions": draft_revision_count,
            "effective_publications": effective_publications,
            "open_change_requests": open_changes,
            "active_workflows": active_workflows,
            "authority_pending": authority_pending,
            "temporary_revisions_in_force": tr_in_force,
            "temporary_revisions_expiring_30_days": tr_expiring,
            "pending_acknowledgements": pending_acks,
            "overdue_acknowledgements": overdue_acks,
            "reviews_due_60_days": reviews_due,
            "external_currency_checks_due": external_checks_due,
            "issued_controlled_copies": issued_copies,
        },
        "recent_activity": [
            {
                "id": row.id,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "actor_id": row.actor_id,
                "at": row.at.isoformat() if row.at else None,
                "diff": dict(row.diff_json or {}),
            }
            for row in activity
        ],
    }


@router.get("/t/{tenant_slug}/documents")
def list_documents(
    tenant_slug: str,
    q: str | None = Query(default=None, max_length=255),
    document_class: str | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(manual_models.Manual).filter(manual_models.Manual.tenant_id == tenant.id)
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
    total = query.count()
    manuals = query.order_by(manual_models.Manual.code.asc()).offset((page - 1) * per_page).limit(per_page).all()
    manual_ids = [row.id for row in manuals]
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
    for revision in revisions:
        latest_by_manual.setdefault(revision.manual_id, revision)
    workflows = {
        row.revision_id: row
        for row in db.query(dm.DocumentWorkflowInstance).filter(
            dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id,
            dm.DocumentWorkflowInstance.manual_id.in_(manual_ids or ["-"]),
        ).all()
    }
    open_change_counts = dict(
        db.query(dm.DocumentChangeRequest.manual_id, func.count(dm.DocumentChangeRequest.id))
        .filter(
            dm.DocumentChangeRequest.tenant_id == tenant.amo_id,
            dm.DocumentChangeRequest.manual_id.in_(manual_ids or ["-"]),
            dm.DocumentChangeRequest.status.in_(OPEN_CHANGE_STATUSES),
        )
        .group_by(dm.DocumentChangeRequest.manual_id)
        .all()
    )
    pending_ack_counts = dict(
        db.query(dm.DocumentDistributionCampaign.manual_id, func.count(dm.DocumentDistributionRecipient.id))
        .join(dm.DocumentDistributionRecipient, dm.DocumentDistributionRecipient.campaign_id == dm.DocumentDistributionCampaign.id)
        .filter(
            dm.DocumentDistributionCampaign.tenant_id == tenant.amo_id,
            dm.DocumentDistributionCampaign.manual_id.in_(manual_ids or ["-"]),
            dm.DocumentDistributionRecipient.status == "PENDING",
        )
        .group_by(dm.DocumentDistributionCampaign.manual_id)
        .all()
    )
    items = []
    for manual in manuals:
        profile = profiles.get(manual.id)
        if document_class and (profile.document_class if profile else "INTERNAL") != document_class:
            continue
        if not can_read_manual(current_user, profile):
            continue
        target, target_kind = readable_revision(db, manual, current_user)
        latest = latest_by_manual.get(manual.id)
        payload = serialize_manual(manual, profile, target, target_kind, latest)
        workflow = workflows.get(latest.id) if latest else None
        payload["workflow"] = serialize_workflow(workflow) if workflow else None
        payload["open_change_requests"] = int(open_change_counts.get(manual.id, 0))
        payload["pending_acknowledgements"] = int(pending_ack_counts.get(manual.id, 0))
        items.append(payload)
    return {
        "items": items,
        "pagination": {"page": page, "per_page": per_page, "total": total, "returned": len(items)},
    }


@router.get("/t/{tenant_slug}/documents/{manual_id}/read-target")
def get_read_target(
    tenant_slug: str,
    manual_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    profile = get_profile(db, tenant, manual.id)
    require_manual_access(current_user, profile)
    revision, kind = readable_revision(db, manual, current_user)
    if not revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "NO_READABLE_REVISION",
                "message": "No effective revision is available. A controller may prepare or upload a revision.",
                "manual_id": manual.id,
            },
        )
    return {
        "manual_id": manual.id,
        "revision_id": revision.id,
        "kind": kind,
        "uncontrolled": kind == "UNCONTROLLED",
        "reader_path": f"/maintenance/{tenant_slug}/publications/{manual.id}/rev/{revision.id}/read",
        "revision": serialize_revision(revision),
    }


@router.get("/t/{tenant_slug}/documents/{manual_id}")
def get_document_detail(
    tenant_slug: str,
    manual_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    profile = get_profile(db, tenant, manual.id)
    require_manual_access(current_user, profile)
    revisions = (
        db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.manual_id == manual.id)
        .order_by(manual_models.ManualRevision.created_at.desc())
        .all()
    )
    target, target_kind = readable_revision(db, manual, current_user)
    changes = db.query(dm.DocumentChangeRequest).filter(dm.DocumentChangeRequest.tenant_id == tenant.amo_id, dm.DocumentChangeRequest.manual_id == manual.id).order_by(dm.DocumentChangeRequest.created_at.desc()).all()
    user_ids = {row.proposer_user_id for row in changes if row.proposer_user_id} | {row.owner_user_id for row in changes if row.owner_user_id}
    users = _load_users(db, user_ids)
    workflows = db.query(dm.DocumentWorkflowInstance).filter(dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id, dm.DocumentWorkflowInstance.manual_id == manual.id).order_by(dm.DocumentWorkflowInstance.created_at.desc()).all()
    workflow_ids = [row.id for row in workflows]
    decisions = db.query(dm.DocumentWorkflowDecision).filter(dm.DocumentWorkflowDecision.workflow_id.in_(workflow_ids or ["-"])).order_by(dm.DocumentWorkflowDecision.created_at.desc()).all()
    decision_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in decisions:
        decision_map[row.workflow_id].append({
            "id": row.id,
            "step_code": row.step_code,
            "decision": row.decision,
            "actor_user_id": row.actor_user_id,
            "from_state": row.from_state,
            "to_state": row.to_state,
            "comments": row.comments,
            "evidence": list(row.evidence_json or []),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })
    authority = db.query(dm.DocumentAuthoritySubmission).filter(dm.DocumentAuthoritySubmission.tenant_id == tenant.amo_id, dm.DocumentAuthoritySubmission.manual_id == manual.id).order_by(dm.DocumentAuthoritySubmission.created_at.desc()).all()
    temporary_revisions = db.query(dm.DocumentTemporaryRevision).filter(dm.DocumentTemporaryRevision.tenant_id == tenant.amo_id, dm.DocumentTemporaryRevision.manual_id == manual.id).order_by(dm.DocumentTemporaryRevision.created_at.desc()).all()
    campaigns = db.query(dm.DocumentDistributionCampaign).filter(dm.DocumentDistributionCampaign.tenant_id == tenant.amo_id, dm.DocumentDistributionCampaign.manual_id == manual.id).order_by(dm.DocumentDistributionCampaign.created_at.desc()).all()
    recipient_counts: dict[str, dict[str, int]] = {}
    for campaign in campaigns:
        rows = db.query(dm.DocumentDistributionRecipient.status, func.count(dm.DocumentDistributionRecipient.id)).filter(dm.DocumentDistributionRecipient.campaign_id == campaign.id).group_by(dm.DocumentDistributionRecipient.status).all()
        recipient_counts[campaign.id] = {str(state).lower(): int(count) for state, count in rows}
    reviews = db.query(dm.DocumentReviewPlan).filter(dm.DocumentReviewPlan.tenant_id == tenant.amo_id, dm.DocumentReviewPlan.manual_id == manual.id).order_by(dm.DocumentReviewPlan.due_at.desc()).all()
    copies = db.query(dm.DocumentControlledCopy).filter(dm.DocumentControlledCopy.tenant_id == tenant.amo_id, dm.DocumentControlledCopy.manual_id == manual.id).order_by(dm.DocumentControlledCopy.copy_number.asc()).all()
    sources = db.query(dm.ExternalDocumentSource).filter(dm.ExternalDocumentSource.tenant_id == tenant.amo_id, dm.ExternalDocumentSource.manual_id == manual.id).all()
    applicability = db.query(dm.DocumentApplicabilityRule).filter(dm.DocumentApplicabilityRule.tenant_id == tenant.amo_id, dm.DocumentApplicabilityRule.manual_id == manual.id).order_by(dm.DocumentApplicabilityRule.created_at.desc()).all()
    integrations = db.query(dm.DocumentIntegrationLink).filter(dm.DocumentIntegrationLink.tenant_id == tenant.amo_id, dm.DocumentIntegrationLink.manual_id == manual.id).order_by(dm.DocumentIntegrationLink.created_at.desc()).all()
    history = db.query(manual_models.ManualAuditLog).filter(manual_models.ManualAuditLog.tenant_id == tenant.id, manual_models.ManualAuditLog.entity_id.in_([manual.id] + [row.id for row in revisions])).order_by(manual_models.ManualAuditLog.at.desc()).limit(100).all()
    return {
        "document": serialize_manual(manual, profile, target, target_kind, revisions[0] if revisions else None),
        "revisions": [serialize_revision(row) for row in revisions],
        "changes": [_change_payload(row, users) for row in changes],
        "workflows": [
            {
                **serialize_workflow(row),
                "blockers": workflow_blockers(db, row),
                "decisions": decision_map.get(row.id, []),
            }
            for row in workflows
        ],
        "authority_submissions": [_authority_payload(row) for row in authority],
        "temporary_revisions": [_tr_payload(row) for row in temporary_revisions],
        "distribution_campaigns": [_campaign_payload(row, recipient_counts) for row in campaigns],
        "reviews": [_review_payload(row) for row in reviews],
        "controlled_copies": [_copy_payload(row) for row in copies],
        "external_sources": [_external_source_payload(row) for row in sources],
        "applicability": [_applicability_payload(row) for row in applicability],
        "integrations": [_integration_payload(row) for row in integrations],
        "history": [
            {
                "id": row.id,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "actor_id": row.actor_id,
                "at": row.at.isoformat() if row.at else None,
                "diff": dict(row.diff_json or {}),
            }
            for row in history
        ],
        "capabilities": {"control": is_control_user(current_user)},
    }


@router.put("/t/{tenant_slug}/documents/{manual_id}/profile")
def upsert_profile(
    tenant_slug: str,
    manual_id: str,
    payload: schemas.ProfileUpsert,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    profile = get_profile(db, tenant, manual.id)
    before = serialize_profile(profile, manual) if profile else profile_defaults(manual)
    if profile and payload.expected_version is not None and profile.version != payload.expected_version:
        raise HTTPException(status_code=409, detail={"message": "Document profile has changed", "current_version": profile.version})
    if not profile:
        profile = dm.DocumentControlProfile(tenant_id=tenant.amo_id, manual_id=manual.id)
        db.add(profile)
    profile.document_class = payload.document_class
    profile.owner_department = payload.owner_department.strip().upper()
    profile.owner_user_id = payload.owner_user_id
    profile.language = payload.language.strip() or "English"
    profile.criticality = payload.criticality
    profile.regulated_flag = payload.regulated_flag
    profile.restricted_flag = payload.restricted_flag
    profile.requires_authority_approval = payload.requires_authority_approval
    profile.acknowledgement_required = payload.acknowledgement_required
    profile.review_interval_months = payload.review_interval_months
    profile.next_review_due = payload.next_review_due
    profile.access_scope_json = dict(payload.access_scope)
    profile.tags_json = list(dict.fromkeys(item.strip() for item in payload.tags if item.strip()))
    profile.metadata_json = dict(payload.metadata)
    profile.version = max(1, int(profile.version or 0) + 1)
    db.flush()
    after = serialize_profile(profile, manual)
    audit(db, tenant, request, "document.profile.updated", "document_control_profile", profile.id, {"before": before, "after": after})
    db.commit()
    return after


@router.get("/t/{tenant_slug}/change-requests")
def list_change_requests(
    tenant_slug: str,
    status: str | None = None,
    manual_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(dm.DocumentChangeRequest).filter(dm.DocumentChangeRequest.tenant_id == tenant.amo_id)
    if status:
        query = query.filter(dm.DocumentChangeRequest.status == status)
    if manual_id:
        manual = get_manual(db, tenant, manual_id)
        require_manual_access(current_user, get_profile(db, tenant, manual.id))
        query = query.filter(dm.DocumentChangeRequest.manual_id == manual.id)
    rows = query.order_by(dm.DocumentChangeRequest.created_at.desc()).all()
    user_ids = {row.proposer_user_id for row in rows if row.proposer_user_id} | {row.owner_user_id for row in rows if row.owner_user_id}
    users = _load_users(db, user_ids)
    return [_change_payload(row, users) for row in rows]


@router.post("/t/{tenant_slug}/change-requests")
def create_change_request(
    tenant_slug: str,
    payload: schemas.ChangeRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    require_manual_access(current_user, get_profile(db, tenant, manual.id))
    if payload.revision_id:
        get_revision(db, manual, payload.revision_id)
    if payload.owner_user_id:
        active_tenant_users(db, tenant, [payload.owner_user_id])
    row = dm.DocumentChangeRequest(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=payload.revision_id,
        source_module=payload.source_module.strip().upper(),
        source_entity_type=payload.source_entity_type,
        source_entity_id=payload.source_entity_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        priority=payload.priority,
        status="OPEN",
        proposer_user_id=current_user.id,
        owner_user_id=payload.owner_user_id,
        due_at=payload.due_at,
        impact_json=dict(payload.impact),
        training_impact_required=payload.training_impact_required,
        qms_blocking=payload.qms_blocking,
    )
    db.add(row)
    db.flush()
    audit(db, tenant, request, "document.change.created", "document_change_request", row.id, {"manual_id": manual.id, "source_module": row.source_module})
    db.commit()
    _event(event_type="doc_control.change_created", entity_type="document_change_request", entity_id=row.id, action="created", user=current_user, tenant_id=tenant.amo_id, metadata={"manual_id": manual.id})
    return _change_payload(row, _load_users(db, {current_user.id, payload.owner_user_id} - {None}))


@router.patch("/t/{tenant_slug}/change-requests/{change_id}")
def update_change_request(
    tenant_slug: str,
    change_id: str,
    payload: schemas.ChangeRequestUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = db.query(dm.DocumentChangeRequest).filter(dm.DocumentChangeRequest.tenant_id == tenant.amo_id, dm.DocumentChangeRequest.id == change_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Change request not found")
    before = _change_payload(row)
    update = payload.model_dump(exclude_unset=True)
    if "owner_user_id" in update and update["owner_user_id"]:
        active_tenant_users(db, tenant, [update["owner_user_id"]])
    mapping = {
        "status": "status",
        "owner_user_id": "owner_user_id",
        "due_at": "due_at",
        "priority": "priority",
        "training_impact_required": "training_impact_required",
        "qms_blocking": "qms_blocking",
        "resolution": "resolution",
    }
    for source, target in mapping.items():
        if source in update:
            setattr(row, target, update[source])
    if "impact" in update:
        row.impact_json = dict(update["impact"] or {})
    if row.status in {"CLOSED", "REJECTED"}:
        row.closed_at = row.closed_at or utcnow()
    else:
        row.closed_at = None
    row.updated_at = utcnow()
    after = _change_payload(row)
    audit(db, tenant, request, "document.change.updated", "document_change_request", row.id, {"before": before, "after": after})
    db.commit()
    _event(event_type="doc_control.change_updated", entity_type="document_change_request", entity_id=row.id, action=row.status.lower(), user=current_user, tenant_id=tenant.amo_id, metadata={"manual_id": row.manual_id})
    return after


@router.post("/t/{tenant_slug}/workflows")
def create_workflow(
    tenant_slug: str,
    payload: schemas.WorkflowCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    revision = get_revision(db, manual, payload.revision_id)
    if revision.immutable_locked or status_value(revision) in {"PUBLISHED", "SUPERSEDED", "ARCHIVED"}:
        raise HTTPException(status_code=409, detail="Published, superseded, or archived revisions cannot enter a new editable workflow")
    existing = get_workflow(db, tenant, revision.id)
    if existing:
        return serialize_workflow(existing)
    profile = get_profile(db, tenant, manual.id)
    requires_authority = payload.requires_authority if payload.requires_authority is not None else bool(profile and profile.requires_authority_approval)
    workflow = dm.DocumentWorkflowInstance(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=revision.id,
        state="DRAFT",
        requires_authority=requires_authority,
        training_impact_required=payload.training_impact_required,
        training_readiness_status=payload.training_readiness_status,
        qms_readiness_status=payload.qms_readiness_status,
        distribution_readiness_status=payload.distribution_readiness_status,
        effective_at=payload.effective_at,
        created_by_user_id=current_user.id,
    )
    db.add(workflow)
    db.flush()
    audit(db, tenant, request, "document.workflow.created", "document_workflow", workflow.id, serialize_workflow(workflow))
    db.commit()
    return serialize_workflow(workflow)


@router.get("/t/{tenant_slug}/workflows")
def list_workflows(
    tenant_slug: str,
    state: str | None = None,
    manual_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(dm.DocumentWorkflowInstance).filter(dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id)
    if state:
        query = query.filter(dm.DocumentWorkflowInstance.state == state)
    if manual_id:
        get_manual(db, tenant, manual_id)
        query = query.filter(dm.DocumentWorkflowInstance.manual_id == manual_id)
    rows = query.order_by(dm.DocumentWorkflowInstance.updated_at.desc()).all()
    return [{**serialize_workflow(row), "blockers": workflow_blockers(db, row)} for row in rows]


@router.post("/t/{tenant_slug}/workflows/{workflow_id}/transition")
def transition_workflow(
    tenant_slug: str,
    workflow_id: str,
    payload: schemas.WorkflowTransitionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    workflow = db.query(dm.DocumentWorkflowInstance).filter(dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id, dm.DocumentWorkflowInstance.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Document workflow not found")
    if workflow.version != payload.expected_version:
        raise HTTPException(status_code=409, detail={"message": "Workflow has changed", "current_version": workflow.version, "state": workflow.state})
    manual = get_manual(db, tenant, workflow.manual_id)
    revision = get_revision(db, manual, workflow.revision_id)
    if payload.action in {"APPROVE_TECHNICAL", "APPROVE_QUALITY", "APPROVE_ACCOUNTABLE_MANAGER", "MARK_AUTHORITY_APPROVED", "PUBLISH", "ARCHIVE"}:
        require_approver(current_user, action=payload.action)
    if revision.immutable_locked and workflow.state not in {"PUBLISHED"}:
        raise HTTPException(status_code=409, detail="The revision is immutable")
    if payload.training_readiness_status is not None:
        workflow.training_readiness_status = payload.training_readiness_status
    if payload.qms_readiness_status is not None:
        workflow.qms_readiness_status = payload.qms_readiness_status
    if payload.distribution_readiness_status is not None:
        workflow.distribution_readiness_status = payload.distribution_readiness_status
    if payload.effective_at is not None:
        workflow.effective_at = payload.effective_at
    previous_state = workflow.state
    next_state = next_workflow_state(workflow, payload.action)
    if payload.action == "PUBLISH":
        blockers = workflow_blockers(db, workflow)
        if blockers:
            raise HTTPException(status_code=409, detail={"message": "Publication is blocked", "blockers": blockers})
        if workflow.effective_at and workflow.effective_at > utcnow():
            raise HTTPException(status_code=409, detail="The scheduled effectivity time has not been reached")
        publish_revision(db, tenant, manual, revision)
    else:
        sync_revision_status(revision, next_state)
    workflow.state = next_state
    workflow.version += 1
    workflow.updated_at = utcnow()
    decision = dm.DocumentWorkflowDecision(
        tenant_id=tenant.amo_id,
        workflow_id=workflow.id,
        step_code=payload.action,
        decision="APPROVED" if payload.action.startswith(("APPROVE", "MARK", "PUBLISH", "SCHEDULE")) else "SUBMITTED" if payload.action.startswith(("SUBMIT", "RESUBMIT")) else "CORRECTIONS_REQUESTED" if payload.action == "REQUEST_CORRECTIONS" else "COMPLETED",
        actor_user_id=current_user.id,
        from_state=previous_state,
        to_state=next_state,
        comments=payload.comments,
        evidence_json=list(payload.evidence),
    )
    db.add(decision)
    audit(db, tenant, request, "document.workflow.transitioned", "document_workflow", workflow.id, {"action": payload.action, "from": previous_state, "to": next_state, "version": workflow.version})
    db.commit()
    _event(event_type="doc_control.workflow_transitioned", entity_type="document_workflow", entity_id=workflow.id, action=payload.action.lower(), user=current_user, tenant_id=tenant.amo_id, metadata={"manual_id": manual.id, "revision_id": revision.id, "from": previous_state, "to": next_state})
    return {**serialize_workflow(workflow), "blockers": workflow_blockers(db, workflow)}


@router.get("/t/{tenant_slug}/authority-submissions")
def list_authority_submissions(
    tenant_slug: str,
    manual_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(dm.DocumentAuthoritySubmission).filter(dm.DocumentAuthoritySubmission.tenant_id == tenant.amo_id)
    if manual_id:
        get_manual(db, tenant, manual_id)
        query = query.filter(dm.DocumentAuthoritySubmission.manual_id == manual_id)
    if status:
        query = query.filter(dm.DocumentAuthoritySubmission.status == status)
    return [_authority_payload(row) for row in query.order_by(dm.DocumentAuthoritySubmission.created_at.desc()).all()]


@router.post("/t/{tenant_slug}/authority-submissions")
def create_authority_submission(
    tenant_slug: str,
    payload: schemas.AuthoritySubmissionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    revision = get_revision(db, manual, payload.revision_id)
    workflow = get_workflow(db, tenant, revision.id)
    if payload.workflow_id and (not workflow or workflow.id != payload.workflow_id):
        raise HTTPException(status_code=400, detail="Workflow does not match the revision")
    row = dm.DocumentAuthoritySubmission(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=revision.id,
        workflow_id=payload.workflow_id or (workflow.id if workflow else None),
        authority_name=payload.authority_name.strip(),
        submission_reference=payload.submission_reference.strip(),
        status="DRAFT",
        response_due_at=payload.response_due_at,
        evidence_json=list(payload.evidence),
    )
    db.add(row)
    db.flush()
    audit(db, tenant, request, "document.authority.created", "document_authority_submission", row.id, _authority_payload(row))
    db.commit()
    return _authority_payload(row)


@router.patch("/t/{tenant_slug}/authority-submissions/{submission_id}")
def update_authority_submission(
    tenant_slug: str,
    submission_id: str,
    payload: schemas.AuthoritySubmissionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_approver(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = db.query(dm.DocumentAuthoritySubmission).filter(dm.DocumentAuthoritySubmission.tenant_id == tenant.amo_id, dm.DocumentAuthoritySubmission.id == submission_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Authority submission not found")
    before = _authority_payload(row)
    row.status = payload.status
    row.response_summary = payload.response_summary
    row.response_due_at = payload.response_due_at
    if payload.evidence is not None:
        row.evidence_json = list(payload.evidence)
    if payload.status == "SUBMITTED":
        row.submitted_at = row.submitted_at or utcnow()
        row.submitted_by_user_id = row.submitted_by_user_id or current_user.id
    if payload.status == "APPROVED":
        row.approved_at = row.approved_at or utcnow()
    row.updated_at = utcnow()
    workflow = db.query(dm.DocumentWorkflowInstance).filter(dm.DocumentWorkflowInstance.id == row.workflow_id).first() if row.workflow_id else None
    if workflow and payload.status == "APPROVED" and workflow.state == "AUTHORITY_SUBMITTED":
        workflow.state = "AUTHORITY_APPROVED"
        workflow.version += 1
        workflow.updated_at = utcnow()
        sync_revision_status(get_revision(db, get_manual(db, tenant, row.manual_id), row.revision_id), workflow.state)
    after = _authority_payload(row)
    audit(db, tenant, request, "document.authority.updated", "document_authority_submission", row.id, {"before": before, "after": after})
    db.commit()
    _event(event_type="doc_control.authority_updated", entity_type="document_authority_submission", entity_id=row.id, action=row.status.lower(), user=current_user, tenant_id=tenant.amo_id, metadata={"manual_id": row.manual_id, "revision_id": row.revision_id})
    return after


@router.get("/t/{tenant_slug}/temporary-revisions")
def list_temporary_revisions(
    tenant_slug: str,
    manual_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(dm.DocumentTemporaryRevision).filter(dm.DocumentTemporaryRevision.tenant_id == tenant.amo_id)
    if manual_id:
        get_manual(db, tenant, manual_id)
        query = query.filter(dm.DocumentTemporaryRevision.manual_id == manual_id)
    if status:
        query = query.filter(dm.DocumentTemporaryRevision.status == status)
    rows = query.order_by(dm.DocumentTemporaryRevision.expiry_date.asc()).all()
    return [_tr_payload(row) for row in rows]


@router.post("/t/{tenant_slug}/temporary-revisions")
def create_temporary_revision(
    tenant_slug: str,
    payload: schemas.TemporaryRevisionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    get_revision(db, manual, payload.base_revision_id)
    if payload.revision_id:
        get_revision(db, manual, payload.revision_id)
    row = dm.DocumentTemporaryRevision(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        base_revision_id=payload.base_revision_id,
        revision_id=payload.revision_id,
        tr_number=payload.tr_number.strip(),
        title=payload.title.strip(),
        reason=payload.reason.strip(),
        affected_sections_json=list(payload.affected_sections),
        filing_instructions=payload.filing_instructions,
        effective_date=payload.effective_date,
        expiry_date=payload.expiry_date,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Temporary revision number already exists for the document") from exc
    audit(db, tenant, request, "document.tr.created", "document_temporary_revision", row.id, _tr_payload(row))
    db.commit()
    return _tr_payload(row)


@router.post("/t/{tenant_slug}/temporary-revisions/{tr_id}/transition")
def transition_temporary_revision(
    tenant_slug: str,
    tr_id: str,
    payload: schemas.TemporaryRevisionTransition,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_approver(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = db.query(dm.DocumentTemporaryRevision).filter(dm.DocumentTemporaryRevision.tenant_id == tenant.amo_id, dm.DocumentTemporaryRevision.id == tr_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Temporary revision not found")
    if payload.status == "IN_FORCE":
        if payload.approval_status != "APPROVED" and row.approval_status != "APPROVED":
            raise HTTPException(status_code=409, detail="Temporary revision approval is required")
        campaign_id = payload.distribution_campaign_id or row.distribution_campaign_id
        if not campaign_id:
            raise HTTPException(status_code=409, detail="A distribution campaign is required before the temporary revision can be in force")
        campaign = db.query(dm.DocumentDistributionCampaign).filter(dm.DocumentDistributionCampaign.id == campaign_id, dm.DocumentDistributionCampaign.status.in_(["ISSUED", "COMPLETED"])).first()
        if not campaign:
            raise HTTPException(status_code=409, detail="The temporary revision distribution campaign has not been issued")
    if payload.status == "INCORPORATED" and not (payload.incorporated_revision_id or row.incorporated_revision_id):
        raise HTTPException(status_code=409, detail="The incorporating permanent revision is required")
    before = _tr_payload(row)
    row.status = payload.status
    if payload.approval_status is not None:
        row.approval_status = payload.approval_status
    if payload.distribution_campaign_id is not None:
        row.distribution_campaign_id = payload.distribution_campaign_id
    if payload.incorporated_revision_id is not None:
        get_revision(db, get_manual(db, tenant, row.manual_id), payload.incorporated_revision_id)
        row.incorporated_revision_id = payload.incorporated_revision_id
    row.updated_at = utcnow()
    after = _tr_payload(row)
    audit(db, tenant, request, "document.tr.transitioned", "document_temporary_revision", row.id, {"before": before, "after": after})
    db.commit()
    _event(event_type="doc_control.temporary_revision_updated", entity_type="document_temporary_revision", entity_id=row.id, action=row.status.lower(), user=current_user, tenant_id=tenant.amo_id, metadata={"manual_id": row.manual_id})
    return after


@router.get("/t/{tenant_slug}/distribution-campaigns")
def list_distribution_campaigns(
    tenant_slug: str,
    manual_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(dm.DocumentDistributionCampaign).filter(dm.DocumentDistributionCampaign.tenant_id == tenant.amo_id)
    if manual_id:
        get_manual(db, tenant, manual_id)
        query = query.filter(dm.DocumentDistributionCampaign.manual_id == manual_id)
    if status:
        query = query.filter(dm.DocumentDistributionCampaign.status == status)
    rows = query.order_by(dm.DocumentDistributionCampaign.created_at.desc()).all()
    counts: dict[str, dict[str, int]] = {}
    for campaign in rows:
        status_rows = db.query(dm.DocumentDistributionRecipient.status, func.count(dm.DocumentDistributionRecipient.id)).filter(dm.DocumentDistributionRecipient.campaign_id == campaign.id).group_by(dm.DocumentDistributionRecipient.status).all()
        counts[campaign.id] = {str(key).lower(): int(value) for key, value in status_rows}
    return [_campaign_payload(row, counts) for row in rows]


@router.post("/t/{tenant_slug}/distribution-campaigns")
def create_distribution_campaign(
    tenant_slug: str,
    payload: schemas.DistributionCampaignCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    revision = get_revision(db, manual, payload.revision_id)
    if payload.temporary_revision_id:
        tr = db.query(dm.DocumentTemporaryRevision).filter(dm.DocumentTemporaryRevision.tenant_id == tenant.amo_id, dm.DocumentTemporaryRevision.id == payload.temporary_revision_id, dm.DocumentTemporaryRevision.manual_id == manual.id).first()
        if not tr:
            raise HTTPException(status_code=400, detail="Temporary revision does not match the document")
    users = active_tenant_users(db, tenant, payload.recipient_user_ids)
    row = dm.DocumentDistributionCampaign(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=revision.id,
        temporary_revision_id=payload.temporary_revision_id,
        title=payload.title.strip(),
        audience_json=dict(payload.audience),
        acknowledgement_required=payload.acknowledgement_required,
        due_at=payload.due_at,
        metadata_json=dict(payload.metadata),
    )
    db.add(row)
    db.flush()
    for user in users:
        db.add(dm.DocumentDistributionRecipient(tenant_id=tenant.amo_id, campaign_id=row.id, recipient_user_id=user.id, due_at=payload.due_at))
    audit(db, tenant, request, "document.distribution.created", "document_distribution_campaign", row.id, {"manual_id": manual.id, "revision_id": revision.id, "recipient_count": len(users)})
    db.commit()
    return _campaign_payload(row, {row.id: {"pending": len(users)}})


@router.post("/t/{tenant_slug}/distribution-campaigns/{campaign_id}/issue")
def issue_distribution_campaign(
    tenant_slug: str,
    campaign_id: str,
    payload: schemas.DistributionIssueRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    campaign = db.query(dm.DocumentDistributionCampaign).filter(dm.DocumentDistributionCampaign.tenant_id == tenant.amo_id, dm.DocumentDistributionCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Distribution campaign not found")
    if campaign.status not in {"DRAFT", "READY"}:
        raise HTTPException(status_code=409, detail="Only draft or ready campaigns can be issued")
    users = active_tenant_users(db, tenant, payload.recipient_user_ids)
    existing_recipient_ids = {
        row.recipient_user_id
        for row in db.query(dm.DocumentDistributionRecipient).filter(dm.DocumentDistributionRecipient.campaign_id == campaign.id).all()
        if row.recipient_user_id
    }
    due_at = payload.due_at or campaign.due_at or (utcnow() + timedelta(days=10))
    for user in users:
        if user.id not in existing_recipient_ids:
            db.add(dm.DocumentDistributionRecipient(tenant_id=tenant.amo_id, campaign_id=campaign.id, recipient_user_id=user.id, due_at=due_at))
    recipients = db.query(dm.DocumentDistributionRecipient).filter(dm.DocumentDistributionRecipient.campaign_id == campaign.id).all()
    if not recipients:
        raise HTTPException(status_code=409, detail="At least one active tenant recipient is required")
    issued_at = utcnow()
    for recipient in recipients:
        recipient.status = "PENDING" if campaign.acknowledgement_required else "DELIVERED"
        recipient.due_at = recipient.due_at or due_at
        recipient.notified_at = issued_at
        if campaign.acknowledgement_required and recipient.recipient_user_id:
            existing_ack = db.query(manual_models.Acknowledgement).filter(manual_models.Acknowledgement.revision_id == campaign.revision_id, manual_models.Acknowledgement.holder_user_id == recipient.recipient_user_id, manual_models.Acknowledgement.status_enum == "PENDING").first()
            if not existing_ack:
                db.add(manual_models.Acknowledgement(revision_id=campaign.revision_id, holder_user_id=recipient.recipient_user_id, due_at=recipient.due_at or due_at, status_enum="PENDING"))
    campaign.status = "ISSUED"
    campaign.issued_at = issued_at
    campaign.issued_by_user_id = current_user.id
    campaign.due_at = due_at
    workflow = get_workflow(db, tenant, campaign.revision_id)
    if workflow:
        workflow.distribution_readiness_status = "READY"
        workflow.version += 1
        workflow.updated_at = issued_at
    if campaign.temporary_revision_id:
        tr = db.query(dm.DocumentTemporaryRevision).filter(dm.DocumentTemporaryRevision.id == campaign.temporary_revision_id).first()
        if tr:
            tr.distribution_campaign_id = campaign.id
    audit(db, tenant, request, "document.distribution.issued", "document_distribution_campaign", campaign.id, {"recipient_count": len(recipients), "due_at": due_at.isoformat()})
    db.commit()
    _event(event_type="doc_control.distribution_issued", entity_type="document_distribution_campaign", entity_id=campaign.id, action="issued", user=current_user, tenant_id=tenant.amo_id, metadata={"manual_id": campaign.manual_id, "revision_id": campaign.revision_id, "recipient_count": len(recipients)})
    return _campaign_payload(campaign, {campaign.id: {"pending": sum(1 for row in recipients if row.status == "PENDING"), "delivered": sum(1 for row in recipients if row.status == "DELIVERED")}})


@router.post("/t/{tenant_slug}/distribution-campaigns/{campaign_id}/acknowledge")
def acknowledge_distribution_campaign(
    tenant_slug: str,
    campaign_id: str,
    payload: schemas.DistributionAcknowledgeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    campaign = db.query(dm.DocumentDistributionCampaign).filter(dm.DocumentDistributionCampaign.tenant_id == tenant.amo_id, dm.DocumentDistributionCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Distribution campaign not found")
    recipient = db.query(dm.DocumentDistributionRecipient).filter(dm.DocumentDistributionRecipient.campaign_id == campaign.id, dm.DocumentDistributionRecipient.recipient_user_id == current_user.id).first()
    if not recipient:
        raise HTTPException(status_code=403, detail="The current user is not a recipient of this campaign")
    if recipient.status != "ACKNOWLEDGED":
        recipient.status = "ACKNOWLEDGED"
        recipient.acknowledged_at = utcnow()
        recipient.evidence_json = list(payload.evidence)
    acknowledgement = db.query(manual_models.Acknowledgement).filter(manual_models.Acknowledgement.revision_id == campaign.revision_id, manual_models.Acknowledgement.holder_user_id == current_user.id, manual_models.Acknowledgement.status_enum == "PENDING").first()
    if acknowledgement:
        acknowledgement.acknowledged_at = recipient.acknowledged_at
        acknowledgement.acknowledgement_text = "I acknowledge that I have read and understood this controlled publication revision."
        acknowledgement.status_enum = "ACKNOWLEDGED"
    remaining = db.query(dm.DocumentDistributionRecipient).filter(dm.DocumentDistributionRecipient.campaign_id == campaign.id, dm.DocumentDistributionRecipient.status == "PENDING").count()
    if remaining == 0:
        campaign.status = "COMPLETED"
    audit(db, tenant, request, "document.distribution.acknowledged", "document_distribution_campaign", campaign.id, {"recipient_user_id": current_user.id, "remaining": remaining})
    db.commit()
    return {"status": recipient.status, "acknowledged_at": recipient.acknowledged_at.isoformat() if recipient.acknowledged_at else None, "campaign_status": campaign.status, "remaining": remaining}


@router.get("/t/{tenant_slug}/reviews")
def list_reviews(
    tenant_slug: str,
    status: str | None = None,
    manual_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(dm.DocumentReviewPlan).filter(dm.DocumentReviewPlan.tenant_id == tenant.amo_id)
    if status:
        query = query.filter(dm.DocumentReviewPlan.status == status)
    if manual_id:
        get_manual(db, tenant, manual_id)
        query = query.filter(dm.DocumentReviewPlan.manual_id == manual_id)
    return [_review_payload(row) for row in query.order_by(dm.DocumentReviewPlan.due_at.asc()).all()]


@router.post("/t/{tenant_slug}/reviews")
def create_review(
    tenant_slug: str,
    payload: schemas.ReviewPlanCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    if payload.revision_id:
        get_revision(db, manual, payload.revision_id)
    if payload.owner_user_id:
        active_tenant_users(db, tenant, [payload.owner_user_id])
    row = dm.DocumentReviewPlan(tenant_id=tenant.amo_id, manual_id=manual.id, revision_id=payload.revision_id, owner_user_id=payload.owner_user_id, due_at=payload.due_at)
    db.add(row)
    db.flush()
    audit(db, tenant, request, "document.review.created", "document_review_plan", row.id, _review_payload(row))
    db.commit()
    return _review_payload(row)


@router.post("/t/{tenant_slug}/reviews/{review_id}/complete")
def complete_review(
    tenant_slug: str,
    review_id: str,
    payload: schemas.ReviewCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = db.query(dm.DocumentReviewPlan).filter(dm.DocumentReviewPlan.tenant_id == tenant.amo_id, dm.DocumentReviewPlan.id == review_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Review plan not found")
    row.status = "COMPLETED"
    row.outcome = payload.outcome
    row.findings_json = list(payload.findings)
    row.actions_json = list(payload.actions)
    row.completed_at = utcnow()
    row.completed_by_user_id = current_user.id
    row.updated_at = utcnow()
    profile = get_profile(db, tenant, row.manual_id)
    if profile:
        profile.next_review_due = (row.completed_at + timedelta(days=30 * profile.review_interval_months)).date()
        profile.version += 1
    audit(db, tenant, request, "document.review.completed", "document_review_plan", row.id, _review_payload(row))
    db.commit()
    _event(event_type="doc_control.review_completed", entity_type="document_review_plan", entity_id=row.id, action="completed", user=current_user, tenant_id=tenant.amo_id, metadata={"manual_id": row.manual_id, "outcome": row.outcome})
    return _review_payload(row)


@router.get("/t/{tenant_slug}/controlled-copies")
def list_controlled_copies(
    tenant_slug: str,
    manual_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(dm.DocumentControlledCopy).filter(dm.DocumentControlledCopy.tenant_id == tenant.amo_id)
    if manual_id:
        get_manual(db, tenant, manual_id)
        query = query.filter(dm.DocumentControlledCopy.manual_id == manual_id)
    if status:
        query = query.filter(dm.DocumentControlledCopy.status == status)
    return [_copy_payload(row) for row in query.order_by(dm.DocumentControlledCopy.copy_number.asc()).all()]


@router.post("/t/{tenant_slug}/controlled-copies")
def create_controlled_copy(
    tenant_slug: str,
    payload: schemas.ControlledCopyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    revision = get_revision(db, manual, payload.revision_id)
    if status_value(revision) != "PUBLISHED":
        raise HTTPException(status_code=409, detail="Only a published revision can be issued as a controlled copy")
    if payload.holder_user_id:
        active_tenant_users(db, tenant, [payload.holder_user_id])
    row = dm.DocumentControlledCopy(tenant_id=tenant.amo_id, manual_id=manual.id, revision_id=revision.id, copy_number=payload.copy_number.strip(), format=payload.format, holder_user_id=payload.holder_user_id, holder_name=payload.holder_name, location_text=payload.location_text.strip(), issued_by_user_id=current_user.id, due_back_at=payload.due_back_at, metadata_json=dict(payload.metadata))
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Controlled copy number already exists for the document") from exc
    db.add(dm.DocumentControlledCopyEvent(tenant_id=tenant.amo_id, controlled_copy_id=row.id, event_type="ISSUE", actor_user_id=current_user.id, to_holder_user_id=row.holder_user_id, to_location=row.location_text))
    audit(db, tenant, request, "document.copy.issued", "document_controlled_copy", row.id, _copy_payload(row))
    db.commit()
    return _copy_payload(row)


@router.post("/t/{tenant_slug}/controlled-copies/{copy_id}/events")
def create_copy_event(
    tenant_slug: str,
    copy_id: str,
    payload: schemas.ControlledCopyEventCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = db.query(dm.DocumentControlledCopy).filter(dm.DocumentControlledCopy.tenant_id == tenant.amo_id, dm.DocumentControlledCopy.id == copy_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Controlled copy not found")
    if payload.to_holder_user_id:
        active_tenant_users(db, tenant, [payload.to_holder_user_id])
    event = dm.DocumentControlledCopyEvent(tenant_id=tenant.amo_id, controlled_copy_id=row.id, event_type=payload.event_type, actor_user_id=current_user.id, from_holder_user_id=row.holder_user_id, to_holder_user_id=payload.to_holder_user_id, from_location=row.location_text, to_location=payload.to_location, reason=payload.reason, evidence_json=list(payload.evidence))
    db.add(event)
    if payload.event_type in {"TRANSFER", "LOCATION_CHANGE"}:
        if payload.to_holder_user_id is not None:
            row.holder_user_id = payload.to_holder_user_id
            row.holder_name = None
        if payload.to_location:
            row.location_text = payload.to_location
    elif payload.event_type in {"RECALL"}:
        row.status = "RECALLED"
    elif payload.event_type in {"RETURN"}:
        row.status = "RETURNED"
    elif payload.event_type in {"WITHDRAW", "DESTROY"}:
        row.status = "WITHDRAWN" if payload.event_type == "WITHDRAW" else "DESTROYED"
        row.withdrawn_at = utcnow()
    audit(db, tenant, request, f"document.copy.{payload.event_type.lower()}", "document_controlled_copy", row.id, _copy_payload(row))
    db.commit()
    return _copy_payload(row)


@router.get("/t/{tenant_slug}/external-sources")
def list_external_sources(
    tenant_slug: str,
    manual_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(dm.ExternalDocumentSource).filter(dm.ExternalDocumentSource.tenant_id == tenant.amo_id)
    if manual_id:
        get_manual(db, tenant, manual_id)
        query = query.filter(dm.ExternalDocumentSource.manual_id == manual_id)
    return [_external_source_payload(row) for row in query.order_by(dm.ExternalDocumentSource.provider.asc()).all()]


@router.post("/t/{tenant_slug}/external-sources")
def create_external_source(
    tenant_slug: str,
    payload: schemas.ExternalSourceCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    profile = get_profile(db, tenant, manual.id)
    if profile and profile.document_class != "EXTERNAL":
        raise HTTPException(status_code=409, detail="The document profile must be classified as EXTERNAL")
    row = dm.ExternalDocumentSource(tenant_id=tenant.amo_id, manual_id=manual.id, provider=payload.provider.strip(), authority=payload.authority, subscription_reference=payload.subscription_reference, access_url=payload.access_url, update_method=payload.update_method, next_check_due_at=payload.next_check_due_at, metadata_json=dict(payload.metadata))
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An external source already exists for this document") from exc
    audit(db, tenant, request, "document.external_source.created", "external_document_source", row.id, _external_source_payload(row))
    db.commit()
    return _external_source_payload(row)


@router.post("/t/{tenant_slug}/external-sources/{source_id}/receipts")
def create_external_revision_receipt(
    tenant_slug: str,
    source_id: str,
    payload: schemas.ExternalRevisionReceiptCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    source = db.query(dm.ExternalDocumentSource).filter(dm.ExternalDocumentSource.tenant_id == tenant.amo_id, dm.ExternalDocumentSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="External document source not found")
    row = dm.ExternalRevisionReceipt(tenant_id=tenant.amo_id, source_id=source.id, manual_id=source.manual_id, revision_label=payload.revision_label.strip(), publication_date=payload.publication_date, received_by_user_id=current_user.id, checksum_sha256=payload.checksum_sha256, currency_status=payload.currency_status, applicability_status=payload.applicability_status, evidence_json=list(payload.evidence), notes=payload.notes)
    source.last_checked_at = utcnow()
    db.add(row)
    db.flush()
    audit(db, tenant, request, "document.external_revision.received", "external_revision_receipt", row.id, {"manual_id": row.manual_id, "revision_label": row.revision_label, "currency_status": row.currency_status})
    db.commit()
    _event(event_type="doc_control.external_revision_received", entity_type="external_revision_receipt", entity_id=row.id, action="received", user=current_user, tenant_id=tenant.amo_id, metadata={"manual_id": row.manual_id, "revision_label": row.revision_label})
    return {
        "id": row.id,
        "source_id": row.source_id,
        "manual_id": row.manual_id,
        "revision_label": row.revision_label,
        "publication_date": row.publication_date.isoformat() if row.publication_date else None,
        "received_at": row.received_at.isoformat(),
        "currency_status": row.currency_status,
        "applicability_status": row.applicability_status,
        "checksum_sha256": row.checksum_sha256,
        "evidence": list(row.evidence_json or []),
        "notes": row.notes,
    }


@router.get("/t/{tenant_slug}/applicability")
def list_applicability(
    tenant_slug: str,
    manual_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(dm.DocumentApplicabilityRule).filter(dm.DocumentApplicabilityRule.tenant_id == tenant.amo_id)
    if manual_id:
        get_manual(db, tenant, manual_id)
        query = query.filter(dm.DocumentApplicabilityRule.manual_id == manual_id)
    if target_type:
        query = query.filter(dm.DocumentApplicabilityRule.target_type == target_type)
    if target_id:
        query = query.filter(dm.DocumentApplicabilityRule.target_id == target_id)
    return [_applicability_payload(row) for row in query.order_by(dm.DocumentApplicabilityRule.created_at.desc()).all()]


@router.post("/t/{tenant_slug}/applicability")
def create_applicability(
    tenant_slug: str,
    payload: schemas.ApplicabilityRuleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    if payload.revision_id:
        get_revision(db, manual, payload.revision_id)
    row = dm.DocumentApplicabilityRule(tenant_id=tenant.amo_id, manual_id=manual.id, revision_id=payload.revision_id, rule_type=payload.rule_type, target_type=payload.target_type, target_id=payload.target_id, target_value=payload.target_value, effective_from=payload.effective_from, effective_to=payload.effective_to, source=payload.source, criteria_json=dict(payload.criteria), created_by_user_id=current_user.id)
    db.add(row)
    db.flush()
    audit(db, tenant, request, "document.applicability.created", "document_applicability_rule", row.id, _applicability_payload(row))
    db.commit()
    return _applicability_payload(row)


@router.get("/t/{tenant_slug}/integration-links")
def list_integration_links(
    tenant_slug: str,
    manual_id: str | None = None,
    source_module: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(dm.DocumentIntegrationLink).filter(dm.DocumentIntegrationLink.tenant_id == tenant.amo_id)
    if manual_id:
        get_manual(db, tenant, manual_id)
        query = query.filter(dm.DocumentIntegrationLink.manual_id == manual_id)
    if source_module:
        query = query.filter(dm.DocumentIntegrationLink.source_module == source_module.upper())
    if entity_type:
        query = query.filter(dm.DocumentIntegrationLink.entity_type == entity_type)
    if entity_id:
        query = query.filter(dm.DocumentIntegrationLink.entity_id == entity_id)
    return [_integration_payload(row) for row in query.order_by(dm.DocumentIntegrationLink.created_at.desc()).all()]


@router.post("/t/{tenant_slug}/integration-links")
def create_integration_link(
    tenant_slug: str,
    payload: schemas.IntegrationLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    if payload.revision_id:
        get_revision(db, manual, payload.revision_id)
    if payload.change_request_id:
        change = db.query(dm.DocumentChangeRequest).filter(dm.DocumentChangeRequest.tenant_id == tenant.amo_id, dm.DocumentChangeRequest.id == payload.change_request_id, dm.DocumentChangeRequest.manual_id == manual.id).first()
        if not change:
            raise HTTPException(status_code=400, detail="Change request does not match the document")
    if payload.workflow_id:
        workflow = db.query(dm.DocumentWorkflowInstance).filter(dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id, dm.DocumentWorkflowInstance.id == payload.workflow_id, dm.DocumentWorkflowInstance.manual_id == manual.id).first()
        if not workflow:
            raise HTTPException(status_code=400, detail="Workflow does not match the document")
    if payload.source_module == "QMS" and not (is_control_user(current_user) or getattr(current_user, "is_auditor", False)):
        raise HTTPException(status_code=403, detail="QMS or Document Control privileges required")
    row = dm.DocumentIntegrationLink(tenant_id=tenant.amo_id, manual_id=manual.id, revision_id=payload.revision_id, change_request_id=payload.change_request_id, workflow_id=payload.workflow_id, source_module=payload.source_module, entity_type=payload.entity_type, entity_id=payload.entity_id, relation_type=payload.relation_type, blocking=payload.blocking, status_snapshot=payload.status_snapshot, metadata_json=dict(payload.metadata), created_by_user_id=current_user.id)
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This integration link already exists") from exc
    audit(db, tenant, request, "document.integration_link.created", "document_integration_link", row.id, _integration_payload(row))
    db.commit()
    _event(event_type="doc_control.integration_linked", entity_type="document_integration_link", entity_id=row.id, action="linked", user=current_user, tenant_id=tenant.amo_id, metadata={"manual_id": manual.id, "source_module": row.source_module, "source_entity_id": row.entity_id})
    return _integration_payload(row)


@router.get("/t/{tenant_slug}/reports/master-register")
def master_register_report(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manuals = db.query(manual_models.Manual).filter(manual_models.Manual.tenant_id == tenant.id).order_by(manual_models.Manual.code.asc()).all()
    profiles = {row.manual_id: row for row in db.query(dm.DocumentControlProfile).filter(dm.DocumentControlProfile.tenant_id == tenant.amo_id).all()}
    items = []
    for manual in manuals:
        profile = profiles.get(manual.id)
        if not can_read_manual(current_user, profile):
            continue
        latest = latest_revision(db, manual)
        published = get_revision(db, manual, manual.current_published_rev_id) if manual.current_published_rev_id else None
        items.append({
            "manual_id": manual.id,
            "code": manual.code,
            "title": manual.title,
            "document_class": profile.document_class if profile else "INTERNAL",
            "owner_department": profile.owner_department if profile else manual.owner_role,
            "regulated": bool(profile and profile.regulated_flag),
            "restricted": bool(profile and profile.restricted_flag),
            "latest_revision": serialize_revision(latest),
            "effective_revision": serialize_revision(published),
            "next_review_due": profile.next_review_due.isoformat() if profile and profile.next_review_due else None,
        })
    return {"generated_at": utcnow().isoformat(), "tenant": tenant.slug, "items": items}


@router.get("/t/{tenant_slug}/reports/overdue")
def overdue_report(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    now = utcnow()
    today = date.today()
    changes = db.query(dm.DocumentChangeRequest).filter(dm.DocumentChangeRequest.tenant_id == tenant.amo_id, dm.DocumentChangeRequest.status.in_(OPEN_CHANGE_STATUSES), dm.DocumentChangeRequest.due_at.isnot(None), dm.DocumentChangeRequest.due_at < now).all()
    reviews = db.query(dm.DocumentReviewPlan).filter(dm.DocumentReviewPlan.tenant_id == tenant.amo_id, dm.DocumentReviewPlan.status.in_(["SCHEDULED", "IN_PROGRESS"]), dm.DocumentReviewPlan.due_at < now).all()
    acknowledgements = db.query(dm.DocumentDistributionRecipient).filter(dm.DocumentDistributionRecipient.tenant_id == tenant.amo_id, dm.DocumentDistributionRecipient.status == "PENDING", dm.DocumentDistributionRecipient.due_at.isnot(None), dm.DocumentDistributionRecipient.due_at < now).all()
    temporary_revisions = db.query(dm.DocumentTemporaryRevision).filter(dm.DocumentTemporaryRevision.tenant_id == tenant.amo_id, dm.DocumentTemporaryRevision.status == "IN_FORCE", dm.DocumentTemporaryRevision.expiry_date < today).all()
    external_sources = db.query(dm.ExternalDocumentSource).filter(dm.ExternalDocumentSource.tenant_id == tenant.amo_id, dm.ExternalDocumentSource.status == "ACTIVE", dm.ExternalDocumentSource.next_check_due_at.isnot(None), dm.ExternalDocumentSource.next_check_due_at < now).all()
    return {
        "generated_at": now.isoformat(),
        "change_requests": [_change_payload(row) for row in changes],
        "reviews": [_review_payload(row) for row in reviews],
        "acknowledgements": [{"id": row.id, "campaign_id": row.campaign_id, "recipient_user_id": row.recipient_user_id, "due_at": row.due_at.isoformat() if row.due_at else None, "reminder_count": row.reminder_count} for row in acknowledgements],
        "temporary_revisions": [_tr_payload(row) for row in temporary_revisions],
        "external_sources": [_external_source_payload(row) for row in external_sources],
    }
