from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import domain_models as dm
from . import governance_models as gm
from amodb.apps.accounts.tenant_authority import is_tenant_admin
from .workspace_service import WORKFLOW_TRANSITIONS, is_accountable_approver, is_control_user, role_assignment_tokens


# A workflow decision is not authorized merely because a button is visible. These
# responsibility types are the governed document assignments that may perform the
# corresponding controlled decision. Accountable management roles remain a secure
# fallback for operational continuity and publication governance.
_ACTION_RESPONSIBILITIES: dict[str, tuple[str, ...]] = {
    "APPROVE_TECHNICAL": ("TECHNICAL_REVIEWER", "DOCUMENT_OWNER"),
    "APPROVE_QUALITY": ("QUALITY_REVIEWER",),
}

_TECHNICAL_OWNER_ROLES = {"BASE_MAINTENANCE_MANAGER", "LINE_MAINTENANCE_MANAGER", "WORKSHOP_MANAGER", "SAFETY_MANAGER"}


def _assignment_target_filter(db: Session, user: account_models.User):
    clauses = [gm.DocumentResponsibilityAssignment.assignee_user_id == str(user.id)]
    department_id = getattr(user, "department_id", None)
    if department_id:
        clauses.append(gm.DocumentResponsibilityAssignment.assignee_department_id == str(department_id))
    role_tokens = role_assignment_tokens(db, user)
    if role_tokens:
        clauses.append(gm.DocumentResponsibilityAssignment.assignee_role.in_(role_tokens))
    return or_(*clauses)


def has_confirmed_responsibility(
    db: Session,
    *,
    workflow: dm.DocumentWorkflowInstance,
    user: account_models.User,
    responsibility_types: tuple[str, ...],
) -> bool:
    """Return whether the user holds an effective confirmed governed assignment.

    Inferred, unresolved or superseded responsibility may be displayed for a
    controller to resolve, but it must never grant a workflow decision privilege.
    A manual-level assignment applies to every revision; a revision-level
    assignment applies only to that exact candidate revision.
    """
    if not responsibility_types:
        return False
    today = date.today()
    return bool(
        db.query(gm.DocumentResponsibilityAssignment.id)
        .filter(
            gm.DocumentResponsibilityAssignment.tenant_id == workflow.tenant_id,
            gm.DocumentResponsibilityAssignment.manual_id == workflow.manual_id,
            or_(
                gm.DocumentResponsibilityAssignment.revision_id.is_(None),
                gm.DocumentResponsibilityAssignment.revision_id == workflow.revision_id,
            ),
            gm.DocumentResponsibilityAssignment.responsibility_type.in_(responsibility_types),
            gm.DocumentResponsibilityAssignment.confirmation_status == "CONFIRMED",
            gm.DocumentResponsibilityAssignment.superseded_by_id.is_(None),
            gm.DocumentResponsibilityAssignment.effective_from <= today,
            or_(
                gm.DocumentResponsibilityAssignment.effective_to.is_(None),
                gm.DocumentResponsibilityAssignment.effective_to >= today,
            ),
            _assignment_target_filter(db, user),
        )
        .limit(1)
        .first()
    )


def _corrections_responsibility(workflow: dm.DocumentWorkflowInstance) -> tuple[str, ...]:
    if workflow.state == "TECHNICAL_REVIEW":
        return ("TECHNICAL_REVIEWER",)
    if workflow.state == "QUALITY_REVIEW":
        return ("QUALITY_REVIEWER",)
    if workflow.state == "ACCOUNTABLE_MANAGER_APPROVAL":
        return ("APPROVER",)
    return ()


def can_perform_workflow_action(
    db: Session,
    *,
    workflow: dm.DocumentWorkflowInstance,
    user: account_models.User,
    action: str,
) -> bool:
    valid_actions = WORKFLOW_TRANSITIONS.get(str(workflow.state or ""), {})
    if action not in valid_actions:
        return False

    if action in {"PUBLISH", "ARCHIVE", "SCHEDULE_EFFECTIVITY"}:
        return is_control_user(user)

    if action == "REQUEST_CORRECTIONS":
        responsibility_types = _corrections_responsibility(workflow)
        role = str(getattr(getattr(user, "role", None), "value", getattr(user, "role", ""))).upper()
        if is_tenant_admin(user):
            return True
        if workflow.state == "QUALITY_REVIEW" and role == "QUALITY_MANAGER":
            return True
        if workflow.state == "ACCOUNTABLE_MANAGER_APPROVAL" and is_accountable_approver(user):
            return True
        if workflow.state == "TECHNICAL_REVIEW" and role in _TECHNICAL_OWNER_ROLES:
            # A post-holder title is not authority over every controlled document.
            # Baseline technical authority is bounded to documents for which that
            # post holder is the confirmed owner; a separately delegated technical
            # reviewer remains valid through the governed assignment below.
            if has_confirmed_responsibility(
                db,
                workflow=workflow,
                user=user,
                responsibility_types=("DOCUMENT_OWNER",),
            ):
                return True
        return has_confirmed_responsibility(
            db,
            workflow=workflow,
            user=user,
            responsibility_types=responsibility_types,
        )

    if action == "APPROVE_ACCOUNTABLE_MANAGER":
        # Final accountable approval belongs to the AE (or tenant admin override).
        # A generic assignment must not manufacture delegated final accountability.
        return is_accountable_approver(user)

    responsibility_types = _ACTION_RESPONSIBILITIES.get(action)
    if responsibility_types:
        role = str(getattr(getattr(user, "role", None), "value", getattr(user, "role", ""))).upper()
        if is_tenant_admin(user):
            return True
        if action == "APPROVE_QUALITY" and role == "QUALITY_MANAGER":
            return True
        if action == "APPROVE_TECHNICAL" and role in _TECHNICAL_OWNER_ROLES:
            if has_confirmed_responsibility(
                db,
                workflow=workflow,
                user=user,
                responsibility_types=("DOCUMENT_OWNER",),
            ):
                return True
        return has_confirmed_responsibility(
            db,
            workflow=workflow,
            user=user,
            responsibility_types=responsibility_types,
        )

    # Starting/submitting/handoff and authority-recording transitions remain
    # controller operations. This prevents a reviewer assignment from silently
    # acquiring publication, distribution or configuration powers.
    return is_control_user(user)


def require_workflow_action(
    db: Session,
    *,
    workflow: dm.DocumentWorkflowInstance,
    user: account_models.User,
    action: str,
) -> None:
    if not can_perform_workflow_action(db, workflow=workflow, user=user, action=action):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "DOCUMENT_WORKFLOW_ACTION_FORBIDDEN",
                "message": "The current user is not authorized for this document workflow decision.",
                "action": action,
                "state": workflow.state,
            },
        )


def workflow_actions_for_user(
    db: Session,
    *,
    workflow: dm.DocumentWorkflowInstance,
    user: account_models.User,
) -> list[str]:
    return [
        action
        for action in WORKFLOW_TRANSITIONS.get(str(workflow.state or ""), {})
        if can_perform_workflow_action(db, workflow=workflow, user=user, action=action)
    ]
