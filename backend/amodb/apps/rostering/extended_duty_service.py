from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from . import common, consent_service, models, validation
from .consent_models import (
    RosterAssignmentConsent,
    RosterConsentStatus,
    RosterSupervisorDecision,
)
from .extended_duty_models import (
    RosterDutyExtension,
    RosterDutyExtensionStatus,
    RosterDutyExtensionType,
)

UTC = timezone.utc


def _rule_parameters(row: models.RosterRule | None) -> dict[str, Any]:
    return dict(getattr(row, "parameters_json", None) or {})


def _extension_rules(db: Session, assignment: models.RosterAssignment):
    version = assignment.version
    rules = validation.active_rules(
        db,
        amo_id=assignment.amo_id,
        on_date=version.period.starts_on,
    )
    duration_rule = validation.find_rule(
        rules,
        models.RosterRuleType.MAX_ASSIGNMENT_DURATION,
        assignment,
    )
    recovery_rule = validation.find_rule(
        rules,
        models.RosterRuleType.MIN_REST_HOURS,
        assignment,
    )
    return rules, duration_rule, recovery_rule


def _force_consent(
    db: Session,
    *,
    assignment: models.RosterAssignment,
    actor_user_id: str,
    reason: str,
    required_recovery_minutes: int,
    continuous_duty_minutes: int,
) -> RosterAssignmentConsent:
    fingerprint = consent_service.assignment_fingerprint(assignment)
    for old in consent_service._active_requests(
        db,
        amo_id=assignment.amo_id,
        assignment_id=assignment.id,
    ):
        if old.assignment_fingerprint == fingerprint and old.duty_type == "EXTENDED_MAINTENANCE_DUTY":
            return old
        consent_service._invalidate(
            db,
            old,
            actor_user_id=actor_user_id,
            reason="UNSCHEDULED_DUTY_EXTENSION",
        )

    personnel = common.require_user(
        db,
        amo_id=assignment.amo_id,
        user_id=assignment.user_id,
        active_only=True,
    )
    request = RosterAssignmentConsent(
        amo_id=assignment.amo_id,
        version_id=assignment.version_id,
        assignment_id=assignment.id,
        assignment_revision=max(int(assignment.state_revision or 1), 1),
        assignment_fingerprint=fingerprint,
        personnel_id=assignment.user_id,
        proposed_by_user_id=actor_user_id,
        reason=reason,
        duty_type="EXTENDED_MAINTENANCE_DUTY",
        planned_start=assignment.starts_at,
        planned_end=assignment.ends_at,
        personnel_response=RosterConsentStatus.PENDING,
        supervisor_required=True,
        supervisor_decision=RosterSupervisorDecision.PENDING,
        replacement_rest_json={"required_recovery_rest_minutes": required_recovery_minutes},
        fatigue_risk_json={"continuous_duty_minutes": continuous_duty_minutes},
    )
    db.add(request)
    db.flush()
    common.audit(
        db,
        amo_id=assignment.amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterAssignmentConsent",
        entity_id=request.id,
        action="roster_consent_requested",
        after={
            "assignment_id": assignment.id,
            "assignment_revision": request.assignment_revision,
            "assignment_fingerprint": fingerprint,
            "duty_type": request.duty_type,
            "supervisor_required": True,
        },
        metadata={"version_id": assignment.version_id, "extension_controlled": True},
        critical=True,
    )
    common.notify_email(
        db,
        amo_id=assignment.amo_id,
        recipient=getattr(personnel, "email", None),
        template_key="roster_consent_requested",
        subject="Extended maintenance duty acknowledgement required",
        context={
            "assignment_id": assignment.id,
            "consent_id": request.id,
            "starts_at": assignment.starts_at.isoformat(),
            "ends_at": assignment.ends_at.isoformat(),
            "reason": reason,
            "required_recovery_rest_minutes": required_recovery_minutes,
        },
        correlation_id=f"roster-extension-consent:{request.id}:{fingerprint}",
    )
    return request


def propose_extension(
    db: Session,
    *,
    amo_id: str,
    assignment_id: str,
    actor_user_id: str,
    proposed_extended_end: datetime,
    aircraft_registration: str,
    operational_reference: str,
    reason: str,
    work_order_reference: str | None = None,
) -> RosterDutyExtension:
    assignment = common.get_assignment(
        db,
        amo_id=amo_id,
        assignment_id=assignment_id,
        lock=True,
    )
    if assignment is None:
        raise consent_service.RosterWorkflowError(
            "ROSTER_ASSIGNMENT_NOT_FOUND",
            "Roster assignment was not found in this tenant.",
            {"assignment_id": assignment_id},
        )
    common.ensure_draft(assignment.version)
    if not proposed_extended_end.tzinfo:
        proposed_extended_end = proposed_extended_end.replace(tzinfo=UTC)
    if proposed_extended_end <= assignment.ends_at:
        raise consent_service.RosterWorkflowError(
            "ROSTER_DUTY_EXTENSION_INVALID",
            "Proposed extended end must be later than the current planned end.",
            {"assignment_id": assignment_id},
        )
    if not aircraft_registration.strip() or not operational_reference.strip() or not reason.strip():
        raise consent_service.RosterWorkflowError(
            "ROSTER_DUTY_EXTENSION_EVIDENCE_REQUIRED",
            "Aircraft registration, AOG/defect reference and reason are required.",
            {"assignment_id": assignment_id},
        )

    rules, duration_rule, recovery_rule = _extension_rules(db, assignment)
    duration_parameters = _rule_parameters(duration_rule)
    if not duration_rule or duration_parameters.get("allow_unscheduled_unserviceability_extension") is not True:
        raise consent_service.RosterWorkflowError(
            "ROSTER_DUTY_EXTENSION_NOT_PERMITTED",
            "The active roster rule set does not permit an unscheduled-aircraft duty extension for this assignment.",
            {"assignment_id": assignment_id, "rule_id": getattr(duration_rule, "id", None)},
        )
    extended_maximum = int(duration_parameters.get("extended_maximum_minutes") or 0)
    continuous = int((proposed_extended_end - assignment.starts_at).total_seconds() // 60)
    if not extended_maximum or continuous > extended_maximum:
        raise consent_service.RosterWorkflowError(
            "ROSTER_DUTY_LIMIT_EXCEEDED",
            "The proposed extension exceeds the configured extended-duty limit.",
            {
                "assignment_id": assignment_id,
                "continuous_duty_minutes": continuous,
                "extended_maximum_minutes": extended_maximum,
                "rule_code": getattr(duration_rule, "code", None),
            },
        )
    recovery_parameters = _rule_parameters(recovery_rule)
    ordinary_recovery = int(recovery_parameters.get("minimum_minutes") or 0)
    extension_recovery = int(duration_parameters.get("extended_recovery_minutes") or 0)
    required_recovery = max(ordinary_recovery, extension_recovery)
    if required_recovery <= 0:
        raise consent_service.RosterWorkflowError(
            "ROSTER_RECOVERY_REST_RULE_REQUIRED",
            "The active rule set must define recovery rest before extended maintenance duty can be proposed.",
            {"assignment_id": assignment_id},
        )

    original_end = assignment.ends_at
    before = {
        "ends_at": original_end.isoformat(),
        "planned_minutes": assignment.planned_minutes,
        "state_revision": assignment.state_revision,
    }
    assignment.ends_at = proposed_extended_end
    assignment.planned_minutes = continuous
    assignment.change_reason = reason.strip()
    assignment.updated_by_user_id = actor_user_id
    assignment.state_revision = int(assignment.state_revision or 1) + 1
    common.bump_version(assignment.version)
    db.add(assignment)
    db.flush()

    request = _force_consent(
        db,
        assignment=assignment,
        actor_user_id=actor_user_id,
        reason=reason.strip(),
        required_recovery_minutes=required_recovery,
        continuous_duty_minutes=continuous,
    )
    result = validation.run_validation(
        db,
        version=assignment.version,
        actor_user_id=actor_user_id,
    )
    snapshot = {
        "blocker_count": result.blocker_count,
        "warning_count": result.warning_count,
        "validation_fingerprint": result.validation_fingerprint,
        "finding_codes": [item.code for item in result.findings if not item.resolved],
    }
    request.statutory_compliance_json = snapshot
    db.add(request)

    row = RosterDutyExtension(
        amo_id=amo_id,
        version_id=assignment.version_id,
        assignment_id=assignment.id,
        consent_id=request.id,
        extension_type=RosterDutyExtensionType.UNSCHEDULED_AIRCRAFT_UNSERVICEABILITY,
        aircraft_registration=aircraft_registration.strip().upper(),
        operational_reference=operational_reference.strip(),
        work_order_reference=work_order_reference.strip() if work_order_reference else None,
        reason=reason.strip(),
        normal_duty_start=assignment.starts_at,
        original_planned_end=original_end,
        proposed_extended_end=proposed_extended_end,
        continuous_duty_minutes=continuous,
        required_recovery_rest_minutes=required_recovery,
        recovery_rest_basis=(
            f"{getattr(recovery_rule, 'code', 'MIN_REST_HOURS')} / "
            f"{getattr(duration_rule, 'code', 'MAX_ASSIGNMENT_DURATION')}"
        ),
        compliance_snapshot_json=snapshot,
        fatigue_risk_json={
            "continuous_duty_minutes": continuous,
            "ordinary_maximum_minutes": int(duration_parameters.get("maximum_minutes") or 0),
            "extended_maximum_minutes": extended_maximum,
        },
        status=(
            RosterDutyExtensionStatus.COMPLIANCE_BLOCKED
            if result.blocker_count
            else RosterDutyExtensionStatus.AWAITING_PERSONNEL_ACKNOWLEDGEMENT
        ),
        proposed_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterDutyExtension",
        entity_id=row.id,
        action="duty_extension_proposed",
        before=before,
        after={
            "assignment_id": assignment.id,
            "extension_type": row.extension_type.value,
            "aircraft_registration": row.aircraft_registration,
            "operational_reference": row.operational_reference,
            "proposed_extended_end": row.proposed_extended_end.isoformat(),
            "continuous_duty_minutes": continuous,
            "required_recovery_rest_minutes": required_recovery,
            "consent_id": request.id,
            "compliance": snapshot,
        },
        critical=True,
    )
    return row


def refresh_status(db: Session, *, row: RosterDutyExtension, actor_user_id: str | None = None) -> RosterDutyExtension:
    consent = row.consent
    if consent is None:
        row.status = RosterDutyExtensionStatus.COMPLIANCE_BLOCKED
        db.add(row)
        return row
    if consent.personnel_response == RosterConsentStatus.INVALIDATED:
        row.status = RosterDutyExtensionStatus.CANCELLED
    elif consent.personnel_response == RosterConsentStatus.DECLINED:
        row.status = RosterDutyExtensionStatus.COMPLIANCE_BLOCKED
    elif consent.personnel_response != RosterConsentStatus.ACCEPTED:
        row.status = RosterDutyExtensionStatus.AWAITING_PERSONNEL_ACKNOWLEDGEMENT
    elif consent.supervisor_decision != RosterSupervisorDecision.APPROVED:
        row.status = RosterDutyExtensionStatus.AWAITING_SUPERVISOR_APPROVAL
    else:
        version = common.get_version(db, amo_id=row.amo_id, version_id=row.version_id, lock=True)
        result = validation.run_validation(db, version=version, actor_user_id=actor_user_id) if version else None
        row.compliance_snapshot_json = (
            {
                "blocker_count": result.blocker_count,
                "warning_count": result.warning_count,
                "validation_fingerprint": result.validation_fingerprint,
                "finding_codes": [item.code for item in result.findings if not item.resolved],
            }
            if result
            else {"blocker_count": 1, "finding_codes": ["ROSTER_VERSION_NOT_FOUND"]}
        )
        row.status = (
            RosterDutyExtensionStatus.READY
            if result and result.blocker_count == 0
            else RosterDutyExtensionStatus.COMPLIANCE_BLOCKED
        )
    db.add(row)
    return row
