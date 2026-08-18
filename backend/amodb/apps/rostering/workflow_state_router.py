from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import common, models, services
from .consent_models import RosterAssignmentConsent, RosterConsentStatus, RosterSupervisorDecision
from .extended_duty_models import RosterDutyExtension, RosterDutyExtensionStatus

router = APIRouter(prefix="/rostering", tags=["rostering-workflow"])


class WorkflowGateRead(BaseModel):
    severity: Literal["HARD_BLOCK", "CONDITIONAL_BLOCK", "WARNING"]
    code: str
    message: str
    assignment_id: str | None = None
    personnel_id: str | None = None
    rule_id: str | None = None
    consent_id: str | None = None
    extension_id: str | None = None
    details: dict = Field(default_factory=dict)
    remediation_actions: list[str] = Field(default_factory=list)


class WorkflowGateResponse(BaseModel):
    version_id: str
    workflow_state: str
    hard_block_count: int
    conditional_block_count: int
    warning_count: int
    can_submit: bool
    can_approve: bool
    can_publish: bool
    gates: list[WorkflowGateRead]


def _amo(user: account_models.User) -> str:
    return common.effective_amo_id(user)


def _finding_gate(row: models.RosterValidationFinding) -> WorkflowGateRead | None:
    if row.resolved or row.severity == models.RosterValidationSeverity.INFO:
        return None
    details = dict(row.details_json or {})
    actions = list(details.get("remediation_actions") or [])
    severity: Literal["HARD_BLOCK", "WARNING"] = (
        "HARD_BLOCK"
        if row.severity == models.RosterValidationSeverity.BLOCKER
        else "WARNING"
    )
    return WorkflowGateRead(
        severity=severity,
        code=row.code,
        message=row.message,
        assignment_id=row.assignment_id,
        personnel_id=row.user_id,
        rule_id=row.rule_id,
        details=details,
        remediation_actions=actions,
    )


def _consent_gates(row: RosterAssignmentConsent) -> list[WorkflowGateRead]:
    if row.personnel_response == RosterConsentStatus.INVALIDATED:
        return []
    base = {
        "assignment_id": row.assignment_id,
        "personnel_id": row.personnel_id,
        "consent_id": row.id,
        "details": {
            "assignment_revision": row.assignment_revision,
            "assignment_fingerprint": row.assignment_fingerprint,
            "planned_start": row.planned_start.isoformat(),
            "planned_end": row.planned_end.isoformat(),
            "duty_type": row.duty_type,
            "reason": row.reason,
        },
    }
    if row.personnel_response == RosterConsentStatus.PENDING:
        return [WorkflowGateRead(
            severity="CONDITIONAL_BLOCK",
            code="ROSTER_CONSENT_REQUIRED",
            message="Personnel acknowledgement is required before this roster can proceed.",
            remediation_actions=["REQUEST_PERSONNEL_ACKNOWLEDGEMENT", "REASSIGN_DUTY", "CHANGE_SHIFT"],
            **base,
        )]
    if row.personnel_response == RosterConsentStatus.DECLINED:
        return [WorkflowGateRead(
            severity="CONDITIONAL_BLOCK",
            code="ROSTER_CONSENT_DECLINED",
            message="The employee declined this proposed assignment. Reassign or amend the roster.",
            remediation_actions=["REASSIGN_DUTY", "CHANGE_SHIFT", "REMOVE_ASSIGNMENT"],
            **base,
        )]
    if row.supervisor_required and row.supervisor_decision == RosterSupervisorDecision.PENDING:
        return [WorkflowGateRead(
            severity="CONDITIONAL_BLOCK",
            code="ROSTER_SUPERVISOR_APPROVAL_REQUIRED",
            message="Scoped supervisor approval is required before this roster can proceed.",
            remediation_actions=["REQUEST_SUPERVISOR_APPROVAL"],
            **base,
        )]
    if row.supervisor_required and row.supervisor_decision == RosterSupervisorDecision.REJECTED:
        return [WorkflowGateRead(
            severity="CONDITIONAL_BLOCK",
            code="ROSTER_SUPERVISOR_REJECTED",
            message="The responsible supervisor rejected this assignment. Reassign or amend the roster.",
            remediation_actions=["REASSIGN_DUTY", "CHANGE_SHIFT", "REMOVE_ASSIGNMENT"],
            **base,
        )]
    return []


def _extension_gate(row: RosterDutyExtension) -> WorkflowGateRead | None:
    if row.status in {RosterDutyExtensionStatus.READY, RosterDutyExtensionStatus.CANCELLED}:
        return None
    code = {
        RosterDutyExtensionStatus.AWAITING_PERSONNEL_ACKNOWLEDGEMENT: "ROSTER_CONSENT_REQUIRED",
        RosterDutyExtensionStatus.AWAITING_SUPERVISOR_APPROVAL: "ROSTER_SUPERVISOR_APPROVAL_REQUIRED",
        RosterDutyExtensionStatus.COMPLIANCE_BLOCKED: "ROSTER_DUTY_EXTENSION_COMPLIANCE_BLOCKED",
    }.get(row.status, "ROSTER_DUTY_EXTENSION_INCOMPLETE")
    return WorkflowGateRead(
        severity="CONDITIONAL_BLOCK",
        code=code,
        message="The controlled unscheduled-unserviceability duty extension is not ready.",
        assignment_id=row.assignment_id,
        extension_id=row.id,
        details={
            "extension_type": str(getattr(row.extension_type, "value", row.extension_type)),
            "aircraft_registration": row.aircraft_registration,
            "operational_reference": row.operational_reference,
            "work_order_reference": row.work_order_reference,
            "proposed_extended_end": row.proposed_extended_end.isoformat(),
            "continuous_duty_minutes": row.continuous_duty_minutes,
            "required_recovery_rest_minutes": row.required_recovery_rest_minutes,
            "status": str(getattr(row.status, "value", row.status)),
        },
        remediation_actions=["COMPLETE_EXTENSION_WORKFLOW", "AMEND_DUTY", "ASSIGN_RECOVERY_REST"],
    )


@router.get("/versions/{version_id}/workflow-gates", response_model=WorkflowGateResponse)
def version_workflow_gates(
    version_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not services.can_view_roster(db, user=current_user):
        raise HTTPException(status_code=403, detail={"code": "ROSTER_ACCESS_DENIED"})
    amo_id = _amo(current_user)
    version = common.get_version(db, amo_id=amo_id, version_id=version_id)
    if version is None:
        raise HTTPException(status_code=404, detail={"code": "ROSTER_VERSION_NOT_FOUND"})

    gates = [gate for row in (version.validation_findings or []) if (gate := _finding_gate(row)) is not None]
    consents = db.query(RosterAssignmentConsent).filter(
        RosterAssignmentConsent.amo_id == amo_id,
        RosterAssignmentConsent.version_id == version_id,
    ).order_by(RosterAssignmentConsent.created_at.asc()).all()
    for consent in consents:
        gates.extend(_consent_gates(consent))
    extensions = db.query(RosterDutyExtension).filter(
        RosterDutyExtension.amo_id == amo_id,
        RosterDutyExtension.version_id == version_id,
    ).order_by(RosterDutyExtension.created_at.asc()).all()
    for extension in extensions:
        gate = _extension_gate(extension)
        if gate is not None:
            gates.append(gate)

    hard = sum(1 for gate in gates if gate.severity == "HARD_BLOCK")
    conditional = sum(1 for gate in gates if gate.severity == "CONDITIONAL_BLOCK")
    warnings = sum(1 for gate in gates if gate.severity == "WARNING")
    if hard:
        state = "STATUTORY_BLOCKED"
    elif conditional:
        state = "AWAITING_WORKFLOW_ACTION"
    elif warnings:
        state = "READY_WITH_WARNINGS"
    else:
        state = "READY"
    clear = hard == 0 and conditional == 0
    return WorkflowGateResponse(
        version_id=version_id,
        workflow_state=state,
        hard_block_count=hard,
        conditional_block_count=conditional,
        warning_count=warnings,
        can_submit=clear and version.status == models.RosterVersionStatus.DRAFT,
        can_approve=clear and version.status == models.RosterVersionStatus.SUBMITTED,
        can_publish=clear and version.status == models.RosterVersionStatus.APPROVED,
        gates=gates,
    )


__all__ = ["router"]
