from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from . import operating_models

PASSING_STATUSES = {"APPROVED", "COMPLETED"}
PASSING_OUTCOMES = {"PASS", "PASSED", "COMPETENT", "SATISFACTORY"}
READY_ITEM_STATES = {"CURRENT", "COMPLETE", "READY", "NOT_APPLICABLE"}


def _enum(value) -> str:
    return str(getattr(value, "value", value) or "").upper()


def bridge_readiness(base_compute: Callable):
    def compute(db: Session, *, case):
        result = base_compute(db, case=case)
        required = {
            str(value or "").strip().upper()
            for value in (case.required_assessment_types or [])
            if str(value or "").strip()
        }
        if not required:
            return result

        rows = (
            db.query(operating_models.TrainingAssessmentInstance, operating_models.TrainingAssessmentTemplate)
            .join(
                operating_models.TrainingAssessmentTemplate,
                operating_models.TrainingAssessmentTemplate.id == operating_models.TrainingAssessmentInstance.template_id,
            )
            .filter(
                operating_models.TrainingAssessmentInstance.amo_id == case.amo_id,
                operating_models.TrainingAssessmentInstance.candidate_user_id == case.candidate_user_id,
            )
            .all()
        )
        passed_types = {
            _enum(template.assessment_type)
            for assessment, template in rows
            if _enum(assessment.status) in PASSING_STATUSES
            and _enum(assessment.outcome) in PASSING_OUTCOMES
        }

        changed = False
        for assessment_type in required:
            item = next(
                (entry for entry in result.items if entry.key == f"assessment_{assessment_type.lower()}"),
                None,
            )
            if item is None or assessment_type not in passed_types:
                continue
            if item.status != "COMPLETE":
                item.status = "COMPLETE"
                item.reason = "Canonical approved/passed assessment outcome recorded."
                item.source = "canonical assessment register"
                changed = True

        if not changed:
            return result
        if result.overall_status in {"REJECTED", "DEFERRED"}:
            case.readiness_snapshot = {
                "overall_status": result.overall_status,
                "items": [item.model_dump(mode="json") for item in result.items],
            }
            return result

        blockers = [
            item
            for item in result.items
            if item.blocking
            and not item.key.startswith("committee_")
            and item.status not in READY_ITEM_STATES
        ]
        committee_items = [item for item in result.items if item.key.startswith("committee_")]
        committee_complete = [item for item in committee_items if item.status == "COMPLETE"]

        if blockers:
            overall = "NOT_READY"
        elif not required.issubset(passed_types):
            overall = "ASSESSMENT_IN_PROGRESS"
        elif committee_items and len(committee_complete) == len(committee_items):
            overall = "APPROVED"
        elif committee_complete:
            overall = "DECISION_REQUIRED"
        else:
            overall = "READY_FOR_COMMITTEE"

        result.overall_status = overall
        result.next_required_action = (
            "Issue authorization"
            if overall == "APPROVED"
            else "Complete the first blocking readiness item"
            if blockers
            else "Record remaining committee decisions"
        )
        case.status = overall
        case.readiness_snapshot = {
            "overall_status": overall,
            "items": [item.model_dump(mode="json") for item in result.items],
        }
        return result

    return compute


__all__ = ["bridge_readiness"]
