# backend/amodb/apps/rostering/source_state.py
"""Cross-module assignment guards for canonical personnel state.

Leave and unavailability are owned by Workforce. Training participation is
owned by Training. Rostering consumes those records and must not create a
second, contradictory copy of either state.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..training import models as training_models
from ..workforce import models as workforce_models


def _value(value) -> str:
    return str(getattr(value, "value", value))


def ensure_source_owned_state(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    starts_at,
    ends_at,
    assignment_status,
    assignment_source,
    source_reference_id: Optional[str],
) -> None:
    """Reject duplicate external states and duty over source-owned commitments."""
    status_value = _value(assignment_status)
    source_value = _value(assignment_source)
    external_state = status_value in {"LEAVE", "TRAINING", "UNAVAILABLE"}
    trusted_external_source = (
        source_value in {"LEAVE", "TRAINING", "SYSTEM"}
        and bool(source_reference_id)
    )

    if external_state and not trusted_external_source:
        owner = "Training" if status_value == "TRAINING" else "Workforce"
        raise ValueError(
            f"{status_value.replace('_', ' ').title()} is owned by the {owner} module. "
            "Create or approve it there; Rostering will display it automatically."
        )

    if trusted_external_source or status_value in {
        "OFF",
        "LEAVE",
        "TRAINING",
        "UNAVAILABLE",
    }:
        return

    availability = db.query(workforce_models.EmployeeAvailabilityEvent.id).filter(
        workforce_models.EmployeeAvailabilityEvent.amo_id == amo_id,
        workforce_models.EmployeeAvailabilityEvent.user_id == user_id,
        workforce_models.EmployeeAvailabilityEvent.blocking.is_(True),
        workforce_models.EmployeeAvailabilityEvent.starts_at < ends_at,
        workforce_models.EmployeeAvailabilityEvent.ends_at > starts_at,
    ).first()
    if availability:
        raise ValueError(
            "This person has blocking leave or unavailability in the selected period. "
            "Resolve the Workforce source record before assigning duty."
        )

    final_date = (ends_at - timedelta(microseconds=1)).date()
    training = db.query(training_models.TrainingEventParticipant.id).join(
        training_models.TrainingEvent,
        training_models.TrainingEventParticipant.event_id
        == training_models.TrainingEvent.id,
    ).filter(
        training_models.TrainingEventParticipant.amo_id == amo_id,
        training_models.TrainingEventParticipant.user_id == user_id,
        training_models.TrainingEventParticipant.status.notin_([
            training_models.TrainingParticipantStatus.CANCELLED,
            training_models.TrainingParticipantStatus.NO_SHOW,
            training_models.TrainingParticipantStatus.DEFERRED,
        ]),
        training_models.TrainingEvent.status
        != training_models.TrainingEventStatus.CANCELLED,
        training_models.TrainingEvent.starts_on <= final_date,
        or_(
            training_models.TrainingEvent.ends_on.is_(None),
            training_models.TrainingEvent.ends_on >= starts_at.date(),
        ),
    ).first()
    if training:
        raise ValueError(
            "This person is already scheduled for Training in the selected period. "
            "The Training commitment is shown automatically and cannot be overwritten by duty."
        )
