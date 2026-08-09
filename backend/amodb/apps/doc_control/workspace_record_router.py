from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from .workspace_capabilities import document_control_capabilities, reader_capabilities
from .workspace_responsibility_access import workflow_actions_for_user
from .workspace_router import (
    _applicability_payload,
    _authority_payload,
    _campaign_payload,
    _change_payload,
    _copy_payload,
    _external_source_payload,
    _integration_payload,
    _load_users,
    _review_payload,
    _tr_payload,
)
from .workspace_service import (
    get_manual,
    get_profile,
    is_control_user,
    readable_revision,
    require_manual_access,
    resolve_tenant,
    role_value,
    serialize_manual,
    serialize_revision,
    serialize_workflow,
    workflow_blockers,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Record"])

# A document workspace is a daily operational summary, not an unbounded register.
# Deeper portfolios and reports own exhaustive paging/search. Each collection uses
# LIMIT + 1 so the API can tell the client that more evidence exists without
# materialising the tenant's entire lifecycle into one browser request.
_COLLECTION_LIMITS: dict[str, int] = {
    "revisions": 50,
    "changes": 50,
    "workflows": 25,
    "authority_submissions": 50,
    "temporary_revisions": 50,
    "distribution_campaigns": 50,
    "reviews": 50,
    "controlled_copies": 100,
    "external_sources": 50,
    "applicability": 100,
    "integrations": 100,
    "history": 250,
    "active_users": 200,
}


def _bounded(query, limit: int):
    rows = query.limit(limit + 1).all()
    return rows[:limit], len(rows) > limit


def _bound_meta(limit: int, returned: int, has_more: bool) -> dict[str, Any]:
    return {"limit": limit, "returned": returned, "has_more": has_more}


def _entity_ids_for_document(detail: dict) -> set[str]:
    identifiers: set[str] = set()
    document = detail.get("document") or {}
    if document.get("id"):
        identifiers.add(str(document["id"]))
    for collection in (
        "revisions",
        "changes",
        "workflows",
        "authority_submissions",
        "temporary_revisions",
        "distribution_campaigns",
        "reviews",
        "controlled_copies",
        "external_sources",
        "applicability",
        "integrations",
    ):
        for row in detail.get(collection) or []:
            if row.get("id"):
                identifiers.add(str(row["id"]))
    return identifiers


def _controller_history(
    db: Session,
    tenant_id: str,
    detail: dict,
) -> tuple[list[dict], bool]:
    """Collect bounded domain events belonging to the visible unified record."""
    entity_ids = _entity_ids_for_document(detail)
    if not entity_ids:
        return [], False
    rows, has_more = _bounded(
        db.query(manual_models.ManualAuditLog)
        .filter(
            manual_models.ManualAuditLog.tenant_id == tenant_id,
            manual_models.ManualAuditLog.entity_id.in_(sorted(entity_ids)),
        )
        .order_by(manual_models.ManualAuditLog.at.desc()),
        _COLLECTION_LIMITS["history"],
    )
    return [
        {
            "id": row.id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "actor_id": row.actor_id,
            "at": row.at.isoformat() if row.at else None,
            "diff": dict(row.diff_json or {}),
        }
        for row in rows
    ], has_more


def _active_tenant_people(db: Session, amo_id: str) -> tuple[list[dict], bool]:
    rows, has_more = _bounded(
        db.query(account_models.User)
        .filter(
            account_models.User.amo_id == amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .order_by(account_models.User.full_name.asc(), account_models.User.email.asc()),
        _COLLECTION_LIMITS["active_users"],
    )
    return [
        {
            "id": row.id,
            "name": row.full_name,
            "email": row.email,
            "role": role_value(row),
            "department": getattr(getattr(row, "department", None), "code", None),
            "active": True,
        }
        for row in rows
    ], has_more


def _bounded_document_detail(
    db: Session,
    *,
    tenant,
    manual: manual_models.Manual,
    current_user: account_models.User,
) -> dict[str, Any]:
    profile = get_profile(db, tenant, manual.id)
    require_manual_access(current_user, profile)
    bounds: dict[str, dict[str, Any]] = {}

    revisions, revisions_more = _bounded(
        db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.manual_id == manual.id)
        .order_by(manual_models.ManualRevision.created_at.desc(), manual_models.ManualRevision.id.desc()),
        _COLLECTION_LIMITS["revisions"],
    )
    bounds["revisions"] = _bound_meta(_COLLECTION_LIMITS["revisions"], len(revisions), revisions_more)
    target, target_kind = readable_revision(db, manual, current_user)

    changes, changes_more = _bounded(
        db.query(dm.DocumentChangeRequest)
        .filter(dm.DocumentChangeRequest.tenant_id == tenant.amo_id, dm.DocumentChangeRequest.manual_id == manual.id)
        .order_by(dm.DocumentChangeRequest.created_at.desc()),
        _COLLECTION_LIMITS["changes"],
    )
    bounds["changes"] = _bound_meta(_COLLECTION_LIMITS["changes"], len(changes), changes_more)
    user_ids = {row.proposer_user_id for row in changes if row.proposer_user_id} | {row.owner_user_id for row in changes if row.owner_user_id}
    users = _load_users(db, user_ids)

    workflows, workflows_more = _bounded(
        db.query(dm.DocumentWorkflowInstance)
        .filter(dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id, dm.DocumentWorkflowInstance.manual_id == manual.id)
        .order_by(dm.DocumentWorkflowInstance.created_at.desc()),
        _COLLECTION_LIMITS["workflows"],
    )
    bounds["workflows"] = _bound_meta(_COLLECTION_LIMITS["workflows"], len(workflows), workflows_more)
    workflow_ids = [row.id for row in workflows]
    decision_rows = (
        db.query(dm.DocumentWorkflowDecision)
        .filter(dm.DocumentWorkflowDecision.workflow_id.in_(workflow_ids or ["-"]))
        .order_by(dm.DocumentWorkflowDecision.created_at.desc())
        .limit(_COLLECTION_LIMITS["workflows"] * 20)
        .all()
    )
    decision_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in decision_rows:
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

    authority, authority_more = _bounded(
        db.query(dm.DocumentAuthoritySubmission)
        .filter(dm.DocumentAuthoritySubmission.tenant_id == tenant.amo_id, dm.DocumentAuthoritySubmission.manual_id == manual.id)
        .order_by(dm.DocumentAuthoritySubmission.created_at.desc()),
        _COLLECTION_LIMITS["authority_submissions"],
    )
    bounds["authority_submissions"] = _bound_meta(_COLLECTION_LIMITS["authority_submissions"], len(authority), authority_more)

    temporary_revisions, tr_more = _bounded(
        db.query(dm.DocumentTemporaryRevision)
        .filter(dm.DocumentTemporaryRevision.tenant_id == tenant.amo_id, dm.DocumentTemporaryRevision.manual_id == manual.id)
        .order_by(dm.DocumentTemporaryRevision.created_at.desc()),
        _COLLECTION_LIMITS["temporary_revisions"],
    )
    bounds["temporary_revisions"] = _bound_meta(_COLLECTION_LIMITS["temporary_revisions"], len(temporary_revisions), tr_more)

    campaigns, campaigns_more = _bounded(
        db.query(dm.DocumentDistributionCampaign)
        .filter(dm.DocumentDistributionCampaign.tenant_id == tenant.amo_id, dm.DocumentDistributionCampaign.manual_id == manual.id)
        .order_by(dm.DocumentDistributionCampaign.created_at.desc()),
        _COLLECTION_LIMITS["distribution_campaigns"],
    )
    bounds["distribution_campaigns"] = _bound_meta(_COLLECTION_LIMITS["distribution_campaigns"], len(campaigns), campaigns_more)
    campaign_ids = [row.id for row in campaigns]
    recipient_counts: dict[str, dict[str, int]] = defaultdict(dict)
    if campaign_ids:
        for campaign_id, state, count in (
            db.query(
                dm.DocumentDistributionRecipient.campaign_id,
                dm.DocumentDistributionRecipient.status,
                func.count(dm.DocumentDistributionRecipient.id),
            )
            .filter(dm.DocumentDistributionRecipient.campaign_id.in_(campaign_ids))
            .group_by(dm.DocumentDistributionRecipient.campaign_id, dm.DocumentDistributionRecipient.status)
            .all()
        ):
            recipient_counts[str(campaign_id)][str(state).lower()] = int(count)

    reviews, reviews_more = _bounded(
        db.query(dm.DocumentReviewPlan)
        .filter(dm.DocumentReviewPlan.tenant_id == tenant.amo_id, dm.DocumentReviewPlan.manual_id == manual.id)
        .order_by(dm.DocumentReviewPlan.due_at.desc()),
        _COLLECTION_LIMITS["reviews"],
    )
    bounds["reviews"] = _bound_meta(_COLLECTION_LIMITS["reviews"], len(reviews), reviews_more)

    copies, copies_more = _bounded(
        db.query(dm.DocumentControlledCopy)
        .filter(dm.DocumentControlledCopy.tenant_id == tenant.amo_id, dm.DocumentControlledCopy.manual_id == manual.id)
        .order_by(dm.DocumentControlledCopy.copy_number.asc()),
        _COLLECTION_LIMITS["controlled_copies"],
    )
    bounds["controlled_copies"] = _bound_meta(_COLLECTION_LIMITS["controlled_copies"], len(copies), copies_more)

    sources, sources_more = _bounded(
        db.query(dm.ExternalDocumentSource)
        .filter(dm.ExternalDocumentSource.tenant_id == tenant.amo_id, dm.ExternalDocumentSource.manual_id == manual.id)
        .order_by(dm.ExternalDocumentSource.updated_at.desc()),
        _COLLECTION_LIMITS["external_sources"],
    )
    bounds["external_sources"] = _bound_meta(_COLLECTION_LIMITS["external_sources"], len(sources), sources_more)

    applicability, applicability_more = _bounded(
        db.query(dm.DocumentApplicabilityRule)
        .filter(dm.DocumentApplicabilityRule.tenant_id == tenant.amo_id, dm.DocumentApplicabilityRule.manual_id == manual.id)
        .order_by(dm.DocumentApplicabilityRule.created_at.desc()),
        _COLLECTION_LIMITS["applicability"],
    )
    bounds["applicability"] = _bound_meta(_COLLECTION_LIMITS["applicability"], len(applicability), applicability_more)

    integrations, integrations_more = _bounded(
        db.query(dm.DocumentIntegrationLink)
        .filter(dm.DocumentIntegrationLink.tenant_id == tenant.amo_id, dm.DocumentIntegrationLink.manual_id == manual.id)
        .order_by(dm.DocumentIntegrationLink.created_at.desc()),
        _COLLECTION_LIMITS["integrations"],
    )
    bounds["integrations"] = _bound_meta(_COLLECTION_LIMITS["integrations"], len(integrations), integrations_more)

    workflow_payloads: list[dict[str, Any]] = []
    workflow_actions: dict[str, list[str]] = {}
    for row in workflows:
        actions = workflow_actions_for_user(db, workflow=row, user=current_user)
        workflow_actions[row.id] = actions
        workflow_payloads.append({
            **serialize_workflow(row),
            "blockers": workflow_blockers(db, row),
            "decisions": decision_map.get(row.id, []),
            "allowed_actions": actions,
        })

    return {
        "document": serialize_manual(manual, profile, target, target_kind, revisions[0] if revisions else None),
        "revisions": [serialize_revision(row) for row in revisions],
        "changes": [_change_payload(row, users) for row in changes],
        "workflows": workflow_payloads,
        "authority_submissions": [_authority_payload(row) for row in authority],
        "temporary_revisions": [_tr_payload(row) for row in temporary_revisions],
        "distribution_campaigns": [_campaign_payload(row, recipient_counts) for row in campaigns],
        "reviews": [_review_payload(row) for row in reviews],
        "controlled_copies": [_copy_payload(row) for row in copies],
        "external_sources": [_external_source_payload(row) for row in sources],
        "applicability": [_applicability_payload(row) for row in applicability],
        "integrations": [_integration_payload(row) for row in integrations],
        "history": [],
        "active_users": [],
        "collection_bounds": bounds,
        "workflow_actions": workflow_actions,
    }


def _reader_detail(
    db: Session,
    *,
    tenant_slug: str,
    manual_id: str,
    current_user: account_models.User,
) -> dict:
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    profile = get_profile(db, tenant, manual.id)
    require_manual_access(current_user, profile)
    target, target_kind = readable_revision(db, manual, current_user)
    document = serialize_manual(manual, profile, target, target_kind, target)
    profile_payload = document.get("profile")
    if isinstance(profile_payload, dict):
        profile_payload["access_scope"] = {}
        profile_payload["metadata"] = {}
    return {
        "document": document,
        "revisions": [serialize_revision(target)] if target else [],
        "changes": [],
        "workflows": [],
        "authority_submissions": [],
        "temporary_revisions": [],
        "distribution_campaigns": [],
        "reviews": [],
        "controlled_copies": [],
        "external_sources": [],
        "applicability": [],
        "integrations": [],
        "history": [],
        "active_users": [],
        "collection_bounds": {},
        "workflow_actions": {},
        "capabilities": reader_capabilities(),
    }


@router.get("/t/{tenant_slug}/documents/{manual_id}", include_in_schema=False)
def get_role_appropriate_document_detail(
    tenant_slug: str,
    manual_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Return a bounded controller/reviewer workspace or minimal reader projection."""
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    profile = get_profile(db, tenant, manual.id)
    require_manual_access(current_user, profile)

    candidate_workflows = (
        db.query(dm.DocumentWorkflowInstance)
        .filter(
            dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id,
            dm.DocumentWorkflowInstance.manual_id == manual.id,
            dm.DocumentWorkflowInstance.state.notin_(["PUBLISHED", "ARCHIVED"]),
        )
        .order_by(dm.DocumentWorkflowInstance.updated_at.desc())
        .limit(_COLLECTION_LIMITS["workflows"])
        .all()
    )
    reviewer_actions = {
        row.id: workflow_actions_for_user(db, workflow=row, user=current_user)
        for row in candidate_workflows
    }
    participates = any(reviewer_actions.values())

    if not is_control_user(current_user) and not participates:
        return _reader_detail(
            db,
            tenant_slug=tenant_slug,
            manual_id=manual_id,
            current_user=current_user,
        )

    detail = _bounded_document_detail(
        db,
        tenant=tenant,
        manual=manual,
        current_user=current_user,
    )
    history, history_more = _controller_history(db, tenant.id, detail)
    detail["history"] = history
    detail["collection_bounds"]["history"] = _bound_meta(_COLLECTION_LIMITS["history"], len(history), history_more)

    if is_control_user(current_user):
        people, people_more = _active_tenant_people(db, tenant.amo_id)
        detail["active_users"] = people
        detail["collection_bounds"]["active_users"] = _bound_meta(_COLLECTION_LIMITS["active_users"], len(people), people_more)
        detail["capabilities"] = {
            **document_control_capabilities(current_user),
            "review": participates,
        }
    else:
        # A reviewer may inspect the document lifecycle needed for the assigned
        # decision, but does not receive tenant people directories, copy-holder
        # custody data, or control/configuration capabilities.
        profile_payload = (detail.get("document") or {}).get("profile")
        if isinstance(profile_payload, dict):
            profile_payload["access_scope"] = {}
            profile_payload["metadata"] = {}
        detail["active_users"] = []
        detail["controlled_copies"] = []
        detail["collection_bounds"]["controlled_copies"] = _bound_meta(_COLLECTION_LIMITS["controlled_copies"], 0, False)
        detail["capabilities"] = {
            **reader_capabilities(),
            "review": True,
        }

    return detail
