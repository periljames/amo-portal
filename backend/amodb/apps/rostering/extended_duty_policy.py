from __future__ import annotations

from . import consent_service, extended_duty_service
from .consent_models import RosterConsentStatus, RosterSupervisorDecision
from .extended_duty_models import RosterDutyExtension, RosterDutyExtensionStatus

_INSTALLED = False


def install() -> None:
    """Bind controlled extensions to the canonical consent lifecycle."""

    global _INSTALLED
    if _INSTALLED:
        return

    original_sync = consent_service.sync_assignment_consent
    original_respond = consent_service.respond
    original_supervisor = consent_service.supervisor_decide

    def sync_assignment_consent(db, *, assignment, actor_user_id, reason=None):
        extension = db.query(RosterDutyExtension).filter(
            RosterDutyExtension.amo_id == assignment.amo_id,
            RosterDutyExtension.assignment_id == assignment.id,
            RosterDutyExtension.status != RosterDutyExtensionStatus.CANCELLED,
        ).order_by(RosterDutyExtension.created_at.desc()).first()
        if extension is not None and extension.consent is not None:
            fingerprint = consent_service.assignment_fingerprint(assignment)
            if (
                extension.consent.assignment_fingerprint == fingerprint
                and extension.consent.personnel_response != RosterConsentStatus.INVALIDATED
            ):
                return extension.consent
            consent_service._invalidate(
                db,
                extension.consent,
                actor_user_id=actor_user_id,
                reason="MATERIAL_ASSIGNMENT_CHANGE_AFTER_EXTENSION_PROPOSAL",
            )
            extension.status = RosterDutyExtensionStatus.CANCELLED
            db.add(extension)
        return original_sync(
            db,
            assignment=assignment,
            actor_user_id=actor_user_id,
            reason=reason,
        )

    def respond(db, *, request, actor, accept, comment=None):
        row = original_respond(
            db,
            request=request,
            actor=actor,
            accept=accept,
            comment=comment,
        )
        extension = db.query(RosterDutyExtension).filter(
            RosterDutyExtension.amo_id == row.amo_id,
            RosterDutyExtension.consent_id == row.id,
        ).with_for_update().first()
        if extension is not None:
            if not accept:
                extension.status = RosterDutyExtensionStatus.COMPLIANCE_BLOCKED
                db.add(extension)
            else:
                extended_duty_service.refresh_status(
                    db,
                    row=extension,
                    actor_user_id=actor.id,
                )
        return row

    def supervisor_decide(db, *, request, actor, approve, comment=None):
        row = original_supervisor(
            db,
            request=request,
            actor=actor,
            approve=approve,
            comment=comment,
        )
        extension = db.query(RosterDutyExtension).filter(
            RosterDutyExtension.amo_id == row.amo_id,
            RosterDutyExtension.consent_id == row.id,
        ).with_for_update().first()
        if extension is not None:
            if not approve or row.supervisor_decision == RosterSupervisorDecision.REJECTED:
                extension.status = RosterDutyExtensionStatus.COMPLIANCE_BLOCKED
                db.add(extension)
            else:
                extended_duty_service.refresh_status(
                    db,
                    row=extension,
                    actor_user_id=actor.id,
                )
        return row

    consent_service.sync_assignment_consent = sync_assignment_consent
    consent_service.respond = respond
    consent_service.supervisor_decide = supervisor_decide
    _INSTALLED = True


__all__ = ["install"]
