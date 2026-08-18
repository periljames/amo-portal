from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..accounts import models as account_models
from . import common, governance, models
from .code_registry_models import RosterShiftTemplatePolicy
from .consent_models import (
    RosterAssignmentConsent,
    RosterConsentStatus,
    RosterSupervisorDecision,
)

UTC = timezone.utc


@dataclass(frozen=True)
class RosterWorkflowError(ValueError):
    code: str
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


def _now() -> datetime:
    return datetime.now(UTC)


def assignment_fingerprint(row: models.RosterAssignment) -> str:
    """Fingerprint exactly the material duty terms an employee acknowledges."""

    return common.canonical_hash({
        "assignment_id": row.id,
        "personnel_id": row.user_id,
        "date": row.starts_at.date().isoformat(),
        "starts_at": row.starts_at.isoformat(),
        "ends_at": row.ends_at.isoformat(),
        "shift_template_id": row.shift_template_id,
        "status": common.enum_value(row.status),
        "role_label": row.role_label,
    })


def _policy(db: Session, row: models.RosterAssignment) -> RosterShiftTemplatePolicy | None:
    if not row.shift_template_id:
        return None
    return db.query(RosterShiftTemplatePolicy).filter(
        RosterShiftTemplatePolicy.amo_id == row.amo_id,
        RosterShiftTemplatePolicy.shift_template_id == row.shift_template_id,
    ).first()


def _needs_workflow(policy: RosterShiftTemplatePolicy | None) -> bool:
    return bool(
        policy
        and (
            policy.requires_personnel_acknowledgement
            or policy.requires_supervisor_approval
        )
    )


def _active_requests(db: Session, *, amo_id: str, assignment_id: str) -> list[RosterAssignmentConsent]:
    return db.query(RosterAssignmentConsent).filter(
        RosterAssignmentConsent.amo_id == amo_id,
        RosterAssignmentConsent.assignment_id == assignment_id,
        RosterAssignmentConsent.personnel_response != RosterConsentStatus.INVALIDATED,
    ).order_by(
        RosterAssignmentConsent.assignment_revision.desc(),
        RosterAssignmentConsent.created_at.desc(),
    ).all()


def _schedule_snapshot(row: RosterAssignmentConsent) -> dict[str, Any]:
    """Capture the exact prior duty terms for an auditable consent revision."""

    return {
        "assignment_revision": row.assignment_revision,
        "assignment_fingerprint": row.assignment_fingerprint,
        "duty_type": row.duty_type,
        "planned_start": row.planned_start.isoformat(),
        "planned_end": row.planned_end.isoformat(),
        "overtime_rest_day_classification": row.overtime_rest_day_classification,
        "replacement_rest": dict(row.replacement_rest_json or {}),
    }


def _invalidate(
    db: Session,
    row: RosterAssignmentConsent,
    *,
    actor_user_id: str | None,
    reason: str,
) -> None:
    if row.personnel_response == RosterConsentStatus.INVALIDATED:
        return
    before = {
        "personnel_response": common.enum_value(row.personnel_response),
        "supervisor_decision": common.enum_value(row.supervisor_decision),
        "assignment_fingerprint": row.assignment_fingerprint,
    }
    row.personnel_response = RosterConsentStatus.INVALIDATED
    row.invalidated_at = _now()
    row.invalidation_reason = reason
    db.add(row)
    common.audit(
        db,
        amo_id=row.amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterAssignmentConsent",
        entity_id=row.id,
        action="roster_consent_invalidated",
        before=before,
        after={"personnel_response": "INVALIDATED", "reason": reason},
        metadata={"assignment_id": row.assignment_id, "version_id": row.version_id},
        critical=True,
    )


def sync_assignment_consent(
    db: Session,
    *,
    assignment: models.RosterAssignment,
    actor_user_id: str | None,
    reason: str | None = None,
) -> RosterAssignmentConsent | None:
    """Ensure one current consent request exists for the exact material duty."""

    policy = _policy(db, assignment)
    existing = _active_requests(db, amo_id=assignment.amo_id, assignment_id=assignment.id)
    if assignment.deleted_at is not None or not _needs_workflow(policy):
        for request in existing:
            _invalidate(
                db,
                request,
                actor_user_id=actor_user_id,
                reason="ASSIGNMENT_REMOVED_OR_POLICY_NO_LONGER_REQUIRES_CONSENT",
            )
        return None

    fingerprint = assignment_fingerprint(assignment)
    same = next((row for row in existing if row.assignment_fingerprint == fingerprint), None)
    if same is not None:
        return same

    prior_schedule = _schedule_snapshot(existing[0]) if existing else None
    for request in existing:
        _invalidate(
            db,
            request,
            actor_user_id=actor_user_id,
            reason="MATERIAL_ASSIGNMENT_CHANGE",
        )

    personnel = common.require_user(
        db,
        amo_id=assignment.amo_id,
        user_id=assignment.user_id,
        active_only=True,
    )
    supervisor_required = bool(policy and policy.requires_supervisor_approval)
    request = RosterAssignmentConsent(
        amo_id=assignment.amo_id,
        version_id=assignment.version_id,
        assignment_id=assignment.id,
        assignment_revision=max(int(assignment.state_revision or 1), 1),
        assignment_fingerprint=fingerprint,
        personnel_id=assignment.user_id,
        proposed_by_user_id=actor_user_id,
        reason=(reason or assignment.change_reason or "Roster assignment requires personnel acknowledgement").strip(),
        duty_type=common.enum_value(assignment.status),
        planned_start=assignment.starts_at,
        planned_end=assignment.ends_at,
        original_schedule_json=prior_schedule,
        personnel_response=RosterConsentStatus.PENDING,
        supervisor_required=supervisor_required,
        supervisor_decision=(
            RosterSupervisorDecision.PENDING
            if supervisor_required
            else RosterSupervisorDecision.NOT_REQUIRED
        ),
        overtime_rest_day_classification=getattr(policy, "pay_classification", None),
        fatigue_risk_json={"weight": float(getattr(policy, "fatigue_weight", 1.0) or 0.0)},
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
            "personnel_id": assignment.user_id,
            "assignment_revision": request.assignment_revision,
            "assignment_fingerprint": fingerprint,
            "supervisor_required": supervisor_required,
            "original_schedule": prior_schedule,
        },
        metadata={"version_id": assignment.version_id},
        critical=True,
    )
    common.notify_email(
        db,
        amo_id=assignment.amo_id,
        recipient=getattr(personnel, "email", None),
        template_key="roster_consent_requested",
        subject="Roster acknowledgement required",
        context={
            "personnel_name": getattr(personnel, "full_name", None),
            "assignment_id": assignment.id,
            "consent_id": request.id,
            "starts_at": assignment.starts_at.isoformat(),
            "ends_at": assignment.ends_at.isoformat(),
            "reason": request.reason,
        },
        correlation_id=f"roster-consent:{request.id}:{fingerprint}",
    )
    return request


def current_request(
    db: Session,
    *,
    amo_id: str,
    consent_id: str,
    lock: bool = False,
) -> RosterAssignmentConsent | None:
    query = db.query(RosterAssignmentConsent).filter(
        RosterAssignmentConsent.amo_id == amo_id,
        RosterAssignmentConsent.id == consent_id,
    )
    if lock:
        query = query.with_for_update()
    return query.first()


def _assert_current_assignment(db: Session, request: RosterAssignmentConsent) -> models.RosterAssignment:
    assignment = common.get_assignment(
        db,
        amo_id=request.amo_id,
        assignment_id=request.assignment_id,
        lock=True,
    )
    if assignment is None or assignment_fingerprint(assignment) != request.assignment_fingerprint:
        _invalidate(
            db,
            request,
            actor_user_id=None,
            reason="STALE_ASSIGNMENT_VERSION",
        )
        raise RosterWorkflowError(
            "ROSTER_CONSENT_STALE",
            "The assignment changed after this acknowledgement request was issued.",
            {"assignment_id": request.assignment_id, "consent_id": request.id},
        )
    return assignment


def respond(
    db: Session,
    *,
    request: RosterAssignmentConsent,
    actor: account_models.User,
    accept: bool,
    comment: str | None = None,
) -> RosterAssignmentConsent:
    if request.personnel_id != actor.id:
        raise RosterWorkflowError(
            "ROSTER_CONSENT_FORBIDDEN",
            "Personnel may only acknowledge their own roster assignments.",
            {"consent_id": request.id},
        )
    if request.personnel_response != RosterConsentStatus.PENDING:
        raise RosterWorkflowError(
            "ROSTER_CONSENT_STALE",
            "This acknowledgement request is no longer pending.",
            {"consent_id": request.id, "status": common.enum_value(request.personnel_response)},
        )
    assignment = _assert_current_assignment(db, request)
    request.personnel_response = RosterConsentStatus.ACCEPTED if accept else RosterConsentStatus.DECLINED
    request.personnel_response_at = _now()
    request.personnel_comment = comment
    db.add(request)
    common.audit(
        db,
        amo_id=request.amo_id,
        actor_user_id=actor.id,
        entity_type="RosterAssignmentConsent",
        entity_id=request.id,
        action="roster_consent_accepted" if accept else "roster_consent_declined",
        after={
            "assignment_id": request.assignment_id,
            "personnel_response": common.enum_value(request.personnel_response),
            "assignment_fingerprint": request.assignment_fingerprint,
        },
        metadata={"version_id": request.version_id},
        critical=True,
    )
    if not accept:
        common.audit(
            db,
            amo_id=request.amo_id,
            actor_user_id=actor.id,
            entity_type="RosterVersion",
            entity_id=request.version_id,
            action="roster_compliance_blocked",
            metadata={"code": "ROSTER_CONSENT_DECLINED", "assignment_id": assignment.id},
            critical=True,
        )
    return request


def supervisor_decide(
    db: Session,
    *,
    request: RosterAssignmentConsent,
    actor: account_models.User,
    approve: bool,
    comment: str | None = None,
) -> RosterAssignmentConsent:
    assignment = _assert_current_assignment(db, request)
    if not request.supervisor_required:
        raise RosterWorkflowError(
            "ROSTER_SUPERVISOR_APPROVAL_NOT_REQUIRED",
            "This assignment does not require supervisor approval.",
            {"consent_id": request.id},
        )
    if request.personnel_response != RosterConsentStatus.ACCEPTED:
        raise RosterWorkflowError(
            "ROSTER_CONSENT_REQUIRED",
            "Personnel acknowledgement must be accepted before supervisor action.",
            {"consent_id": request.id},
        )
    if request.supervisor_decision != RosterSupervisorDecision.PENDING:
        raise RosterWorkflowError(
            "ROSTER_SUPERVISOR_DECISION_STALE",
            "This supervisor decision is no longer pending.",
            {"consent_id": request.id},
        )
    if not governance.can_approve_scope(
        db,
        user=actor,
        department_id=assignment.department_id,
        base_station_id=assignment.base_station_id,
    ):
        raise RosterWorkflowError(
            "ROSTER_SUPERVISOR_SCOPE_FORBIDDEN",
            "Supervisor approval is outside this user's permitted roster scope.",
            {"assignment_id": assignment.id},
        )
    request.supervisor_decision = (
        RosterSupervisorDecision.APPROVED if approve else RosterSupervisorDecision.REJECTED
    )
    request.supervisor_decision_at = _now()
    request.supervisor_decided_by_user_id = actor.id
    request.supervisor_user_id = actor.id
    request.supervisor_comment = comment
    db.add(request)
    common.audit(
        db,
        amo_id=request.amo_id,
        actor_user_id=actor.id,
        entity_type="RosterAssignmentConsent",
        entity_id=request.id,
        action="roster_supervisor_approved" if approve else "roster_supervisor_rejected",
        after={
            "assignment_id": request.assignment_id,
            "supervisor_decision": common.enum_value(request.supervisor_decision),
        },
        metadata={"version_id": request.version_id},
        critical=True,
    )
    return request


def ensure_version_consents(
    db: Session,
    *,
    version: models.RosterVersion,
    actor_user_id: str | None = None,
) -> list[RosterAssignmentConsent]:
    requests: list[RosterAssignmentConsent] = []
    for assignment in version.assignments or []:
        if assignment.deleted_at is not None:
            continue
        request = sync_assignment_consent(
            db,
            assignment=assignment,
            actor_user_id=actor_user_id,
        )
        if request is not None:
            requests.append(request)
    return requests


def assert_version_ready(
    db: Session,
    *,
    version: models.RosterVersion,
    actor_user_id: str | None = None,
) -> None:
    requests = ensure_version_consents(db, version=version, actor_user_id=actor_user_id)
    for request in requests:
        assignment = _assert_current_assignment(db, request)
        if request.personnel_response == RosterConsentStatus.DECLINED:
            raise RosterWorkflowError(
                "ROSTER_CONSENT_DECLINED",
                "A required roster assignment was declined by the employee.",
                {"assignment_id": assignment.id, "personnel_id": request.personnel_id},
            )
        if request.personnel_response != RosterConsentStatus.ACCEPTED:
            raise RosterWorkflowError(
                "ROSTER_CONSENT_REQUIRED",
                "Required personnel acknowledgement is still outstanding.",
                {"assignment_id": assignment.id, "personnel_id": request.personnel_id},
            )
        if request.supervisor_required and request.supervisor_decision != RosterSupervisorDecision.APPROVED:
            raise RosterWorkflowError(
                "ROSTER_SUPERVISOR_APPROVAL_REQUIRED",
                "Required supervisor approval is still outstanding.",
                {"assignment_id": assignment.id, "consent_id": request.id},
            )


def list_for_personnel(
    db: Session,
    *,
    amo_id: str,
    personnel_id: str,
) -> list[RosterAssignmentConsent]:
    return db.query(RosterAssignmentConsent).filter(
        RosterAssignmentConsent.amo_id == amo_id,
        RosterAssignmentConsent.personnel_id == personnel_id,
    ).order_by(RosterAssignmentConsent.created_at.desc()).all()
