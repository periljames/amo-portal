from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_decision_policy import is_decision_approver, require_decision_approver
from .workspace_integration_router import refresh_integration_link
from .workspace_responsibility_access import require_workflow_action
from .workspace_router import _event
from .workspace_service import (
    audit,
    get_manual,
    get_revision,
    next_workflow_state,
    publish_revision,
    resolve_tenant,
    serialize_workflow,
    sync_revision_status,
    utcnow,
    workflow_blockers,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Workflow"])
_OPEN_CHANGE_STATUSES = {"OPEN", "ASSESSING", "ACCEPTED", "IMPLEMENTING"}
_RESOLVED_LINK_STATUSES = {"CLOSED", "RESOLVED", "READY", "COMPLETED", "WAIVED", "NOT_REQUIRED"}


def _module_links(
    db: Session,
    *,
    workflow: dm.DocumentWorkflowInstance,
    modules: set[str] | None = None,
) -> list[dm.DocumentIntegrationLink]:
    query = db.query(dm.DocumentIntegrationLink).filter(
        dm.DocumentIntegrationLink.tenant_id == workflow.tenant_id,
        dm.DocumentIntegrationLink.workflow_id == workflow.id,
    )
    rows = query.all()
    if modules is None:
        return rows
    normalized = {value.upper() for value in modules}
    return [row for row in rows if str(row.source_module or "").upper() in normalized]


def _refresh_links(
    db: Session,
    *,
    tenant,
    links: list[dm.DocumentIntegrationLink],
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for link in links:
        try:
            refresh_integration_link(db, tenant, link)
        except HTTPException as exc:
            failures.append(
                {
                    "code": "INTEGRATION_SOURCE_UNAVAILABLE",
                    "message": (
                        f"{link.source_module} {link.entity_type} {link.entity_id} "
                        f"could not be verified: {exc.detail}"
                    ),
                }
            )
    return failures


def _resolved_integration_exists(
    db: Session,
    *,
    tenant,
    workflow: dm.DocumentWorkflowInstance,
    modules: set[str],
) -> bool:
    links = _module_links(db, workflow=workflow, modules=modules)
    if not links:
        return False
    if _refresh_links(db, tenant=tenant, links=links):
        return False
    return any(
        str(row.status_snapshot or "").upper() in _RESOLVED_LINK_STATUSES
        for row in links
    )


def _validate_readiness_change(
    db: Session,
    *,
    tenant,
    workflow: dm.DocumentWorkflowInstance,
    payload: schemas.WorkflowTransitionRequest,
    current_user: account_models.User,
) -> None:
    proposed = {
        "training": payload.training_readiness_status,
        "qms": payload.qms_readiness_status,
        "distribution": payload.distribution_readiness_status,
    }
    if not any(value is not None for value in proposed.values()):
        return

    require_decision_approver(current_user)
    comments = str(payload.comments or "").strip()
    evidence = list(payload.evidence or [])

    if proposed["distribution"] == "READY":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DISTRIBUTION_READY_IS_SYSTEM_MANAGED",
                "message": "Issue a real distribution campaign; readiness cannot be marked ready manually.",
            },
        )

    if proposed["training"] == "READY" and not _resolved_integration_exists(
        db,
        tenant=tenant,
        workflow=workflow,
        modules={"TRAINING", "TRAINING_AND_COMPETENCE"},
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TRAINING_LINK_NOT_READY",
                "message": "A live, resolved Training integration link is required before training readiness can be marked ready.",
            },
        )

    if proposed["qms"] == "READY" and not _resolved_integration_exists(
        db,
        tenant=tenant,
        workflow=workflow,
        modules={"QMS", "QUALITY", "QUALITY_AND_COMPLIANCE"},
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "QMS_LINK_NOT_READY",
                "message": "A live, resolved QMS integration link is required before QMS readiness can be marked ready.",
            },
        )

    if any(value == "WAIVED" for value in proposed.values() if value is not None):
        if not comments or not evidence:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "WAIVER_EVIDENCE_REQUIRED",
                    "message": "A waiver requires a reason and supporting evidence.",
                },
            )


def _publication_blockers(
    db: Session,
    *,
    tenant,
    workflow: dm.DocumentWorkflowInstance,
) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []

    open_changes = (
        db.query(func.count(dm.DocumentChangeRequest.id))
        .filter(
            dm.DocumentChangeRequest.tenant_id == workflow.tenant_id,
            dm.DocumentChangeRequest.manual_id == workflow.manual_id,
            dm.DocumentChangeRequest.status.in_(_OPEN_CHANGE_STATUSES),
        )
        .scalar()
        or 0
    )
    if open_changes:
        blockers.append(
            {
                "code": "OPEN_CHANGE_REQUESTS",
                "message": f"{int(open_changes)} unresolved change request(s) remain open.",
            }
        )

    integration_links = _module_links(db, workflow=workflow)
    blockers.extend(_refresh_links(db, tenant=tenant, links=integration_links))
    for link in integration_links:
        if link.blocking and str(link.status_snapshot or "").upper() not in _RESOLVED_LINK_STATUSES:
            blockers.append(
                {
                    "code": "INTEGRATION_BLOCKER",
                    "message": (
                        f"{link.source_module} {link.entity_type} {link.entity_id} "
                        f"is still {link.status_snapshot or 'UNVERIFIED'}."
                    ),
                }
            )

    if workflow.requires_authority:
        approved_authority = (
            db.query(dm.DocumentAuthoritySubmission)
            .filter(
                dm.DocumentAuthoritySubmission.tenant_id == workflow.tenant_id,
                dm.DocumentAuthoritySubmission.revision_id == workflow.revision_id,
                dm.DocumentAuthoritySubmission.status == "APPROVED",
            )
            .order_by(dm.DocumentAuthoritySubmission.approved_at.desc())
            .first()
        )
        if not approved_authority:
            blockers.append(
                {
                    "code": "AUTHORITY_NOT_APPROVED",
                    "message": "Authority approval is required before publication.",
                }
            )
        elif not list(approved_authority.evidence_json or []):
            blockers.append(
                {
                    "code": "AUTHORITY_EVIDENCE_MISSING",
                    "message": "The approved authority submission has no retained evidence.",
                }
            )

    profile = get_profile_by_workflow(db, workflow)
    if profile and profile.acknowledgement_required:
        campaign = (
            db.query(dm.DocumentDistributionCampaign)
            .filter(
                dm.DocumentDistributionCampaign.tenant_id == workflow.tenant_id,
                dm.DocumentDistributionCampaign.revision_id == workflow.revision_id,
                dm.DocumentDistributionCampaign.status.in_(["ISSUED", "COMPLETED"]),
            )
            .order_by(dm.DocumentDistributionCampaign.issued_at.desc())
            .first()
        )
        if not campaign:
            blockers.append(
                {
                    "code": "DISTRIBUTION_NOT_ISSUED",
                    "message": "An issued distribution campaign is required for this revision.",
                }
            )
        else:
            recipients = (
                db.query(func.count(dm.DocumentDistributionRecipient.id))
                .filter(dm.DocumentDistributionRecipient.campaign_id == campaign.id)
                .scalar()
                or 0
            )
            if recipients == 0:
                blockers.append(
                    {
                        "code": "DISTRIBUTION_HAS_NO_RECIPIENTS",
                        "message": "The issued distribution campaign has no active tenant recipients.",
                    }
                )

    return blockers


def get_profile_by_workflow(
    db: Session,
    workflow: dm.DocumentWorkflowInstance,
) -> dm.DocumentControlProfile | None:
    return (
        db.query(dm.DocumentControlProfile)
        .filter(
            dm.DocumentControlProfile.tenant_id == workflow.tenant_id,
            dm.DocumentControlProfile.manual_id == workflow.manual_id,
        )
        .first()
    )


def _dedupe_blockers(*groups: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for group in groups:
        for blocker in group:
            key = (str(blocker.get("code") or ""), str(blocker.get("message") or ""))
            if key in seen:
                continue
            seen.add(key)
            result.append(blocker)
    return result


@router.post(
    "/t/{tenant_slug}/workflows/{workflow_id}/transition",
    include_in_schema=False,
)
def transition_workflow_with_release_guards(
    tenant_slug: str,
    workflow_id: str,
    payload: schemas.WorkflowTransitionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    workflow = (
        db.query(dm.DocumentWorkflowInstance)
        .filter(
            dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id,
            dm.DocumentWorkflowInstance.id == workflow_id,
        )
        .first()
    )
    if not workflow:
        raise HTTPException(status_code=404, detail="Document workflow not found")

    require_workflow_action(
        db,
        workflow=workflow,
        user=current_user,
        action=payload.action,
    )
    if workflow.version != payload.expected_version:
        raise HTTPException(
            status_code=409,
            detail={"message": "Workflow has changed", "current_version": workflow.version, "state": workflow.state},
        )

    _validate_readiness_change(
        db,
        tenant=tenant,
        workflow=workflow,
        payload=payload,
        current_user=current_user,
    )

    if payload.effective_at is not None and not is_decision_approver(current_user):
        raise HTTPException(
            status_code=403,
            detail="Accountable document approval privileges are required to schedule effectivity",
        )

    if payload.action in {"PUBLISH", "ARCHIVE", "SCHEDULE_EFFECTIVITY"}:
        require_decision_approver(current_user)

    manual = get_manual(db, tenant, workflow.manual_id)
    revision = get_revision(db, manual, workflow.revision_id)
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
        release_blockers = _publication_blockers(db, tenant=tenant, workflow=workflow)
        state_blockers = workflow_blockers(db, workflow)
        blockers = _dedupe_blockers(release_blockers, state_blockers)
        if blockers:
            raise HTTPException(
                status_code=409,
                detail={"message": "Publication is blocked", "blockers": blockers},
            )
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
        decision=(
            "APPROVED"
            if payload.action.startswith(("APPROVE", "MARK", "PUBLISH", "SCHEDULE"))
            else "SUBMITTED"
            if payload.action.startswith(("SUBMIT", "RESUBMIT"))
            else "CORRECTIONS_REQUESTED"
            if payload.action == "REQUEST_CORRECTIONS"
            else "COMPLETED"
        ),
        actor_user_id=current_user.id,
        from_state=previous_state,
        to_state=next_state,
        comments=payload.comments,
        evidence_json=list(payload.evidence),
    )
    db.add(decision)
    audit(
        db,
        tenant,
        request,
        "document.workflow.transitioned",
        "document_workflow",
        workflow.id,
        {"action": payload.action, "from": previous_state, "to": next_state, "version": workflow.version},
    )
    db.commit()
    _event(
        event_type="doc_control.workflow_transitioned",
        entity_type="document_workflow",
        entity_id=workflow.id,
        action=payload.action.lower(),
        user=current_user,
        tenant_id=tenant.amo_id,
        metadata={"manual_id": manual.id, "revision_id": revision.id, "from": previous_state, "to": next_state},
    )
    return {**serialize_workflow(workflow), "blockers": workflow_blockers(db, workflow)}
