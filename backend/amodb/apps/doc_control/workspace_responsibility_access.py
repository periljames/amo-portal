from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import domain_models as dm
from . import governance_models as gm
from .workspace_decision_policy import is_decision_approver
from .workspace_service import WORKFLOW_TRANSITIONS, is_control_user, role_value


# A workflow decision is not authorized merely because a button is visible. These
# responsibility types are the governed document assignments that may perform the
# corresponding controlled decision. Accountable management roles remain a secure
# fallback for operational continuity and publication governance.
_ACTION_RESPONSIBILITIES: dict[str, tuple[str, ...]] = {
    "APPROVE_TECHNICAL": ("TECHNICAL_REVIEWER",),
    "APPROVE_QUALITY": ("QUALITY_REVIEWER",),
    "APPROVE_ACCOUNTABLE_MANAGER": ("APPROVER",),
}


def _assignment_target_filter(user: account_models.User):
    clauses = [gm.DocumentResponsibilityAssignment.assignee_user_id == str(user.id)]
    department_id = getattr(user, "department_id", None)
    if department_id:
        clauses.append(gm.DocumentResponsibilityAssignment.assignee_department_id == str(department_id))
    role = role_value(user)
    if role:
        clauses.append(gm.DocumentResponsibilityAssignment.assignee_role == role)
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
            _assignment_target_filter(user),
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
        return is_decision_approver(user)

    if action == "REQUEST_CORRECTIONS":
        responsibility_types = _corrections_responsibility(workflow)
        return bool(
            is_decision_approver(user)
            or is_control_user(user)
            or has_confirmed_responsibility(
                db,
                workflow=workflow,
                user=user,
                responsibility_types=responsibility_types,
            )
        )

    responsibility_types = _ACTION_RESPONSIBILITIES.get(action)
    if responsibility_types:
        return bool(
            is_decision_approver(user)
            or has_confirmed_responsibility(
                db,
                workflow=workflow,
                user=user,
                responsibility_types=responsibility_types,
            )
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
