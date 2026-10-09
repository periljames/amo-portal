"""Connect auditee responses and Quality review to the existing CAR milestones."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .car_control_loop_models import QualityCARControlEvent, QualityCARControlProfile, QualityCARMilestone


def sync_response_milestones(db: Session, car, *, actor_user_id: str | None, record_review: bool = True) -> bool:
    profile = db.query(QualityCARControlProfile).filter(
        QualityCARControlProfile.amo_id == car.amo_id,
        QualityCARControlProfile.car_id == car.id,
    ).first()
    if profile is None:
        return False
    now = datetime.now(timezone.utc)
    for key, decision, note in (
        ("RCA_SUBMISSION", car.root_cause_status, car.root_cause_review_note),
        ("CAP_APPROVAL", car.capa_status, car.capa_review_note),
    ):
        status = {"SUBMITTED": "SUBMITTED", "ACCEPTED": "ACCEPTED", "REJECTED": "REJECTED", "NEEDS_EVIDENCE": "IN_PROGRESS", "PENDING": "PLANNED"}.get(decision)
        if status is None:
            continue
        milestone = db.query(QualityCARMilestone).filter(
            QualityCARMilestone.amo_id == car.amo_id,
            QualityCARMilestone.car_id == car.id,
            QualityCARMilestone.profile_id == profile.id,
            QualityCARMilestone.milestone_key == key,
        ).with_for_update().first()
        if milestone is None or milestone.status == status:
            continue
        previous = milestone.status
        milestone.status = status
        milestone.notes = note if decision in {"ACCEPTED", "REJECTED", "NEEDS_EVIDENCE"} else None
        milestone.completed_at = now if record_review and status == "ACCEPTED" else None
        milestone.completed_by_user_id = actor_user_id if record_review and status == "ACCEPTED" else None
        milestone.reviewed_at = now if record_review and actor_user_id and decision in {"ACCEPTED", "REJECTED", "NEEDS_EVIDENCE"} else None
        milestone.reviewed_by_user_id = actor_user_id if milestone.reviewed_at else None
        db.add(QualityCARControlEvent(
            amo_id=car.amo_id, car_id=car.id, milestone_id=milestone.id,
            event_type="RESPONSE_MILESTONE_UPDATED", actor_user_id=actor_user_id,
            reason=f"{key.replace('_', ' ').title()} synchronized from the auditee response and Quality review.",
            snapshot={"milestone_key": key, "previous_status": previous, "status": status, "submitted_at": car.submitted_at.isoformat() if car.submitted_at else None},
        ))
    # Implementation, evidence verification and effectiveness require their own
    # recorded decisions. Accepting a proposed plan never completes those stages.
    return True
