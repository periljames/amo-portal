from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database import get_db
from ..accounts import models as account_models
from . import compliance
from . import governance_models
from . import models as legacy_models
from . import operating_models
from . import operating_service
from .permissions import TrainingCapability as Cap, require_training_capability, tenant_id_for

UTC = timezone.utc


class SessionCloseoutFinalize(BaseModel):
    note: str | None = Field(None, max_length=4000)


class SessionCloseoutVerify(BaseModel):
    note: str | None = Field(None, max_length=4000)
    issue_certificates: bool = True


def _now() -> datetime:
    return datetime.now(UTC)


def _enum(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().upper()


def _scoped(db: Session, model: type, *, amo_id: str, row_id: str, label: str):
    row = db.query(model).filter(model.id == row_id, model.amo_id == amo_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{label} was not found in this tenant.")
    return row


def _session_context(db: Session, *, amo_id: str, event_id: str):
    event = _scoped(db, legacy_models.TrainingEvent, amo_id=amo_id, row_id=event_id, label="Training session")
    envelope = db.query(governance_models.TrainingSessionGovernance).filter(
        governance_models.TrainingSessionGovernance.amo_id == amo_id,
        governance_models.TrainingSessionGovernance.event_id == event_id,
    ).first()
    if envelope is None:
        raise HTTPException(status_code=409, detail="Training session has no governed course-revision envelope.")
    revision = _scoped(
        db,
        governance_models.TrainingCourseRevision,
        amo_id=amo_id,
        row_id=str(envelope.course_revision_id),
        label="Course revision",
    )
    course = _scoped(db, legacy_models.TrainingCourse, amo_id=amo_id, row_id=str(event.course_id), label="Course")
    return event, envelope, revision, course


def _certificate_required(revision, course) -> bool:
    rules = dict(revision.certificate_rules or {})
    if "required" in rules:
        return bool(rules.get("required"))
    policy = _enum(course.certificate_policy)
    return policy in {"ON_COMPLETION", "REQUIRED"}


def _learner_evidence(db: Session, *, amo_id: str, event, revision, course, user_id: str) -> dict[str, Any]:
    required_modules = db.query(governance_models.TrainingCourseModule).filter(
        governance_models.TrainingCourseModule.amo_id == amo_id,
        governance_models.TrainingCourseModule.course_revision_id == revision.id,
        governance_models.TrainingCourseModule.required.is_(True),
    ).all()
    required_module_ids = {str(row.id) for row in required_modules}
    attendance_rows = db.query(governance_models.TrainingModuleAttendance).filter(
        governance_models.TrainingModuleAttendance.amo_id == amo_id,
        governance_models.TrainingModuleAttendance.event_id == event.id,
        governance_models.TrainingModuleAttendance.user_id == user_id,
    ).all()
    completed_module_ids = {
        str(row.module_id)
        for row in attendance_rows
        if _enum(row.status) in {"ATTENDED", "COMPLETED", "PRESENT"}
    }

    required_tasks = db.query(governance_models.TrainingPracticalTask).filter(
        governance_models.TrainingPracticalTask.amo_id == amo_id,
        governance_models.TrainingPracticalTask.course_revision_id == revision.id,
        governance_models.TrainingPracticalTask.required.is_(True),
    ).all()
    required_task_ids = {str(row.id) for row in required_tasks}
    practical_rows = db.query(governance_models.TrainingPracticalAssessment).filter(
        governance_models.TrainingPracticalAssessment.amo_id == amo_id,
        governance_models.TrainingPracticalAssessment.event_id == event.id,
        governance_models.TrainingPracticalAssessment.user_id == user_id,
    ).all()
    passed_task_ids = {str(row.practical_task_id) for row in practical_rows if _enum(row.result) == "PASS"}

    assessments = db.query(operating_models.TrainingAssessmentInstance).filter(
        operating_models.TrainingAssessmentInstance.amo_id == amo_id,
        operating_models.TrainingAssessmentInstance.event_id == event.id,
        operating_models.TrainingAssessmentInstance.candidate_user_id == user_id,
        operating_models.TrainingAssessmentInstance.course_id == event.course_id,
    ).all()
    passed_assessments = [
        row
        for row in assessments
        if _enum(row.status) in {"APPROVED", "COMPLETED"}
        and _enum(row.outcome) in {"PASS", "PASSED", "COMPETENT", "SATISFACTORY"}
    ]

    participant = db.query(legacy_models.TrainingEventParticipant).filter(
        legacy_models.TrainingEventParticipant.amo_id == amo_id,
        legacy_models.TrainingEventParticipant.event_id == event.id,
        legacy_models.TrainingEventParticipant.user_id == user_id,
    ).first()

    blockers: list[str] = []
    missing_modules = sorted(required_module_ids - completed_module_ids)
    if missing_modules:
        blockers.append(f"Required module attendance incomplete: {', '.join(missing_modules)}")
    missing_tasks = sorted(required_task_ids - passed_task_ids)
    if missing_tasks:
        blockers.append(f"Required practical tasks not passed: {', '.join(missing_tasks)}")
    if bool(course.attendance_required) and not required_module_ids:
        if participant is None or _enum(participant.status) != "ATTENDED":
            blockers.append("Required session attendance is not recorded as ATTENDED.")
    if bool(course.assessment_required) and not passed_assessments:
        blockers.append("Required assessment has no approved/passed canonical outcome.")

    completion_rules = dict(revision.completion_rules or {})
    required_assessment_types = {
        str(value).strip().upper()
        for value in completion_rules.get("required_assessment_types", [])
        if str(value).strip()
    }
    if required_assessment_types:
        templates = {
            str(row.id): row
            for row in db.query(operating_models.TrainingAssessmentTemplate).filter(
                operating_models.TrainingAssessmentTemplate.amo_id == amo_id,
                operating_models.TrainingAssessmentTemplate.id.in_([str(item.template_id) for item in assessments] or [""]),
            ).all()
        }
        passed_types = {
            _enum(templates.get(str(item.template_id)).assessment_type)
            for item in passed_assessments
            if templates.get(str(item.template_id)) is not None
        }
        missing_types = sorted(required_assessment_types - passed_types)
        if missing_types:
            blockers.append(f"Required assessment types not passed: {', '.join(missing_types)}")

    latest_score = None
    scored = [row for row in passed_assessments if row.score is not None]
    if scored:
        latest = max(scored, key=lambda row: row.performed_at or row.created_at)
        latest_score = float(latest.score)

    return {
        "user_id": user_id,
        "required_module_ids": sorted(required_module_ids),
        "completed_module_ids": sorted(completed_module_ids),
        "required_practical_task_ids": sorted(required_task_ids),
        "passed_practical_task_ids": sorted(passed_task_ids),
        "passed_assessment_ids": [str(row.id) for row in passed_assessments],
        "assessment_score": latest_score,
        "blockers": blockers,
        "completed": not blockers,
    }


def _upsert_closeout(db: Session, *, amo_id: str, event, revision, course):
    closeout = db.query(governance_models.TrainingSessionCloseout).filter(
        governance_models.TrainingSessionCloseout.amo_id == amo_id,
        governance_models.TrainingSessionCloseout.event_id == event.id,
    ).first()
    if closeout is None:
        closeout = governance_models.TrainingSessionCloseout(
            amo_id=amo_id,
            event_id=event.id,
            status="DRAFT",
            summary_json={},
        )
        db.add(closeout)
        db.flush()

    participant_ids = [
        str(row.user_id)
        for row in db.query(legacy_models.TrainingEventParticipant).filter(
            legacy_models.TrainingEventParticipant.amo_id == amo_id,
            legacy_models.TrainingEventParticipant.event_id == event.id,
            legacy_models.TrainingEventParticipant.status.notin_([
                legacy_models.TrainingParticipantStatus.CANCELLED,
                legacy_models.TrainingParticipantStatus.DEFERRED,
                legacy_models.TrainingParticipantStatus.WAITLISTED,
            ]),
        ).all()
    ]
    existing = {
        str(row.user_id): row
        for row in db.query(governance_models.TrainingLearnerCloseout).filter(
            governance_models.TrainingLearnerCloseout.amo_id == amo_id,
            governance_models.TrainingLearnerCloseout.event_id == event.id,
        ).all()
    }
    required_certificate = _certificate_required(revision, course)
    rows: list[governance_models.TrainingLearnerCloseout] = []
    for user_id in participant_ids:
        evidence = _learner_evidence(db, amo_id=amo_id, event=event, revision=revision, course=course, user_id=user_id)
        row = existing.get(user_id)
        if row is None:
            row = governance_models.TrainingLearnerCloseout(
                amo_id=amo_id,
                closeout_id=closeout.id,
                event_id=event.id,
                user_id=user_id,
            )
            db.add(row)
        row.completed = bool(evidence["completed"])
        row.status = "READY" if row.completed else "BLOCKED"
        row.blockers_json = list(evidence["blockers"])
        row.decision_json = {
            **dict(row.decision_json or {}),
            "evidence": {key: value for key, value in evidence.items() if key not in {"blockers", "completed"}},
            "certificate_required": required_certificate,
        }
        row.certificate_eligible = bool(row.completed and required_certificate)
        rows.append(row)
    db.flush()
    closeout.summary_json = {
        "course_revision_id": str(revision.id),
        "participant_count": len(rows),
        "completed_count": sum(1 for row in rows if row.completed),
        "blocked_count": sum(1 for row in rows if not row.completed),
        "certificate_eligible_count": sum(1 for row in rows if row.certificate_eligible),
    }
    return closeout, rows


def _closeout_payload(closeout, learners) -> dict[str, Any]:
    return {
        "id": str(closeout.id),
        "event_id": str(closeout.event_id),
        "status": closeout.status,
        "summary": dict(closeout.summary_json or {}),
        "closed_by_user_id": str(closeout.closed_by_user_id) if closeout.closed_by_user_id else None,
        "closed_at": closeout.closed_at,
        "learners": [
            {
                "id": str(row.id),
                "user_id": str(row.user_id),
                "status": row.status,
                "completed": bool(row.completed),
                "certificate_eligible": bool(row.certificate_eligible),
                "blockers": list(row.blockers_json or []),
                "decision": dict(row.decision_json or {}),
            }
            for row in learners
        ],
    }


def install_training_session_closeout_routes(router_module) -> None:
    router = router_module.router
    if getattr(router, "_training_session_closeout_routes_installed", False):
        return
    router._training_session_closeout_routes_installed = True

    @router.get("/operating/governance/events/{event_id}/closeout")
    def read_closeout(
        event_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SESSION_VIEW)),
    ):
        amo_id = tenant_id_for(current_user)
        event, envelope, revision, course = _session_context(db, amo_id=amo_id, event_id=event_id)
        closeout, learners = _upsert_closeout(db, amo_id=amo_id, event=event, revision=revision, course=course)
        db.commit()
        return _closeout_payload(closeout, learners)

    @router.post("/operating/governance/events/{event_id}/closeout/refresh")
    def refresh_closeout(
        event_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SESSION_CLOSE)),
    ):
        amo_id = tenant_id_for(current_user)
        event, envelope, revision, course = _session_context(db, amo_id=amo_id, event_id=event_id)
        closeout, learners = _upsert_closeout(db, amo_id=amo_id, event=event, revision=revision, course=course)
        if closeout.closed_at:
            raise HTTPException(status_code=409, detail="Closed session evidence cannot be silently recalculated. Reopen through a controlled correction workflow.")
        router_module._audit(db, amo_id=amo_id, actor_user_id=str(current_user.id), action="SESSION_CLOSEOUT_REFRESH", entity_type="TrainingSessionCloseout", entity_id=str(closeout.id), details=dict(closeout.summary_json or {}))
        db.commit()
        return _closeout_payload(closeout, learners)

    @router.post("/operating/governance/events/{event_id}/closeout/finalize")
    def finalize_closeout(
        event_id: str,
        payload: SessionCloseoutFinalize,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SESSION_CLOSE)),
    ):
        amo_id = tenant_id_for(current_user)
        event, envelope, revision, course = _session_context(db, amo_id=amo_id, event_id=event_id)
        closeout, learners = _upsert_closeout(db, amo_id=amo_id, event=event, revision=revision, course=course)
        if closeout.closed_at:
            return _closeout_payload(closeout, learners)

        completion_date = event.ends_on or event.starts_on
        valid_until = compliance.add_months(completion_date, int(course.frequency_months)) if course.frequency_months else None
        for learner in learners:
            if not learner.completed:
                continue
            existing_record = db.query(legacy_models.TrainingRecord).filter(
                legacy_models.TrainingRecord.amo_id == amo_id,
                legacy_models.TrainingRecord.event_id == event.id,
                legacy_models.TrainingRecord.course_id == event.course_id,
                legacy_models.TrainingRecord.user_id == learner.user_id,
            ).first()
            if existing_record is None:
                evidence = dict((learner.decision_json or {}).get("evidence") or {})
                score = evidence.get("assessment_score")
                existing_record = legacy_models.TrainingRecord(
                    amo_id=amo_id,
                    user_id=learner.user_id,
                    course_id=event.course_id,
                    event_id=event.id,
                    completion_date=completion_date,
                    valid_until=valid_until,
                    exam_score=int(round(float(score))) if score is not None else None,
                    remarks=payload.note,
                    verification_status=legacy_models.TrainingRecordVerificationStatus.PENDING,
                    is_manual_entry=False,
                    source_status="GOVERNED_SESSION_CLOSEOUT",
                    record_status="ACTIVE",
                    created_by_user_id=str(current_user.id),
                )
                db.add(existing_record)
                db.flush()
            learner.decision_json = {**dict(learner.decision_json or {}), "record_id": str(existing_record.id)}

        closeout.status = "CLOSED_WITH_EXCEPTIONS" if any(not row.completed for row in learners) else "CLOSED"
        closeout.closed_by_user_id = str(current_user.id)
        closeout.closed_at = _now()
        envelope.status = "COMPLETED"
        event.status = legacy_models.TrainingEventStatus.COMPLETED
        closeout.summary_json = {**dict(closeout.summary_json or {}), "closeout_note": payload.note}
        router_module._audit(db, amo_id=amo_id, actor_user_id=str(current_user.id), action="SESSION_CLOSEOUT_FINALIZE", entity_type="TrainingSessionCloseout", entity_id=str(closeout.id), details=dict(closeout.summary_json or {}))
        db.commit()
        return _closeout_payload(closeout, learners)

    @router.post("/operating/governance/events/{event_id}/closeout/verify")
    def verify_closeout(
        event_id: str,
        payload: SessionCloseoutVerify,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.CERTIFICATE_ISSUE)),
    ):
        amo_id = tenant_id_for(current_user)
        event, envelope, revision, course = _session_context(db, amo_id=amo_id, event_id=event_id)
        closeout = db.query(governance_models.TrainingSessionCloseout).filter(
            governance_models.TrainingSessionCloseout.amo_id == amo_id,
            governance_models.TrainingSessionCloseout.event_id == event_id,
        ).first()
        if closeout is None or closeout.closed_at is None:
            raise HTTPException(status_code=409, detail="Session must be finalized before completion records can be independently verified.")
        if str(closeout.closed_by_user_id or "") == str(current_user.id):
            raise HTTPException(status_code=409, detail="The user who finalized session close-out cannot verify the same completion records or issue their certificates.")
        learners = db.query(governance_models.TrainingLearnerCloseout).filter(
            governance_models.TrainingLearnerCloseout.amo_id == amo_id,
            governance_models.TrainingLearnerCloseout.closeout_id == closeout.id,
        ).all()
        from .router import _issue_certificate_for_record

        issued: list[dict[str, str]] = []
        verified = 0
        for learner in learners:
            if not learner.completed:
                continue
            record_id = str((learner.decision_json or {}).get("record_id") or "")
            record = _scoped(db, legacy_models.TrainingRecord, amo_id=amo_id, row_id=record_id, label="Training completion record")
            if str(record.created_by_user_id or "") == str(current_user.id):
                raise HTTPException(status_code=409, detail="A completion-record creator cannot verify the same record.")
            record.verification_status = legacy_models.TrainingRecordVerificationStatus.VERIFIED
            record.verified_by_user_id = str(current_user.id)
            record.verified_at = _now()
            record.verification_comment = payload.note
            verified += 1
            decision = dict(learner.decision_json or {})
            if payload.issue_certificates and learner.certificate_eligible:
                current_issue = db.query(legacy_models.TrainingCertificateIssue).filter(
                    legacy_models.TrainingCertificateIssue.amo_id == amo_id,
                    legacy_models.TrainingCertificateIssue.record_id == record.id,
                    legacy_models.TrainingCertificateIssue.status == "VALID",
                ).order_by(legacy_models.TrainingCertificateIssue.issued_at.desc()).first()
                if current_issue is None:
                    blockers = operating_service.completion_gate(db, record=record)
                    if blockers:
                        raise HTTPException(status_code=409, detail={"code": "CERTIFICATE_COMPLETION_GATE", "record_id": str(record.id), "blockers": blockers})
                    current_issue = _issue_certificate_for_record(
                        db,
                        record=record,
                        amo_id=amo_id,
                        actor_user_id=str(current_user.id),
                    )
                decision.update({"certificate_issue_id": str(current_issue.id), "certificate_number": current_issue.certificate_number})
                issued.append({"record_id": str(record.id), "certificate_issue_id": str(current_issue.id), "certificate_number": current_issue.certificate_number})
            learner.decision_json = decision
            learner.status = "VERIFIED"

        closeout.status = "VERIFIED"
        closeout.summary_json = {
            **dict(closeout.summary_json or {}),
            "verified_count": verified,
            "issued_certificate_count": len(issued),
            "verification_note": payload.note,
            "verified_by_user_id": str(current_user.id),
            "verified_at": _now().isoformat(),
        }
        router_module._audit(db, amo_id=amo_id, actor_user_id=str(current_user.id), action="SESSION_CLOSEOUT_VERIFY", entity_type="TrainingSessionCloseout", entity_id=str(closeout.id), details={"verified": verified, "issued": len(issued)})
        db.commit()
        return {**_closeout_payload(closeout, learners), "verified_records": verified, "issued_certificates": issued}


__all__ = ["install_training_session_closeout_routes"]
