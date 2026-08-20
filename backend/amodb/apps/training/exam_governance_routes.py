"""Regulated examination routes installed on the canonical Training API."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping

from fastapi import Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import exam_governance
from . import exam_governance_models as exam_models
from . import exam_governance_schemas as schemas
from . import governance_models as models
from . import governance_rules
from . import governance_service
from . import models as legacy_models
from .permissions import TrainingCapability as Cap, require_not_self_approval, require_training_capability, tenant_id_for


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _question_and_revision_rows(db: Session, *, amo_id: str, course_revision_id: str):
    return (
        db.query(models.TrainingQuestionBankItem, models.TrainingQuestionRevision)
        .join(models.TrainingQuestionRevision, models.TrainingQuestionRevision.question_id == models.TrainingQuestionBankItem.id)
        .filter(
            models.TrainingQuestionBankItem.amo_id == amo_id,
            models.TrainingQuestionBankItem.course_revision_id == course_revision_id,
            models.TrainingQuestionBankItem.status == "ACTIVE",
            models.TrainingQuestionRevision.amo_id == amo_id,
            models.TrainingQuestionRevision.status == "ACTIVE",
        )
        .all()
    )


def _candidate_payload(question, revision) -> dict[str, object]:
    return {"question": governance_service._dict(question), "revision": governance_service._dict(revision)}


def _get_blueprint(db: Session, *, amo_id: str, blueprint_id: str):
    return governance_service._tenant_row(db, models.TrainingExamBlueprint, amo_id=amo_id, row_id=blueprint_id, label="Exam blueprint")


def _validate_blueprint_current(blueprint, *, on_date: date) -> list[str]:
    blockers: list[str] = []
    if str(blueprint.status).upper() != "ACTIVE":
        blockers.append("Exam blueprint is not ACTIVE.")
    if blueprint.effective_from and on_date < blueprint.effective_from:
        blockers.append("Exam blueprint is not yet effective.")
    if blueprint.effective_to and on_date > blueprint.effective_to:
        blockers.append("Exam blueprint is superseded/expired.")
    return blockers


def install_training_exam_governance_routes(router_module) -> None:
    router = router_module.router
    if getattr(router_module, "_training_exam_governance_routes_installed", False):
        return
    router_module._training_exam_governance_routes_installed = True

    @router.get("/operating/governance/exams/blueprints", response_model=list[schemas.ExamBlueprintRead])
    def list_exam_blueprints(
        course_revision_id: str | None = None,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_VIEW)),
    ):
        query = db.query(models.TrainingExamBlueprint).filter(models.TrainingExamBlueprint.amo_id == tenant_id_for(current_user))
        if course_revision_id:
            query = query.filter(models.TrainingExamBlueprint.course_revision_id == course_revision_id)
        return query.order_by(models.TrainingExamBlueprint.course_revision_id, models.TrainingExamBlueprint.revision_no.desc()).all()

    @router.post("/operating/governance/exams/blueprints", response_model=schemas.ExamBlueprintRead, status_code=201)
    def create_exam_blueprint(
        payload: schemas.ExamBlueprintCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_CREATE)),
    ):
        amo_id = tenant_id_for(current_user)
        governance_service._tenant_row(db, models.TrainingCourseRevision, amo_id=amo_id, row_id=payload.course_revision_id, label="Course revision")
        row = models.TrainingExamBlueprint(amo_id=amo_id, **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return row

    @router.post("/operating/governance/exams/blueprints/{blueprint_id}/activate", response_model=schemas.ExamBlueprintRead)
    def activate_exam_blueprint(
        blueprint_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_APPROVE)),
    ):
        amo_id = tenant_id_for(current_user)
        row = _get_blueprint(db, amo_id=amo_id, blueprint_id=blueprint_id)
        revision = governance_service._tenant_row(db, models.TrainingCourseRevision, amo_id=amo_id, row_id=row.course_revision_id, label="Course revision")
        if str(revision.status).upper() != "ACTIVE":
            raise HTTPException(status_code=409, detail="Exam blueprint cannot be activated against a non-active course revision.")
        # Blueprint creation does not currently carry an originator column; an
        # independent question author/reviewer boundary is still enforced on each item.
        candidates = [_candidate_payload(q, r) for q, r in _question_and_revision_rows(db, amo_id=amo_id, course_revision_id=str(row.course_revision_id))]
        selection = exam_governance.select_question_revisions(candidates, on_date=row.effective_from or date.today(), selection_rules=row.selection_rules or {})
        if not selection["ready"]:
            raise HTTPException(status_code=409, detail={"code": "EXAM_BLUEPRINT_NOT_GENERATABLE", **selection})
        db.query(models.TrainingExamBlueprint).filter(
            models.TrainingExamBlueprint.amo_id == amo_id,
            models.TrainingExamBlueprint.course_revision_id == row.course_revision_id,
            models.TrainingExamBlueprint.id != row.id,
            models.TrainingExamBlueprint.status == "ACTIVE",
        ).update({models.TrainingExamBlueprint.status: "SUPERSEDED"}, synchronize_session=False)
        row.status = "ACTIVE"; row.approved_by_user_id = str(current_user.id)
        db.commit(); db.refresh(row)
        return row

    @router.post("/operating/governance/exams/forms", status_code=201)
    def create_exam_form(
        payload: schemas.ExamFormCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_CREATE)),
    ):
        amo_id = tenant_id_for(current_user)
        blueprint = _get_blueprint(db, amo_id=amo_id, blueprint_id=payload.blueprint_id)
        candidate_map = {str(revision.id): (question, revision) for question, revision in _question_and_revision_rows(db, amo_id=amo_id, course_revision_id=str(blueprint.course_revision_id))}
        blockers: list[dict[str, object]] = []
        for revision_id in payload.question_revision_ids:
            pair = candidate_map.get(revision_id)
            if not pair:
                blockers.append({"question_revision_id": revision_id, "reasons": ["Question revision is not an ACTIVE item in this blueprint's course revision."]})
                continue
            reasons = governance_rules.question_eligibility_reasons(governance_service._dict(pair[0]), governance_service._dict(pair[1]), on_date=date.today())
            if reasons:
                blockers.append({"question_revision_id": revision_id, "reasons": reasons})
        if blockers:
            raise HTTPException(status_code=409, detail={"code": "EXAM_FORM_BLOCKED", "blockers": blockers})
        row = exam_models.TrainingExamForm(amo_id=amo_id, **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return governance_service._dict(row)

    @router.post("/operating/governance/exams/forms/{form_id}/activate")
    def activate_exam_form(
        form_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_APPROVE)),
    ):
        amo_id = tenant_id_for(current_user)
        form = governance_service._tenant_row(db, exam_models.TrainingExamForm, amo_id=amo_id, row_id=form_id, label="Exam form")
        blueprint = _get_blueprint(db, amo_id=amo_id, blueprint_id=form.blueprint_id)
        blockers = _validate_blueprint_current(blueprint, on_date=date.today())
        if blockers:
            raise HTTPException(status_code=409, detail={"code": "EXAM_FORM_BLOCKED", "blockers": blockers})
        required_count = int((blueprint.selection_rules or {}).get("question_count") or 0)
        if len(form.question_revision_ids or []) != required_count:
            raise HTTPException(status_code=409, detail=f"Exam form contains {len(form.question_revision_ids or [])} questions but blueprint requires {required_count}.")
        form.status = "ACTIVE"; form.approved_by_user_id = str(current_user.id)
        db.commit(); db.refresh(form)
        return governance_service._dict(form)

    @router.post("/operating/governance/exams/generations", response_model=schemas.ExamGenerationRead, status_code=201)
    def generate_exam(
        payload: schemas.ExamGenerationCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_CREATE)),
    ):
        amo_id = tenant_id_for(current_user)
        event = governance_service._tenant_row(db, legacy_models.TrainingEvent, amo_id=amo_id, row_id=payload.event_id, label="Training session")
        blueprint = _get_blueprint(db, amo_id=amo_id, blueprint_id=payload.blueprint_id)
        blockers = _validate_blueprint_current(blueprint, on_date=event.starts_on)
        if blockers:
            raise HTTPException(status_code=409, detail={"code": "EXAM_BLUEPRINT_BLOCKED", "blockers": blockers})
        envelope = db.query(models.TrainingSessionGovernance).filter(models.TrainingSessionGovernance.amo_id == amo_id, models.TrainingSessionGovernance.event_id == event.id).first()
        if not envelope or str(envelope.course_revision_id) != str(blueprint.course_revision_id):
            raise HTTPException(status_code=409, detail="Exam blueprint does not match the governed course revision for this session.")

        excluded: list[dict[str, object]] = []
        if payload.form_id:
            form = governance_service._tenant_row(db, exam_models.TrainingExamForm, amo_id=amo_id, row_id=payload.form_id, label="Exam form")
            if str(form.blueprint_id) != str(blueprint.id) or str(form.status).upper() != "ACTIVE":
                raise HTTPException(status_code=409, detail="Exam form is not an active form for this blueprint.")
            selected_ids = list(form.question_revision_ids or [])
            pairs = db.query(models.TrainingQuestionBankItem, models.TrainingQuestionRevision).join(models.TrainingQuestionRevision, models.TrainingQuestionRevision.question_id == models.TrainingQuestionBankItem.id).filter(
                models.TrainingQuestionBankItem.amo_id == amo_id,
                models.TrainingQuestionRevision.amo_id == amo_id,
                models.TrainingQuestionRevision.id.in_(selected_ids),
            ).all()
            by_id = {str(revision.id): (question, revision) for question, revision in pairs}
            for revision_id in selected_ids:
                pair = by_id.get(revision_id)
                reasons = ["Question revision was not found in this tenant."] if not pair else governance_rules.question_eligibility_reasons(governance_service._dict(pair[0]), governance_service._dict(pair[1]), on_date=event.starts_on)
                if reasons:
                    excluded.append({"question_revision_id": revision_id, "reasons": reasons})
            if excluded:
                raise HTTPException(status_code=409, detail={"code": "EXAM_FORM_SUPERSEDED", "blockers": excluded})
        else:
            candidates = [_candidate_payload(q, r) for q, r in _question_and_revision_rows(db, amo_id=amo_id, course_revision_id=str(blueprint.course_revision_id))]
            selection = exam_governance.select_question_revisions(candidates, on_date=event.starts_on, selection_rules=blueprint.selection_rules or {})
            if not selection["ready"]:
                raise HTTPException(status_code=409, detail={"code": "EXAM_GENERATION_BLOCKED", **selection})
            selected_ids = list(selection["selected_revision_ids"])
            excluded = list(selection["excluded"])

        row = models.TrainingExamGeneration(
            amo_id=amo_id,
            event_id=event.id,
            blueprint_id=blueprint.id,
            generation_code=payload.generation_code,
            question_revision_ids=selected_ids,
            generated_by_user_id=str(current_user.id),
            security_metadata=payload.security_metadata,
        )
        db.add(row)
        questions = db.query(models.TrainingQuestionBankItem).join(models.TrainingQuestionRevision, models.TrainingQuestionRevision.question_id == models.TrainingQuestionBankItem.id).filter(
            models.TrainingQuestionBankItem.amo_id == amo_id,
            models.TrainingQuestionRevision.id.in_(selected_ids),
        ).all()
        for question in questions:
            question.exposure_count = int(question.exposure_count or 0) + 1
            question.last_used_at = _utcnow()
        db.commit(); db.refresh(row)
        return {**governance_service._dict(row), "excluded": excluded}

    @router.post("/operating/governance/exams/attempts", status_code=201)
    def create_exam_attempt(
        payload: schemas.ExamAttemptCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = tenant_id_for(current_user)
        generation = governance_service._tenant_row(db, models.TrainingExamGeneration, amo_id=amo_id, row_id=payload.generation_id, label="Exam generation")
        if str(generation.event_id) != payload.event_id or str(generation.status).upper() != "ACTIVE":
            raise HTTPException(status_code=409, detail="Exam generation is not active for this session.")
        participant = db.query(legacy_models.TrainingEventParticipant).filter(
            legacy_models.TrainingEventParticipant.amo_id == amo_id,
            legacy_models.TrainingEventParticipant.event_id == payload.event_id,
            legacy_models.TrainingEventParticipant.user_id == str(current_user.id),
        ).first()
        if not participant:
            raise HTTPException(status_code=403, detail="Only an enrolled learner may start this examination.")
        blueprint = _get_blueprint(db, amo_id=amo_id, blueprint_id=generation.blueprint_id)
        security_rules = dict(blueprint.security_rules or {})
        result_rules = dict(blueprint.result_rules or {})
        if security_rules.get("proctor_required") and not payload.proctor_user_id:
            raise HTTPException(status_code=409, detail="This examination requires a proctor under the controlled blueprint.")
        existing = db.query(models.TrainingExamAttempt).filter(models.TrainingExamAttempt.amo_id == amo_id, models.TrainingExamAttempt.event_id == payload.event_id, models.TrainingExamAttempt.user_id == str(current_user.id)).order_by(models.TrainingExamAttempt.attempt_no.desc()).all()
        max_attempts = result_rules.get("max_attempts")
        if max_attempts is not None and len(existing) >= int(max_attempts):
            raise HTTPException(status_code=409, detail="Controlled maximum examination attempts has been reached.")
        cooldown_hours = result_rules.get("cooldown_hours")
        if cooldown_hours is not None and existing and existing[0].submitted_at:
            next_allowed = existing[0].submitted_at + timedelta(hours=float(cooldown_hours))
            if _utcnow() < next_allowed:
                raise HTTPException(status_code=409, detail={"code": "EXAM_COOLDOWN", "next_allowed_at": next_allowed.isoformat()})
        attempt_no = len(existing) + 1
        row = models.TrainingExamAttempt(
            amo_id=amo_id, generation_id=generation.id, event_id=payload.event_id, user_id=str(current_user.id),
            attempt_no=attempt_no, status="IN_PROGRESS", started_at=_utcnow(), proctor_user_id=payload.proctor_user_id,
        )
        db.add(row); db.commit(); db.refresh(row)
        return {"id": str(row.id), "event_id": str(row.event_id), "attempt_no": row.attempt_no, "status": row.status, "started_at": row.started_at}

    @router.get("/operating/governance/exams/attempts/{attempt_id}/learner", response_model=schemas.ExamAttemptLearnerRead)
    def learner_exam_attempt(
        attempt_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = tenant_id_for(current_user)
        attempt = governance_service._tenant_row(db, models.TrainingExamAttempt, amo_id=amo_id, row_id=attempt_id, label="Exam attempt")
        if str(attempt.user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="This examination attempt belongs to another learner.")
        generation = governance_service._tenant_row(db, models.TrainingExamGeneration, amo_id=amo_id, row_id=attempt.generation_id, label="Exam generation")
        revisions = db.query(models.TrainingQuestionRevision).filter(models.TrainingQuestionRevision.amo_id == amo_id, models.TrainingQuestionRevision.id.in_(list(generation.question_revision_ids or []))).all()
        by_id = {str(row.id): row for row in revisions}
        questions = []
        for revision_id in generation.question_revision_ids or []:
            revision = by_id.get(str(revision_id))
            if not revision:
                raise HTTPException(status_code=409, detail="The frozen exam form references a missing question revision.")
            questions.append(governance_service.learner_question_projection(revision))
        return {"attempt_id": str(attempt.id), "event_id": str(attempt.event_id), "status": attempt.status, "questions": questions}

    @router.post("/operating/governance/exams/attempts/{attempt_id}/security-events", status_code=201)
    def record_exam_security_event(
        attempt_id: str,
        payload: schemas.ExamSecurityEventCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = tenant_id_for(current_user)
        attempt = governance_service._tenant_row(db, models.TrainingExamAttempt, amo_id=amo_id, row_id=attempt_id, label="Exam attempt")
        if str(attempt.user_id) != str(current_user.id) and not getattr(current_user, "is_amo_admin", False):
            raise HTTPException(status_code=403, detail="You cannot record a security event against another learner's attempt.")
        row = models.TrainingExamSecurityEvent(amo_id=amo_id, attempt_id=attempt.id, recorded_by_user_id=str(current_user.id), **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return governance_service._dict(row)

    @router.post("/operating/governance/exams/attempts/{attempt_id}/submit")
    def submit_exam_attempt(
        attempt_id: str,
        payload: schemas.ExamAttemptSubmit,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = tenant_id_for(current_user)
        attempt = governance_service._tenant_row(db, models.TrainingExamAttempt, amo_id=amo_id, row_id=attempt_id, label="Exam attempt")
        if str(attempt.user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="This examination attempt belongs to another learner.")
        if str(attempt.status).upper() != "IN_PROGRESS":
            raise HTTPException(status_code=409, detail="Only an in-progress examination may be submitted.")
        generation = governance_service._tenant_row(db, models.TrainingExamGeneration, amo_id=amo_id, row_id=attempt.generation_id, label="Exam generation")
        blueprint = _get_blueprint(db, amo_id=amo_id, blueprint_id=generation.blueprint_id)
        selected_ids = [str(value) for value in generation.question_revision_ids or []]
        revisions = db.query(models.TrainingQuestionRevision).filter(models.TrainingQuestionRevision.amo_id == amo_id, models.TrainingQuestionRevision.id.in_(selected_ids)).all()
        by_id = {str(row.id): row for row in revisions}
        total_marks = Decimal("0")
        awarded = Decimal("0")
        manual_pending = False
        for revision_id in selected_ids:
            revision = by_id.get(revision_id)
            if not revision:
                raise HTTPException(status_code=409, detail="The frozen exam form references a missing question revision.")
            total_marks += Decimal(str(revision.marks or 0))
            response = payload.responses.get(revision_id)
            response_payload = response if isinstance(response, Mapping) else {"selected_option": response}
            answer = dict(revision.answer_key_json or {})
            selected = response_payload.get("selected_option")
            correct: bool | None = None
            if "correct_option" in answer:
                correct = str(selected) == str(answer.get("correct_option"))
            elif "correct_options" in answer:
                correct = str(selected) in {str(value) for value in answer.get("correct_options") or []}
            manual_mark = correct is None
            if manual_mark:
                manual_pending = True
                item_award = None
            else:
                item_award = Decimal(str(revision.marks or 0)) if correct else Decimal("0")
                awarded += item_award
            db.add(models.TrainingExamAttemptItem(
                amo_id=amo_id, attempt_id=attempt.id, question_revision_id=revision.id,
                response_json=dict(response_payload), awarded_marks=item_award, correct=correct,
                manual_mark_required=manual_mark,
            ))
        attempt.submitted_at = _utcnow()
        if manual_pending:
            attempt.status = "MANUAL_MARKING_REQUIRED"
            attempt.result = None
            attempt.score = None
        else:
            percent = (awarded / total_marks * Decimal("100")) if total_marks else Decimal("0")
            attempt.score = percent
            pass_mark = (blueprint.result_rules or {}).get("pass_mark")
            if pass_mark is None:
                attempt.status = "REVIEW_REQUIRED"
                attempt.result = None
            else:
                attempt.result = "PASS" if percent >= Decimal(str(pass_mark)) else "FAIL"
                attempt.status = "GRADED"
        db.commit(); db.refresh(attempt)
        return {"attempt_id": str(attempt.id), "status": attempt.status, "score": attempt.score, "result": attempt.result, "manual_marking_required": manual_pending}

    @router.post("/operating/governance/exams/analysis", response_model=schemas.ExamAnalysisRead)
    def run_exam_item_analysis(
        payload: schemas.ExamAnalysisRun,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_REVIEW)),
    ):
        amo_id = tenant_id_for(current_user)
        revision = governance_service._tenant_row(db, models.TrainingQuestionRevision, amo_id=amo_id, row_id=payload.question_revision_id, label="Question revision")
        items = db.query(models.TrainingExamAttemptItem, models.TrainingExamAttempt).join(models.TrainingExamAttempt, models.TrainingExamAttempt.id == models.TrainingExamAttemptItem.attempt_id).filter(
            models.TrainingExamAttemptItem.amo_id == amo_id,
            models.TrainingExamAttemptItem.question_revision_id == revision.id,
            models.TrainingExamAttempt.status.in_(["GRADED", "REVIEWED", "COMPLETED"]),
        ).all()
        response_rows = [
            {
                "selected_option": (item.response_json or {}).get("selected_option"),
                "correct": item.correct,
                "total_score": attempt.score or 0,
            }
            for item, attempt in items
            if item.correct is not None
        ]
        analysis = exam_governance.item_analysis(
            response_rows,
            policy=payload.policy,
            source_superseded=payload.source_superseded,
            complaint_count=payload.complaint_count,
        )
        row = db.query(exam_models.TrainingExamItemAnalysis).filter(
            exam_models.TrainingExamItemAnalysis.amo_id == amo_id,
            exam_models.TrainingExamItemAnalysis.question_revision_id == revision.id,
            exam_models.TrainingExamItemAnalysis.analysis_window == payload.analysis_window,
        ).first()
        if row is None:
            row = exam_models.TrainingExamItemAnalysis(amo_id=amo_id, question_revision_id=revision.id, analysis_window=payload.analysis_window)
            db.add(row)
        for key, value in analysis.items():
            setattr(row, key, value)
        row.computed_at = _utcnow()
        if analysis["review_status"] == "REVIEW_REQUIRED":
            existing_moderation = db.query(exam_models.TrainingExamModeration).filter(
                exam_models.TrainingExamModeration.amo_id == amo_id,
                exam_models.TrainingExamModeration.question_revision_id == revision.id,
                exam_models.TrainingExamModeration.status == "OPEN",
            ).first()
            if not existing_moderation:
                db.add(exam_models.TrainingExamModeration(
                    amo_id=amo_id,
                    question_revision_id=revision.id,
                    reason="; ".join(analysis["review_reasons"]),
                    evidence_json={"analysis_window": payload.analysis_window, "metrics": {key: str(value) if isinstance(value, Decimal) else value for key, value in analysis.items()}},
                    recommendation="Human examination-quality review required. Approved question content has not been altered.",
                    opened_by_user_id=str(current_user.id),
                ))
        db.commit(); db.refresh(row)
        return row

    @router.get("/operating/governance/exams/quality-queue")
    def exam_quality_queue(
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_REVIEW)),
    ):
        amo_id = tenant_id_for(current_user)
        rows = db.query(exam_models.TrainingExamModeration).filter(
            exam_models.TrainingExamModeration.amo_id == amo_id,
            exam_models.TrainingExamModeration.status == "OPEN",
        ).order_by(exam_models.TrainingExamModeration.created_at.asc()).limit(200).all()
        return [governance_service._dict(row) for row in rows]

    @router.post("/operating/governance/exams/moderations", status_code=201)
    def create_moderation(
        payload: schemas.ModerationCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_REVIEW)),
    ):
        amo_id = tenant_id_for(current_user)
        if payload.question_revision_id:
            governance_service._tenant_row(db, models.TrainingQuestionRevision, amo_id=amo_id, row_id=payload.question_revision_id, label="Question revision")
        if payload.generation_id:
            governance_service._tenant_row(db, models.TrainingExamGeneration, amo_id=amo_id, row_id=payload.generation_id, label="Exam generation")
        row = exam_models.TrainingExamModeration(amo_id=amo_id, opened_by_user_id=str(current_user.id), **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return governance_service._dict(row)

    @router.post("/operating/governance/exams/moderations/{moderation_id}/decision")
    def decide_moderation(
        moderation_id: str,
        payload: schemas.ModerationDecision,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_APPROVE)),
    ):
        amo_id = tenant_id_for(current_user)
        row = governance_service._tenant_row(db, exam_models.TrainingExamModeration, amo_id=amo_id, row_id=moderation_id, label="Exam moderation")
        require_not_self_approval(actor_user_id=str(current_user.id), originator_user_id=row.opened_by_user_id, action="decide")
        if str(row.status).upper() != "OPEN":
            raise HTTPException(status_code=409, detail="Exam moderation has already been decided.")
        if row.question_revision_id and payload.decision in {"SUSPEND_PENDING_REVIEW", "RETIRE"}:
            revision = governance_service._tenant_row(db, models.TrainingQuestionRevision, amo_id=amo_id, row_id=row.question_revision_id, label="Question revision")
            question = governance_service._tenant_row(db, models.TrainingQuestionBankItem, amo_id=amo_id, row_id=revision.question_id, label="Question")
            if payload.decision == "SUSPEND_PENDING_REVIEW":
                question.status = "SUSPENDED"
            elif payload.decision == "RETIRE":
                question.status = "RETIRED"
                revision.status = "RETIRED"
        row.status = "DECIDED"; row.decision = payload.decision; row.decision_reason = payload.decision_reason
        row.decided_by_user_id = str(current_user.id); row.decided_at = _utcnow()
        db.commit(); db.refresh(row)
        return governance_service._dict(row)

    @router.post("/operating/governance/exams/appeals", status_code=201)
    def create_exam_appeal(
        payload: schemas.AppealCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = tenant_id_for(current_user)
        attempt = governance_service._tenant_row(db, models.TrainingExamAttempt, amo_id=amo_id, row_id=payload.attempt_id, label="Exam attempt")
        if str(attempt.user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="You may appeal only your own examination attempt.")
        row = exam_models.TrainingExamAppeal(amo_id=amo_id, appellant_user_id=str(current_user.id), **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return governance_service._dict(row)

    @router.post("/operating/governance/exams/appeals/{appeal_id}/decision")
    def decide_exam_appeal(
        appeal_id: str,
        payload: schemas.AppealDecision,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_REVIEW)),
    ):
        amo_id = tenant_id_for(current_user)
        row = governance_service._tenant_row(db, exam_models.TrainingExamAppeal, amo_id=amo_id, row_id=appeal_id, label="Exam appeal")
        require_not_self_approval(actor_user_id=str(current_user.id), originator_user_id=row.appellant_user_id, action="decide")
        if str(row.status).upper() != "SUBMITTED":
            raise HTTPException(status_code=409, detail="Exam appeal has already been decided.")
        row.status = "DECIDED"; row.reviewer_user_id = str(current_user.id); row.decision = payload.decision
        row.decision_reason = payload.decision_reason; row.decided_at = _utcnow()
        db.commit(); db.refresh(row)
        return governance_service._dict(row)
