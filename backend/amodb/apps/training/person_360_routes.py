"""Tenant-scoped Training Person 360 projection.

This is a read model over the existing canonical Training, assessment,
certificate, workflow and authorization domains. It deliberately excludes
assessment responses and answer keys.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import compliance
from . import governance_models
from . import models as training_models
from . import operating_models
from . import operating_service
from .permissions import TrainingCapability as Cap, require_training_capability, tenant_id_for


def _enum(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().upper()


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _is_training_editor(router_module, user: account_models.User) -> bool:
    helper = getattr(router_module, "_is_training_editor", None)
    return bool(helper and helper(user))


def _assert_person_scope(
    router_module,
    *,
    current_user: account_models.User,
    person: account_models.User,
) -> None:
    if str(person.id) == str(current_user.id):
        return
    if _is_training_editor(router_module, current_user):
        return
    current_department = str(getattr(current_user, "department_id", None) or "")
    person_department = str(getattr(person, "department_id", None) or "")
    if current_department and current_department == person_department:
        return
    raise HTTPException(
        status_code=403,
        detail="Person 360 is limited to your department unless you hold tenant-wide Training management authority.",
    )


def _course_map(db: Session, *, amo_id: str, course_ids: set[str]) -> dict[str, training_models.TrainingCourse]:
    if not course_ids:
        return {}
    rows = db.query(training_models.TrainingCourse).filter(
        training_models.TrainingCourse.amo_id == amo_id,
        training_models.TrainingCourse.id.in_(course_ids),
    ).all()
    return {str(row.id): row for row in rows}


def install_training_person_360_routes(router_module) -> None:
    router = router_module.router
    if getattr(router, "_training_person_360_routes_installed", False):
        return
    router._training_person_360_routes_installed = True

    @router.get("/operating/people/{user_id}/360")
    def person_360(
        user_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.PEOPLE_VIEW)),
    ):
        amo_id = tenant_id_for(current_user)
        person = db.query(account_models.User).filter(
            account_models.User.id == user_id,
            account_models.User.amo_id == amo_id,
            account_models.User.is_system_account.is_(False),
        ).first()
        if person is None:
            raise HTTPException(status_code=404, detail="Person was not found in this tenant.")
        _assert_person_scope(router_module, current_user=current_user, person=person)

        evaluation = compliance.evaluate_user_training_policy(
            db,
            person,
            required_only=False,
            today=date.today(),
        )
        requirements = [
            {
                "course_id": str(item.course_id),
                "course_name": item.course_name,
                "status": item.status,
                "valid_until": _iso(item.valid_until),
                "extended_due_date": _iso(item.extended_due_date),
                "days_until_due": item.days_until_due,
                "last_completion_date": _iso(item.last_completion_date),
            }
            for item in evaluation.items
        ]

        records = db.query(training_models.TrainingRecord).filter(
            training_models.TrainingRecord.amo_id == amo_id,
            training_models.TrainingRecord.user_id == user_id,
        ).order_by(
            training_models.TrainingRecord.completion_date.desc(),
            training_models.TrainingRecord.created_at.desc(),
        ).limit(250).all()
        record_course_ids = {str(row.course_id) for row in records}

        assessments = db.query(operating_models.TrainingAssessmentInstance).filter(
            operating_models.TrainingAssessmentInstance.amo_id == amo_id,
            operating_models.TrainingAssessmentInstance.candidate_user_id == user_id,
        ).order_by(operating_models.TrainingAssessmentInstance.created_at.desc()).limit(250).all()
        template_ids = {str(row.template_id) for row in assessments}
        templates = {
            str(row.id): row
            for row in db.query(operating_models.TrainingAssessmentTemplate).filter(
                operating_models.TrainingAssessmentTemplate.amo_id == amo_id,
                operating_models.TrainingAssessmentTemplate.id.in_(template_ids or {""}),
            ).all()
        }
        assessment_course_ids = {str(row.course_id) for row in assessments if row.course_id}

        certificates = db.query(training_models.TrainingCertificateIssue).join(
            training_models.TrainingRecord,
            training_models.TrainingRecord.id == training_models.TrainingCertificateIssue.record_id,
        ).filter(
            training_models.TrainingCertificateIssue.amo_id == amo_id,
            training_models.TrainingRecord.amo_id == amo_id,
            training_models.TrainingRecord.user_id == user_id,
        ).order_by(training_models.TrainingCertificateIssue.issued_at.desc()).limit(250).all()

        workflows = db.query(operating_models.TrainingWorkflowInstance).filter(
            operating_models.TrainingWorkflowInstance.amo_id == amo_id,
            operating_models.TrainingWorkflowInstance.subject_user_id == user_id,
            operating_models.TrainingWorkflowInstance.workflow_type.in_([
                "EXTERNAL_LEARNING",
                "ASSESSMENT_APPEAL",
                "OJT_REVIEW",
                "COMPETENCE_REVIEW",
            ]),
        ).order_by(operating_models.TrainingWorkflowInstance.created_at.desc()).limit(250).all()
        workflow_course_ids = {str(row.course_id) for row in workflows if row.course_id}

        authorizations = db.query(operating_models.TrainingAuthorizationCase).filter(
            operating_models.TrainingAuthorizationCase.amo_id == amo_id,
            operating_models.TrainingAuthorizationCase.candidate_user_id == user_id,
        ).order_by(operating_models.TrainingAuthorizationCase.created_at.desc()).limit(100).all()
        authorization_payload: list[dict[str, Any]] = []
        for case in authorizations:
            readiness = operating_service.compute_authorization_readiness(db, case=case)
            authorization_payload.append({
                "id": str(case.id),
                "status": case.status,
                "application_date": _iso(case.application_date),
                "requested_scope": case.requested_scope,
                "requested_privileges": list(case.requested_privileges or []),
                "decision": case.decision,
                "restrictions": case.restrictions,
                "readiness": {
                    "overall_status": readiness.overall_status,
                    "next_required_action": readiness.next_required_action,
                    "items": [item.model_dump(mode="json") for item in readiness.items],
                },
            })

        technical_authorizations = db.query(governance_models.TrainingTechnicalAuthorisation).filter(
            governance_models.TrainingTechnicalAuthorisation.amo_id == amo_id,
            governance_models.TrainingTechnicalAuthorisation.user_id == user_id,
        ).order_by(
            governance_models.TrainingTechnicalAuthorisation.expiry_date.desc(),
            governance_models.TrainingTechnicalAuthorisation.created_at.desc(),
        ).limit(100).all()

        competence_reviews = db.query(operating_models.TrainingCompetenceReview).filter(
            operating_models.TrainingCompetenceReview.amo_id == amo_id,
            operating_models.TrainingCompetenceReview.candidate_user_id == user_id,
        ).order_by(operating_models.TrainingCompetenceReview.period_end.desc()).limit(100).all()
        experience_reviews = db.query(operating_models.TrainingExperienceReview).filter(
            operating_models.TrainingExperienceReview.amo_id == amo_id,
            operating_models.TrainingExperienceReview.candidate_user_id == user_id,
        ).order_by(operating_models.TrainingExperienceReview.reviewed_on.desc()).limit(100).all()

        course_ids = record_course_ids | assessment_course_ids | workflow_course_ids | {
            str(item.course_id) for item in evaluation.items
        }
        courses = _course_map(db, amo_id=amo_id, course_ids=course_ids)

        department = getattr(person, "department", None)
        payload = {
            "person": {
                "id": str(person.id),
                "staff_code": person.staff_code,
                "full_name": person.full_name,
                "position_title": person.position_title,
                "department_id": str(person.department_id) if person.department_id else None,
                "department": getattr(department, "name", None),
                "active": bool(person.is_active),
                "licence_number": person.licence_number,
                "licence_expires_on": _iso(person.licence_expires_on),
            },
            "compliance": {
                "requirements": requirements,
                "counts": {
                    "overdue": sum(1 for item in requirements if item["status"] == "OVERDUE"),
                    "due_soon": sum(1 for item in requirements if item["status"] == "DUE_SOON"),
                    "not_done": sum(1 for item in requirements if item["status"] == "NOT_DONE"),
                    "current": sum(1 for item in requirements if item["status"] in {"CURRENT", "COMPLIANT"}),
                },
            },
            "records": [
                {
                    "id": str(row.id),
                    "course_id": str(row.course_id),
                    "course_name": courses.get(str(row.course_id)).name if courses.get(str(row.course_id)) else None,
                    "completion_date": _iso(row.completion_date),
                    "valid_until": _iso(row.valid_until),
                    "verification_status": _enum(row.verification_status),
                    "source_status": row.source_status,
                    "record_status": row.record_status,
                    "event_id": str(row.event_id) if row.event_id else None,
                }
                for row in records
            ],
            "assessments": [
                {
                    "id": str(row.id),
                    "template_id": str(row.template_id),
                    "template_name": templates.get(str(row.template_id)).name if templates.get(str(row.template_id)) else None,
                    "assessment_type": templates.get(str(row.template_id)).assessment_type if templates.get(str(row.template_id)) else None,
                    "course_id": str(row.course_id) if row.course_id else None,
                    "course_name": courses.get(str(row.course_id)).name if row.course_id and courses.get(str(row.course_id)) else None,
                    "status": row.status,
                    "outcome": row.outcome,
                    "score": float(row.score) if row.score is not None else None,
                    "performed_at": _iso(row.performed_at),
                    "review_decision": row.review_decision,
                    "reviewed_at": _iso(row.reviewed_at),
                }
                for row in assessments
            ],
            "certificates": [
                {
                    "id": str(row.id),
                    "record_id": str(row.record_id),
                    "certificate_number": row.certificate_number,
                    "status": row.status,
                    "issued_at": _iso(row.issued_at),
                }
                for row in certificates
            ],
            "external_and_workflow_evidence": [
                {
                    "id": str(row.id),
                    "workflow_type": row.workflow_type,
                    "title": row.title,
                    "status": row.status,
                    "course_id": str(row.course_id) if row.course_id else None,
                    "course_name": courses.get(str(row.course_id)).name if row.course_id and courses.get(str(row.course_id)) else None,
                    "due_at": _iso(row.due_at),
                    "submitted_at": _iso(row.submitted_at),
                    "completed_at": _iso(row.completed_at),
                    "provenance": dict(row.provenance or {}),
                }
                for row in workflows
            ],
            "authorization_cases": authorization_payload,
            "technical_training_authorizations": [
                {
                    "id": str(row.id),
                    "privilege_type": row.privilege_type,
                    "status": row.status,
                    "course_ids": list(row.course_ids or []),
                    "aircraft": row.aircraft,
                    "engine": row.engine,
                    "system_scope": row.system_scope,
                    "theoretical_privilege": bool(row.theoretical_privilege),
                    "practical_privilege": bool(row.practical_privilege),
                    "ojt_privilege": bool(row.ojt_privilege),
                    "limitations": row.limitations,
                    "issue_date": _iso(row.issue_date),
                    "expiry_date": _iso(row.expiry_date),
                }
                for row in technical_authorizations
            ],
            "competence_reviews": [
                {
                    "id": str(row.id),
                    "review_type": row.review_type,
                    "period_start": _iso(row.period_start),
                    "period_end": _iso(row.period_end),
                    "outcome": row.outcome,
                    "status": row.status,
                    "reassessment_due": _iso(row.reassessment_due),
                }
                for row in competence_reviews
            ],
            "experience_reviews": [
                {
                    "id": str(row.id),
                    "review_status": row.review_status,
                    "reviewed_on": _iso(row.reviewed_on),
                    "next_review_due": _iso(row.next_review_due),
                }
                for row in experience_reviews
            ],
        }
        db.commit()
        return payload


__all__ = ["install_training_person_360_routes"]
