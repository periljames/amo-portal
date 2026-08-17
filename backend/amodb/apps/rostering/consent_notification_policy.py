from __future__ import annotations

from typing import Iterable

from ..accounts import models as account_models
from . import common, consent_service, governance, models
from .consent_models import RosterConsentStatus, RosterSupervisorDecision

_INSTALLED = False


def _user_email(db, *, amo_id: str, user_id: str | None) -> str | None:
    if not user_id:
        return None
    row = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id == user_id,
    ).first()
    return getattr(row, "email", None) if row else None


def _notify(
    db,
    *,
    amo_id: str,
    recipient: str | None,
    event: str,
    subject: str,
    consent_id: str,
    fingerprint: str,
    context: dict,
) -> None:
    if not recipient:
        return
    common.notify_email(
        db,
        amo_id=amo_id,
        recipient=recipient,
        template_key=event,
        subject=subject,
        context={"event": event, "consent_id": consent_id, **context},
        correlation_id=f"{event}:{consent_id}:{fingerprint}",
    )


def _supervisor_recipients(db, assignment: models.RosterAssignment) -> Iterable[str]:
    seen: set[str] = set()
    for authority in governance.list_authorities(db, amo_id=assignment.amo_id):
        if not authority.can_approve:
            continue
        if authority.department_id and authority.department_id != assignment.department_id:
            continue
        if authority.base_station_id and authority.base_station_id != assignment.base_station_id:
            continue
        email = getattr(authority.user, "email", None)
        if email and email not in seen:
            seen.add(email)
            yield email


def install() -> None:
    """Use the existing notification service for all consent workflow events.

    The base consent service already sends the initial consent-requested message.
    This wrapper adds change/invalidation and supervisor workflow events without
    ever claiming the full roster is ready merely because one consent was approved.
    """

    global _INSTALLED
    if _INSTALLED:
        return

    original_sync = consent_service.sync_assignment_consent
    original_respond = consent_service.respond
    original_supervisor_decide = consent_service.supervisor_decide

    def sync_assignment_consent(db, *, assignment, actor_user_id, reason=None):
        previous = consent_service._active_requests(
            db,
            amo_id=assignment.amo_id,
            assignment_id=assignment.id,
        )
        previous_ids = {row.id for row in previous}
        previous_accepted = [
            row for row in previous
            if row.personnel_response == RosterConsentStatus.ACCEPTED
        ]
        request = original_sync(
            db,
            assignment=assignment,
            actor_user_id=actor_user_id,
            reason=reason,
        )
        for old in previous:
            if old.personnel_response == RosterConsentStatus.INVALIDATED:
                _notify(
                    db,
                    amo_id=old.amo_id,
                    recipient=_user_email(db, amo_id=old.amo_id, user_id=old.personnel_id),
                    event="roster_consent_invalidated",
                    subject="Roster acknowledgement changed",
                    consent_id=old.id,
                    fingerprint=old.assignment_fingerprint,
                    context={
                        "assignment_id": old.assignment_id,
                        "reason": old.invalidation_reason,
                    },
                )
        if request is not None and request.id not in previous_ids and previous_accepted:
            _notify(
                db,
                amo_id=request.amo_id,
                recipient=_user_email(db, amo_id=request.amo_id, user_id=request.personnel_id),
                event="roster_assignment_changed_after_consent",
                subject="Roster assignment changed — acknowledgement required again",
                consent_id=request.id,
                fingerprint=request.assignment_fingerprint,
                context={
                    "assignment_id": request.assignment_id,
                    "starts_at": request.planned_start.isoformat(),
                    "ends_at": request.planned_end.isoformat(),
                },
            )
        return request

    def respond(db, *, request, actor, accept, comment=None):
        row = original_respond(
            db,
            request=request,
            actor=actor,
            accept=accept,
            comment=comment,
        )
        event = "roster_consent_accepted" if accept else "roster_consent_declined"
        _notify(
            db,
            amo_id=row.amo_id,
            recipient=_user_email(db, amo_id=row.amo_id, user_id=row.proposed_by_user_id),
            event=event,
            subject="Roster assignment accepted" if accept else "Roster assignment declined",
            consent_id=row.id,
            fingerprint=row.assignment_fingerprint,
            context={
                "assignment_id": row.assignment_id,
                "personnel_id": row.personnel_id,
                "comment": row.personnel_comment,
            },
        )
        if accept and row.supervisor_required and row.supervisor_decision == RosterSupervisorDecision.PENDING:
            assignment = common.get_assignment(
                db,
                amo_id=row.amo_id,
                assignment_id=row.assignment_id,
            )
            if assignment is not None:
                for recipient in _supervisor_recipients(db, assignment):
                    _notify(
                        db,
                        amo_id=row.amo_id,
                        recipient=recipient,
                        event="roster_supervisor_approval_required",
                        subject="Roster supervisor approval required",
                        consent_id=row.id,
                        fingerprint=row.assignment_fingerprint,
                        context={
                            "assignment_id": row.assignment_id,
                            "personnel_id": row.personnel_id,
                            "starts_at": row.planned_start.isoformat(),
                            "ends_at": row.planned_end.isoformat(),
                        },
                    )
        return row

    def supervisor_decide(db, *, request, actor, approve, comment=None):
        row = original_supervisor_decide(
            db,
            request=request,
            actor=actor,
            approve=approve,
            comment=comment,
        )
        _notify(
            db,
            amo_id=row.amo_id,
            recipient=_user_email(db, amo_id=row.amo_id, user_id=row.proposed_by_user_id),
            event="roster_supervisor_approved" if approve else "roster_supervisor_rejected",
            subject="Roster supervisor approval recorded" if approve else "Roster supervisor rejected assignment",
            consent_id=row.id,
            fingerprint=row.assignment_fingerprint,
            context={
                "assignment_id": row.assignment_id,
                "personnel_id": row.personnel_id,
                "supervisor_user_id": actor.id,
                "comment": row.supervisor_comment,
            },
        )
        return row

    consent_service.sync_assignment_consent = sync_assignment_consent
    consent_service.respond = respond
    consent_service.supervisor_decide = supervisor_decide
    _INSTALLED = True


__all__ = ["install"]
