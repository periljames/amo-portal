from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import role_registry
from amodb.apps.manuals import models as manual_models
from amodb.apps.manuals.core_router import _tenant_by_slug
from amodb.security import get_current_actor_id

from . import domain_models


# Use only roles that exist in the authoritative AccountRole enum. AUDITOR is
# intentionally read-only and cannot mutate document governance. A future dedicated
# Document Control Officer role must be introduced through the shared RBAC/capability
# model and migration rather than accepted here as an unprovisioned string.
CONTROL_ROLES = {
    "SUPERUSER",
    "AMO_ADMIN",
    "QUALITY_MANAGER",
    "QUALITY_INSPECTOR",
}

APPROVER_ROLES = {
    "SUPERUSER",
    "AMO_ADMIN",
    "ACCOUNTABLE_EXECUTIVE",
    "QUALITY_MANAGER",
}

WORKFLOW_TRANSITIONS: dict[str, dict[str, str]] = {
    "DRAFT": {
        "SUBMIT_TECHNICAL_REVIEW": "TECHNICAL_REVIEW",
    },
    "TECHNICAL_REVIEW": {
        "APPROVE_TECHNICAL": "TECHNICAL_APPROVED",
        "REQUEST_CORRECTIONS": "CORRECTIONS_REQUIRED",
    },
    "CORRECTIONS_REQUIRED": {
        "RESUBMIT_TECHNICAL_REVIEW": "TECHNICAL_REVIEW",
    },
    "TECHNICAL_APPROVED": {
        "START_QUALITY_REVIEW": "QUALITY_REVIEW",
    },
    "QUALITY_REVIEW": {
        "APPROVE_QUALITY": "QUALITY_APPROVED",
        "REQUEST_CORRECTIONS": "CORRECTIONS_REQUIRED",
    },
    "QUALITY_APPROVED": {
        "SUBMIT_ACCOUNTABLE_MANAGER": "ACCOUNTABLE_MANAGER_APPROVAL",
    },
    "ACCOUNTABLE_MANAGER_APPROVAL": {
        "APPROVE_ACCOUNTABLE_MANAGER": "SCHEDULED_FOR_EFFECTIVITY",
        "MARK_AUTHORITY_SUBMITTED": "AUTHORITY_SUBMITTED",
        "REQUEST_CORRECTIONS": "CORRECTIONS_REQUIRED",
    },
    "AUTHORITY_SUBMITTED": {
        "MARK_AUTHORITY_APPROVED": "AUTHORITY_APPROVED",
        "REQUEST_CORRECTIONS": "CORRECTIONS_REQUIRED",
    },
    "AUTHORITY_APPROVED": {
        "SCHEDULE_EFFECTIVITY": "SCHEDULED_FOR_EFFECTIVITY",
    },
    "SCHEDULED_FOR_EFFECTIVITY": {
        "PUBLISH": "PUBLISHED",
        "REQUEST_CORRECTIONS": "CORRECTIONS_REQUIRED",
    },
    "PUBLISHED": {
        "ARCHIVE": "ARCHIVED",
    },
}


def utcnow() -> datetime:
    return datetime.utcnow()


def role_value(user: account_models.User) -> str:
    role = getattr(user, "role", None)
    return str(getattr(role, "value", role or "")).upper()


def is_control_user(user: account_models.User) -> bool:
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_amo_admin", False)
        or role_value(user) in CONTROL_ROLES
    )


def is_approver(user: account_models.User) -> bool:
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_amo_admin", False)
        or role_value(user) in APPROVER_ROLES
    )


def is_accountable_approver(user: account_models.User) -> bool:
    role = role_value(user)
    inferred = role_registry.infer_regulated_role(getattr(user, "position_title", None))
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_amo_admin", False)
        or role == account_models.AccountRole.ACCOUNTABLE_EXECUTIVE.value
        or inferred == account_models.AccountRole.ACCOUNTABLE_EXECUTIVE
    )


def require_control_user(user: account_models.User) -> None:
    if not is_control_user(user):
        raise HTTPException(status_code=403, detail="Document Control privileges required")


def require_approver(user: account_models.User, *, action: str | None = None) -> None:
    allowed = is_accountable_approver(user) if action == "APPROVE_ACCOUNTABLE_MANAGER" else is_approver(user)
    if not allowed:
        raise HTTPException(status_code=403, detail="Document approval privileges required")


def resolve_tenant(db: Session, tenant_slug: str, user: account_models.User) -> manual_models.Tenant:
    tenant = _tenant_by_slug(db, tenant_slug)
    if not getattr(user, "is_superuser", False) and str(getattr(user, "amo_id", "")) != str(tenant.amo_id):
        raise HTTPException(status_code=403, detail="The requested tenant is outside the active AMO context")
    return tenant


def get_manual(db: Session, tenant: manual_models.Tenant, manual_id: str) -> manual_models.Manual:
    manual = (
        db.query(manual_models.Manual)
        .filter(
            manual_models.Manual.id == manual_id,
            manual_models.Manual.tenant_id == tenant.id,
        )
        .first()
    )
    if not manual:
        raise HTTPException(status_code=404, detail="Document not found")
    return manual


def get_revision(
    db: Session,
    manual: manual_models.Manual,
    revision_id: str,
) -> manual_models.ManualRevision:
    revision = (
        db.query(manual_models.ManualRevision)
        .filter(
            manual_models.ManualRevision.id == revision_id,
            manual_models.ManualRevision.manual_id == manual.id,
        )
        .first()
    )
    if not revision:
        raise HTTPException(status_code=404, detail="Document revision not found")
    return revision


def latest_revision(db: Session, manual: manual_models.Manual) -> manual_models.ManualRevision | None:
    return (
        db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.manual_id == manual.id)
        .order_by(
            manual_models.ManualRevision.created_at.desc(),
            manual_models.ManualRevision.id.desc(),
        )
        .first()
    )


def get_profile(
    db: Session,
    tenant: manual_models.Tenant,
    manual_id: str,
) -> domain_models.DocumentControlProfile | None:
    return (
        db.query(domain_models.DocumentControlProfile)
        .filter(
            domain_models.DocumentControlProfile.tenant_id == tenant.amo_id,
            domain_models.DocumentControlProfile.manual_id == manual_id,
        )
        .first()
    )


def profile_defaults(manual: manual_models.Manual) -> dict[str, Any]:
    return {
        "id": None,
        "manual_id": manual.id,
        "document_class": "INTERNAL",
        "owner_department": manual.owner_role or "DOCUMENT_CONTROL",
        "owner_user_id": None,
        "language": "en",
        "criticality": "STANDARD",
        "regulated_flag": False,
        "restricted_flag": False,
        "requires_authority_approval": False,
        "acknowledgement_required": False,
        "review_interval_months": 24,
        "next_review_due": None,
        "access_scope": {},
        "tags": [],
        "metadata": {},
        "version": 0,
    }


def serialize_profile(
    profile: domain_models.DocumentControlProfile | None,
    manual: manual_models.Manual,
) -> dict[str, Any]:
    if not profile:
        return profile_defaults(manual)
    return {
        "id": profile.id,
        "manual_id": profile.manual_id,
        "document_class": profile.document_class,
        "owner_department": profile.owner_department,
        "owner_user_id": profile.owner_user_id,
        "language": profile.language,
        "criticality": profile.criticality,
        "regulated_flag": profile.regulated_flag,
        "restricted_flag": profile.restricted_flag,
        "requires_authority_approval": profile.requires_authority_approval,
        "acknowledgement_required": profile.acknowledgement_required,
        "review_interval_months": profile.review_interval_months,
        "next_review_due": profile.next_review_due.isoformat() if profile.next_review_due else None,
        "access_scope": dict(profile.access_scope_json or {}),
        "tags": list(profile.tags_json or []),
        "metadata": dict(profile.metadata_json or {}),
        "version": profile.version,
    }


def can_read_manual(
    user: account_models.User,
    profile: domain_models.DocumentControlProfile | None,
) -> bool:
    if not profile or not profile.restricted_flag:
        return True
    if is_control_user(user):
        return True
    scope = dict(profile.access_scope_json or {})
    allowed_user_ids = {str(value) for value in scope.get("user_ids", [])}
    allowed_roles = {str(value).upper() for value in scope.get("roles", [])}
    allowed_departments = {str(value).upper() for value in scope.get("departments", [])}
    department = getattr(getattr(user, "department", None), "code", None)
    return bool(
        str(user.id) in allowed_user_ids
        or role_value(user) in allowed_roles
        or (department and str(department).upper() in allowed_departments)
    )


def require_manual_access(
    user: account_models.User,
    profile: domain_models.DocumentControlProfile | None,
) -> None:
    if not can_read_manual(user, profile):
        raise HTTPException(status_code=403, detail="This document is restricted")


def readable_revision(
    db: Session,
    manual: manual_models.Manual,
    user: account_models.User,
) -> tuple[manual_models.ManualRevision | None, str]:
    if manual.current_published_rev_id:
        published = (
            db.query(manual_models.ManualRevision)
            .filter(
                manual_models.ManualRevision.id == manual.current_published_rev_id,
                manual_models.ManualRevision.manual_id == manual.id,
                manual_models.ManualRevision.status_enum == manual_models.ManualRevisionStatus.PUBLISHED,
            )
            .first()
        )
        if published:
            return published, "PUBLISHED"
    if is_control_user(user):
        draft = latest_revision(db, manual)
        if draft:
            return draft, "UNCONTROLLED"
    return None, "NONE"


def source_type_value(revision: manual_models.ManualRevision) -> str | None:
    value = getattr(revision, "source_type", None)
    return str(getattr(value, "value", value)) if value is not None else None


def status_value(revision: manual_models.ManualRevision) -> str:
    value = revision.status_enum
    return str(getattr(value, "value", value))


def serialize_revision(revision: manual_models.ManualRevision | None) -> dict[str, Any] | None:
    if not revision:
        return None
    return {
        "id": revision.id,
        "manual_id": revision.manual_id,
        "issue_number": revision.issue_number,
        "revision_number": revision.rev_number,
        "status": status_value(revision),
        "effective_date": revision.effective_date.isoformat() if revision.effective_date else None,
        "created_at": revision.created_at.isoformat() if revision.created_at else None,
        "published_at": revision.published_at.isoformat() if revision.published_at else None,
        "immutable": bool(revision.immutable_locked),
        "source_type": source_type_value(revision),
        "source_filename": revision.source_filename,
        "source_page_count": revision.source_page_count,
        "source_sha256": revision.source_sha256,
        "requires_authority_approval": bool(revision.requires_authority_approval_bool),
        "authority_approval_ref": revision.authority_approval_ref,
    }


def serialize_manual(
    manual: manual_models.Manual,
    profile: domain_models.DocumentControlProfile | None,
    target_revision: manual_models.ManualRevision | None,
    target_kind: str,
    latest: manual_models.ManualRevision | None,
) -> dict[str, Any]:
    return {
        "id": manual.id,
        "code": manual.code,
        "title": manual.title,
        "manual_type": manual.manual_type,
        "owner_role": manual.owner_role,
        "status": manual.status,
        "current_published_revision_id": manual.current_published_rev_id,
        "profile": serialize_profile(profile, manual),
        "latest_revision": serialize_revision(latest),
        "read_target": {
            "revision_id": target_revision.id if target_revision else None,
            "kind": target_kind,
            "label": (
                "Read current issue"
                if target_kind == "PUBLISHED"
                else "Read uncontrolled draft"
                if target_kind == "UNCONTROLLED"
                else "No readable revision"
            ),
            "uncontrolled": target_kind == "UNCONTROLLED",
        },
    }


def get_workflow(
    db: Session,
    tenant: manual_models.Tenant,
    revision_id: str,
) -> domain_models.DocumentWorkflowInstance | None:
    return (
        db.query(domain_models.DocumentWorkflowInstance)
        .filter(
            domain_models.DocumentWorkflowInstance.tenant_id == tenant.amo_id,
            domain_models.DocumentWorkflowInstance.revision_id == revision_id,
        )
        .first()
    )


def serialize_workflow(workflow: domain_models.DocumentWorkflowInstance) -> dict[str, Any]:
    return {
        "id": workflow.id,
        "manual_id": workflow.manual_id,
        "revision_id": workflow.revision_id,
        "state": workflow.state,
        "requires_authority": workflow.requires_authority,
        "training_impact_required": workflow.training_impact_required,
        "training_readiness_status": workflow.training_readiness_status,
        "qms_readiness_status": workflow.qms_readiness_status,
        "distribution_readiness_status": workflow.distribution_readiness_status,
        "effective_at": workflow.effective_at.isoformat() if workflow.effective_at else None,
        "version": workflow.version,
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
    }


def workflow_blockers(
    db: Session,
    workflow: domain_models.DocumentWorkflowInstance,
) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    if workflow.training_impact_required and workflow.training_readiness_status not in {"READY", "WAIVED"}:
        blockers.append({"code": "TRAINING_NOT_READY", "message": "Training impact is not ready or waived."})
    if workflow.qms_readiness_status not in {"NOT_REQUIRED", "READY", "WAIVED"}:
        blockers.append({"code": "QMS_BLOCKED", "message": "A linked QMS item is not resolved."})
    if workflow.distribution_readiness_status not in {"NOT_REQUIRED", "READY", "WAIVED"}:
        blockers.append({"code": "DISTRIBUTION_NOT_READY", "message": "Distribution readiness has not been confirmed."})
    if workflow.requires_authority:
        approved = (
            db.query(domain_models.DocumentAuthoritySubmission)
            .filter(
                domain_models.DocumentAuthoritySubmission.tenant_id == workflow.tenant_id,
                domain_models.DocumentAuthoritySubmission.revision_id == workflow.revision_id,
                domain_models.DocumentAuthoritySubmission.status == "APPROVED",
            )
            .first()
        )
        if not approved:
            blockers.append({"code": "AUTHORITY_NOT_APPROVED", "message": "Authority approval is required before publication."})
    linked_blocker = (
        db.query(domain_models.DocumentIntegrationLink)
        .filter(
            domain_models.DocumentIntegrationLink.tenant_id == workflow.tenant_id,
            domain_models.DocumentIntegrationLink.workflow_id == workflow.id,
            domain_models.DocumentIntegrationLink.blocking.is_(True),
            domain_models.DocumentIntegrationLink.status_snapshot.notin_(["CLOSED", "RESOLVED", "READY", "COMPLETED"]),
        )
        .first()
    )
    if linked_blocker:
        blockers.append({"code": "INTEGRATION_BLOCKER", "message": "A linked module item is still blocking publication."})
    return blockers


def next_workflow_state(
    workflow: domain_models.DocumentWorkflowInstance,
    action: str,
) -> str:
    allowed = WORKFLOW_TRANSITIONS.get(workflow.state, {})
    next_state = allowed.get(action)
    if not next_state:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Action {action} is not valid from {workflow.state}",
                "state": workflow.state,
                "allowed_actions": sorted(allowed),
            },
        )
    if workflow.requires_authority and workflow.state == "ACCOUNTABLE_MANAGER_APPROVAL" and action == "APPROVE_ACCOUNTABLE_MANAGER":
        raise HTTPException(status_code=409, detail="Authority submission is required for this revision")
    if not workflow.requires_authority and action == "MARK_AUTHORITY_SUBMITTED":
        raise HTTPException(status_code=409, detail="This revision does not require authority approval")
    return next_state


def sync_revision_status(
    revision: manual_models.ManualRevision,
    workflow_state: str,
) -> None:
    if workflow_state in {"DRAFT", "CORRECTIONS_REQUIRED"}:
        revision.status_enum = manual_models.ManualRevisionStatus.DRAFT
        revision.immutable_locked = False
    elif workflow_state in {"TECHNICAL_REVIEW", "TECHNICAL_APPROVED"}:
        revision.status_enum = manual_models.ManualRevisionStatus.DEPARTMENT_REVIEW
    elif workflow_state in {"QUALITY_REVIEW", "QUALITY_APPROVED", "ACCOUNTABLE_MANAGER_APPROVAL"}:
        revision.status_enum = manual_models.ManualRevisionStatus.QUALITY_APPROVAL
    elif workflow_state in {"AUTHORITY_SUBMITTED", "AUTHORITY_APPROVED", "SCHEDULED_FOR_EFFECTIVITY"}:
        revision.status_enum = manual_models.ManualRevisionStatus.REGULATOR_SIGNOFF
    elif workflow_state == "PUBLISHED":
        revision.status_enum = manual_models.ManualRevisionStatus.PUBLISHED
        revision.immutable_locked = True
        revision.published_at = utcnow()
    elif workflow_state == "ARCHIVED":
        revision.status_enum = manual_models.ManualRevisionStatus.ARCHIVED
        revision.immutable_locked = True


def publish_revision(
    db: Session,
    tenant: manual_models.Tenant,
    manual: manual_models.Manual,
    revision: manual_models.ManualRevision,
) -> None:
    previous = None
    if manual.current_published_rev_id and manual.current_published_rev_id != revision.id:
        previous = (
            db.query(manual_models.ManualRevision)
            .filter(manual_models.ManualRevision.id == manual.current_published_rev_id)
            .first()
        )
    if previous:
        previous.status_enum = manual_models.ManualRevisionStatus.SUPERSEDED
        previous.immutable_locked = True
        previous.superseded_by_rev_id = revision.id
    sync_revision_status(revision, "PUBLISHED")
    manual.current_published_rev_id = revision.id
    manual.status = "ACTIVE"
    db.add(
        manual_models.ManualAIHookEvent(
            tenant_id=tenant.id,
            revision_id=revision.id,
            event_name="revision.published",
            payload_json={"manual_id": manual.id, "source": "document-control-workflow"},
        )
    )


def audit(
    db: Session,
    tenant: manual_models.Tenant,
    request: Request,
    action: str,
    entity_type: str,
    entity_id: str,
    diff: dict[str, Any] | None = None,
) -> None:
    actor_id = get_current_actor_id()
    ip_device = f"{request.client.host if request.client else 'unknown'}::{request.headers.get('user-agent', 'n/a')}"
    db.add(
        manual_models.ManualAuditLog(
            tenant_id=tenant.id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            ip_device=ip_device,
            diff_json=diff or {},
        )
    )


def active_tenant_users(
    db: Session,
    tenant: manual_models.Tenant,
    user_ids: list[str],
) -> list[account_models.User]:
    if not user_ids:
        return []
    unique_ids = list(dict.fromkeys(str(item) for item in user_ids if item))
    users = (
        db.query(account_models.User)
        .filter(
            account_models.User.amo_id == tenant.amo_id,
            account_models.User.id.in_(unique_ids),
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .all()
    )
    found = {user.id for user in users}
    missing = [user_id for user_id in unique_ids if user_id not in found]
    if missing:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "One or more recipients are inactive, system, missing, or outside the tenant",
                "invalid_user_ids": missing,
            },
        )
    return users
