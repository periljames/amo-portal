from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from . import operating_models


PASSING_STATUSES = {"APPROVED", "COMPLETED"}
PASSING_OUTCOMES = {"PASS", "PASSED", "COMPETENT", "SATISFACTORY"}


def _enum(value) -> str:
    return str(getattr(value, "value", value) or "").strip().upper()


def bridge_completion_gate(base_gate: Callable):
    """Remove the legacy assessment blocker when canonical proof exists."""

    def completion_gate(db: Session, *, record):
        blockers = list(base_gate(db, record=record))
        if not any(item.get("code") == "ASSESSMENT_MISSING" for item in blockers):
            return blockers
        passed = (
            db.query(operating_models.TrainingAssessmentInstance)
            .filter(
                operating_models.TrainingAssessmentInstance.amo_id == record.amo_id,
                operating_models.TrainingAssessmentInstance.course_id == record.course_id,
                operating_models.TrainingAssessmentInstance.candidate_user_id == record.user_id,
            )
            .all()
        )
        if not any(
            _enum(row.status) in PASSING_STATUSES and _enum(row.outcome) in PASSING_OUTCOMES
            for row in passed
        ):
            return blockers
        return [item for item in blockers if item.get("code") != "ASSESSMENT_MISSING"]

    return completion_gate


__all__ = ["bridge_completion_gate"]
