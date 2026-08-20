"""Calendar lifecycle propagation for governed Training sessions.

Training invitations keep a stable iCalendar UID through the existing calendar
endpoint. This listener marks previously-sent invitations for update/cancellation
whenever a material session field changes, including writes made outside the main
Training event route.
"""
from __future__ import annotations

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from . import models as training_models
from . import operating_models

_MATERIAL_FIELDS = {"title", "starts_on", "ends_on", "location", "provider", "status"}
_INSTALLED = False


def _before_flush(session: Session, flush_context, instances) -> None:
    changed_events: list[training_models.TrainingEvent] = []
    for row in list(session.dirty):
        if not isinstance(row, training_models.TrainingEvent):
            continue
        state = inspect(row)
        if any(
            field in state.attrs and state.attrs[field].history.has_changes()
            for field in _MATERIAL_FIELDS
        ):
            changed_events.append(row)

    for training_event in changed_events:
        if not training_event.id or not training_event.amo_id:
            continue
        cancelled = str(getattr(training_event.status, "value", training_event.status) or "").upper() == "CANCELLED"
        target_state = "CANCEL_PENDING" if cancelled else "UPDATE_PENDING"
        invitations = session.query(operating_models.TrainingSessionInvitation).filter(
            operating_models.TrainingSessionInvitation.amo_id == training_event.amo_id,
            operating_models.TrainingSessionInvitation.event_id == training_event.id,
        ).all()
        for invitation in invitations:
            # Preserve RSVP history; a changed session is an update to the same
            # governed invitation, not a new invitation or a synthetic response.
            invitation.delivery_status = target_state
            invitation.last_error = None


def install_training_calendar_lifecycle() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    event.listen(Session, "before_flush", _before_flush)
    _INSTALLED = True


__all__ = ["install_training_calendar_lifecycle"]
