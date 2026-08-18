from __future__ import annotations

"""Tenant-scoped learner projections for governed Training workflows.

These routes expose only the current learner's invitations, assessments and
authorisation cases.  Mutations remain on the canonical Training entities; no
parallel learner state is introduced.
"""

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...database import get_db, get_read_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import models as training_models
from . import operating_models

UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: Any) -> Any:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else value


def _enum(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


class LearnerRsvpPayload(BaseModel):
    response: Literal["ACCEPTED", "DECLINED", "TENTATIVE"]


def _safe_assessment_payload(
    row: operating_models.TrainingAssessmentInstance,
    template: operating_models.TrainingAssessmentTemplate | None,
) -> dict[str, Any]:
    results = dict(row.results or {})
    engine = dict(results.get("_engine") or {})
    safe_questions: list[dict[str, Any]] = []
    for raw in engine.get("questions") or []:
        if not isinstance(raw, dict):
            continue
        safe_questions.append(
            {
                key: raw.get(key)
                for key in (
                    "id",
                    "sequence_no",
                    "question_text",
                    "response_type",
                    "answer_options",
                    "marks",
                    "mandatory",
                )
            }
        )
    safe_engine = {
        key: engine.get(key)
        for key in (
            "attempt_no",
            "attempt_limit",
            "started_at",
            "deadline_at",
            "time_limit_minutes",
            "cooldown_hours",
            "cooldown_until",
            "autosave_revision",
            "autosaved_at",
            "submitted_at",
        )
        if key in engine
    }
    return {
        "id": str(row.id),
        "status": row.status,
        "outcome": row.outcome,
        "score": float(row.score) if row.score is not None else None,
        "assessment_type": template.assessment_type if template else None,
        "template_name": template.name if template else "Assessment",
        "candidate_user_id": str(row.candidate_user_id),
        "course_id": str(row.course_id) if row.course_id else None,
        "event_id": str(row.event_id) if row.event_id else None,
        "authorization_case_id": str(row.authorization_case_id) if row.authorization_case_id else None,
        "planned_at": _iso(row.planned_at),
        "performed_at": _iso(row.performed_at),
        "attempt": safe_engine,
        "questions": safe_questions,
        "answers": dict(results.get("answers") or {}),
        "comments": row.comments,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def install_training_learner_workflow_routes(router_module) -> None:
    router = router_module.router
    if getattr(router, "_learner_workflow_routes_installed", False):
        return
    router._learner_workflow_routes_installed = True

    @router.get("/assessments/me")
    def list_my_training_assessments(
        include_completed: bool = True,
        limit: int = Query(100, ge=1, le=250),
        db: Session = Depends(get_read_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        query = db.query(operating_models.TrainingAssessmentInstance).filter(
            operating_models.TrainingAssessmentInstance.amo_id == amo_id,
            operating_models.TrainingAssessmentInstance.candidate_user_id == str(current_user.id),
        )
        if not include_completed:
            query = query.filter(
                operating_models.TrainingAssessmentInstance.status.notin_(["COMPLETED", "CANCELLED"])
            )
        rows = query.order_by(operating_models.TrainingAssessmentInstance.created_at.desc()).limit(limit).all()
        template_ids = {str(row.template_id) for row in rows}
        templates = db.query(operating_models.TrainingAssessmentTemplate).filter(
            operating_models.TrainingAssessmentTemplate.amo_id == amo_id,
            operating_models.TrainingAssessmentTemplate.id.in_(template_ids or {""}),
        ).all()
        template_by_id = {str(row.id): row for row in templates}
        return [
            _safe_assessment_payload(row, template_by_id.get(str(row.template_id)))
            for row in rows
        ]

    @router.get("/authorization-cases/me")
    def list_my_training_authorization_cases(
        limit: int = Query(100, ge=1, le=250),
        db: Session = Depends(get_read_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        rows = db.query(operating_models.TrainingAuthorizationCase).filter(
            operating_models.TrainingAuthorizationCase.amo_id == amo_id,
            operating_models.TrainingAuthorizationCase.candidate_user_id == str(current_user.id),
        ).order_by(operating_models.TrainingAuthorizationCase.updated_at.desc()).limit(limit).all()
        return [
            {
                "id": str(row.id),
                "status": row.status,
                "authorisation_type_id": str(row.authorisation_type_id),
                "requested_scope": row.requested_scope,
                "application_date": _iso(row.application_date),
                "required_assessment_types": list(row.required_assessment_types or []),
                "readiness_snapshot": dict(row.readiness_snapshot or {}),
                "readiness_computed_at": _iso(row.readiness_computed_at),
                "recommendation": row.recommendation,
                "decision": row.decision,
                "restrictions": row.restrictions,
                "updated_at": _iso(row.updated_at),
            }
            for row in rows
        ]

    @router.post("/invitations/{invitation_id}/rsvp")
    def learner_rsvp_training_invitation(
        invitation_id: str,
        payload: LearnerRsvpPayload,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        invitation = db.query(operating_models.TrainingSessionInvitation).filter(
            operating_models.TrainingSessionInvitation.id == invitation_id,
            operating_models.TrainingSessionInvitation.amo_id == amo_id,
            operating_models.TrainingSessionInvitation.user_id == str(current_user.id),
        ).first()
        if invitation is None:
            raise HTTPException(status_code=404, detail="Training invitation was not found for this learner/tenant.")
        event = db.query(training_models.TrainingEvent).filter(
            training_models.TrainingEvent.id == invitation.event_id,
            training_models.TrainingEvent.amo_id == amo_id,
        ).first()
        if event is None:
            raise HTTPException(status_code=404, detail="Training event was not found in this tenant.")
        if _enum(event.status).upper() == "CANCELLED":
            raise HTTPException(status_code=409, detail="A cancelled Training event cannot accept RSVP changes.")

        prior = str(invitation.rsvp_status or "PENDING")
        invitation.rsvp_status = payload.response
        invitation.responded_at = _now()
        if invitation.read_at is None:
            invitation.read_at = _now()

        participant = db.query(training_models.TrainingEventParticipant).filter(
            training_models.TrainingEventParticipant.amo_id == amo_id,
            training_models.TrainingEventParticipant.event_id == invitation.event_id,
            training_models.TrainingEventParticipant.user_id == str(current_user.id),
        ).first()
        if participant is not None:
            participant.status = {
                "ACCEPTED": training_models.TrainingParticipantStatus.CONFIRMED,
                "DECLINED": training_models.TrainingParticipantStatus.CANCELLED,
                "TENTATIVE": training_models.TrainingParticipantStatus.INVITED,
            }[payload.response]

        router_module._audit(
            db,
            amo_id=amo_id,
            actor_user_id=str(current_user.id),
            action="TRAINING_INVITATION_RSVP",
            entity_type="TrainingSessionInvitation",
            entity_id=str(invitation.id),
            details={
                "from": prior,
                "to": payload.response,
                "event_id": str(invitation.event_id),
                "participant_status": _enum(participant.status) if participant is not None else None,
            },
        )
        db.commit()
        db.refresh(invitation)
        return {
            "id": str(invitation.id),
            "event_id": str(invitation.event_id),
            "rsvp_status": invitation.rsvp_status,
            "responded_at": _iso(invitation.responded_at),
            "participant_status": _enum(participant.status) if participant is not None else None,
        }


__all__ = ["install_training_learner_workflow_routes"]
