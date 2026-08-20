from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal, Mapping

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import assessment_policy_models
from . import operating_models
from .permissions import TrainingCapability as Cap, require_training_capability, tenant_id_for

UTC = timezone.utc


class AssessmentAttemptPolicyWrite(BaseModel):
    attempt_limit: int = Field(..., ge=1, le=20)
    time_limit_minutes: int | None = Field(None, ge=1, le=1440)
    cooldown_hours: int = Field(..., ge=0, le=720)
    randomize_questions: bool
    question_count: int | None = Field(None, ge=1, le=500)


class AssessmentAutosave(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)
    client_revision: int | None = Field(None, ge=0)


class AssessmentReviewPayload(BaseModel):
    outcome: Literal["PASSED", "FAILED", "REVIEW_REQUIRED"]
    score: Decimal | None = Field(None, ge=0, le=100)
    comments: str = Field(..., min_length=2, max_length=4000)
    proctor_signoff: dict[str, Any] = Field(default_factory=dict)
    moderation_decision: str | None = Field(None, max_length=1000)


class AssessmentAppealPayload(BaseModel):
    reason: str = Field(..., min_length=2, max_length=4000)


def _now() -> datetime:
    return datetime.now(UTC)


def _enum(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().upper()


def _scoped(db: Session, model: type, *, amo_id: str, row_id: str, label: str):
    row = db.query(model).filter(model.id == row_id, model.amo_id == amo_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{label} was not found in this tenant.")
    return row


def _audit(router_module, db: Session, *, current_user: account_models.User, action: str, entity_type: str, entity_id: str, details: dict[str, Any]) -> None:
    router_module._audit(
        db,
        amo_id=tenant_id_for(current_user),
        actor_user_id=str(current_user.id),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )


def _policy_payload(row: assessment_policy_models.TrainingAssessmentAttemptPolicy) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "template_id": str(row.template_id),
        "status": row.status,
        "attempt_limit": row.attempt_limit,
        "time_limit_minutes": row.time_limit_minutes,
        "cooldown_hours": row.cooldown_hours,
        "randomize_questions": bool(row.randomize_questions),
        "question_count": row.question_count,
        "approved_by_user_id": str(row.approved_by_user_id) if row.approved_by_user_id else None,
        "approved_at": row.approved_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _template(db: Session, *, amo_id: str, template_id: str):
    return _scoped(
        db,
        operating_models.TrainingAssessmentTemplate,
        amo_id=amo_id,
        row_id=template_id,
        label="Assessment template",
    )


def _active_policy(db: Session, *, amo_id: str, template_id: str):
    row = db.query(assessment_policy_models.TrainingAssessmentAttemptPolicy).filter(
        assessment_policy_models.TrainingAssessmentAttemptPolicy.amo_id == amo_id,
        assessment_policy_models.TrainingAssessmentAttemptPolicy.template_id == template_id,
    ).first()
    if row is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ASSESSMENT_POLICY_MISSING",
                "message": "This assessment template has no tenant-defined attempt policy. Configure and approve the policy before assigning learner attempts.",
            },
        )
    if _enum(row.status) != "ACTIVE":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ASSESSMENT_POLICY_NOT_ACTIVE",
                "message": "The assessment attempt policy is not approved and active.",
                "status": row.status,
            },
        )
    return row


def _validate_template_for_attempt(template) -> None:
    today = date.today()
    if not bool(template.active):
        raise HTTPException(status_code=409, detail="Assessment template is inactive.")
    if template.effective_from and today < template.effective_from:
        raise HTTPException(status_code=409, detail="Assessment template is not yet effective.")
    if template.effective_to and today > template.effective_to:
        raise HTTPException(status_code=409, detail="Assessment template is expired or superseded.")
    if _enum(template.outcome_scheme) in {"NUMERIC", "PASS_FAIL"} and template.pass_threshold is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ASSESSMENT_THRESHOLD_MISSING",
                "message": "Numeric/pass-fail assessment templates require an explicit tenant-approved pass threshold.",
            },
        )


def _question_snapshot(db: Session, *, instance, attempt_no: int, policy) -> list[dict[str, Any]]:
    questions = db.query(operating_models.TrainingAssessmentQuestion).filter(
        operating_models.TrainingAssessmentQuestion.amo_id == instance.amo_id,
        operating_models.TrainingAssessmentQuestion.template_id == instance.template_id,
        operating_models.TrainingAssessmentQuestion.active.is_(True),
    ).order_by(operating_models.TrainingAssessmentQuestion.sequence_no.asc()).all()
    if not questions:
        raise HTTPException(status_code=409, detail="Assessment template has no active questions/criteria.")
    if policy.question_count is not None and policy.question_count > len(questions):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ASSESSMENT_POLICY_QUESTION_COUNT",
                "message": "Approved assessment question count exceeds the active controlled question set.",
                "configured": policy.question_count,
                "available": len(questions),
            },
        )
    if policy.randomize_questions:
        seed = int(hashlib.sha256(f"{instance.id}:{attempt_no}".encode()).hexdigest()[:16], 16)
        random.Random(seed).shuffle(questions)
    if policy.question_count is not None:
        questions = questions[: policy.question_count]
    return [
        {
            "id": str(question.id),
            "sequence_no": question.sequence_no,
            "question_text": question.question_text,
            "response_type": question.response_type,
            "answer_options": list(question.answer_options or []),
            "marks": float(question.marks or 0),
            "mandatory": bool(question.mandatory),
            "manual_reference": question.manual_reference,
        }
        for question in questions
    ]


def _assessment_read(db: Session, instance, *, include_answers: bool) -> dict[str, Any]:
    template = _template(db, amo_id=str(instance.amo_id), template_id=str(instance.template_id))
    results = dict(instance.results or {})
    engine = dict(results.get("_engine") or {})
    payload: dict[str, Any] = {
        "id": str(instance.id),
        "status": instance.status,
        "outcome": instance.outcome,
        "score": float(instance.score) if instance.score is not None else None,
        "assessment_type": template.assessment_type,
        "template_name": template.name,
        "candidate_user_id": str(instance.candidate_user_id),
        "course_id": str(instance.course_id) if instance.course_id else None,
        "planned_at": instance.planned_at,
        "performed_at": instance.performed_at,
        "attempt": engine,
        "questions": engine.get("questions") or [],
        "comments": instance.comments,
    }
    if include_answers:
        payload["answers"] = results.get("answers") or {}
    return payload


def _answer_value(answer: Any) -> Any:
    if isinstance(answer, Mapping):
        for key in ("selected_option", "value", "answer"):
            if key in answer:
                return answer[key]
    return answer


def _normalize_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip().casefold()


def _is_objective_correct(question, answer: Any) -> bool | None:
    if question.answer_key is None:
        return None
    response_type = _enum(question.response_type)
    key = question.answer_key
    if response_type == "MULTI_CHOICE":
        expected = key.get("values") if isinstance(key, Mapping) else key
        actual = answer.get("selected_options") if isinstance(answer, Mapping) else answer
        if not isinstance(expected, (list, tuple, set)) or not isinstance(actual, (list, tuple, set)):
            return None
        return {_normalize_scalar(value) for value in actual} == {_normalize_scalar(value) for value in expected}
    if response_type not in {"SINGLE_CHOICE", "MCQ", "MULTIPLE_CHOICE", "BOOLEAN", "TRUE_FALSE", "NUMBER"}:
        return None
    expected = key.get("value") if isinstance(key, Mapping) and "value" in key else key
    actual = _answer_value(answer)
    return _normalize_scalar(actual) == _normalize_scalar(expected)


def _workflow_appeal(db: Session, *, instance, user: account_models.User, reason: str):
    amo_id = tenant_id_for(user)
    idempotency_key = f"assessment-appeal:{instance.id}"
    existing = db.query(operating_models.TrainingWorkflowInstance).filter(
        operating_models.TrainingWorkflowInstance.amo_id == amo_id,
        operating_models.TrainingWorkflowInstance.workflow_type == "ASSESSMENT_APPEAL",
        operating_models.TrainingWorkflowInstance.idempotency_key == idempotency_key,
    ).first()
    if existing:
        return existing
    row = operating_models.TrainingWorkflowInstance(
        amo_id=amo_id,
        workflow_type="ASSESSMENT_APPEAL",
        title="Assessment appeal",
        status="SUBMITTED",
        subject_user_id=str(user.id),
        course_id=str(instance.course_id) if instance.course_id else None,
        authorization_case_id=str(instance.authorization_case_id) if instance.authorization_case_id else None,
        data_json={
            "assessment_id": str(instance.id),
            "reason": reason,
            "outcome": instance.outcome,
            "score": float(instance.score) if instance.score is not None else None,
        },
        validation_result={},
        provenance={"module": "training", "canonical_assessment": True},
        idempotency_key=idempotency_key,
        revision_no=1,
        submitted_at=_now(),
        created_by_user_id=str(user.id),
    )
    db.add(row)
    db.flush()
    return row


def install_training_canonical_assessment_routes(router_module) -> None:
    router = router_module.router
    if getattr(router, "_canonical_assessment_routes_installed", False):
        return
    router._canonical_assessment_routes_installed = True

    @router.get("/operating/assessment-templates/{template_id}/attempt-policy")
    def read_attempt_policy(
        template_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_VIEW)),
    ):
        amo_id = tenant_id_for(current_user)
        _template(db, amo_id=amo_id, template_id=template_id)
        row = db.query(assessment_policy_models.TrainingAssessmentAttemptPolicy).filter(
            assessment_policy_models.TrainingAssessmentAttemptPolicy.amo_id == amo_id,
            assessment_policy_models.TrainingAssessmentAttemptPolicy.template_id == template_id,
        ).first()
        return _policy_payload(row) if row else None

    @router.put("/operating/assessment-templates/{template_id}/attempt-policy")
    def save_attempt_policy(
        template_id: str,
        payload: AssessmentAttemptPolicyWrite,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_CREATE)),
    ):
        amo_id = tenant_id_for(current_user)
        template = _template(db, amo_id=amo_id, template_id=template_id)
        _validate_template_for_attempt(template)
        active_question_count = db.query(operating_models.TrainingAssessmentQuestion).filter(
            operating_models.TrainingAssessmentQuestion.amo_id == amo_id,
            operating_models.TrainingAssessmentQuestion.template_id == template_id,
            operating_models.TrainingAssessmentQuestion.active.is_(True),
        ).count()
        if payload.question_count is not None and payload.question_count > active_question_count:
            raise HTTPException(status_code=422, detail="Configured question count exceeds the template's active controlled questions.")
        row = db.query(assessment_policy_models.TrainingAssessmentAttemptPolicy).filter(
            assessment_policy_models.TrainingAssessmentAttemptPolicy.amo_id == amo_id,
            assessment_policy_models.TrainingAssessmentAttemptPolicy.template_id == template_id,
        ).first()
        values = payload.model_dump()
        if row is None:
            row = assessment_policy_models.TrainingAssessmentAttemptPolicy(
                amo_id=amo_id,
                template_id=template_id,
                status="DRAFT",
                created_by_user_id=str(current_user.id),
                updated_by_user_id=str(current_user.id),
                **values,
            )
            db.add(row)
        else:
            if _enum(row.status) == "ACTIVE":
                row.status = "DRAFT"
                row.approved_by_user_id = None
                row.approved_at = None
            for key, value in values.items():
                setattr(row, key, value)
            row.updated_by_user_id = str(current_user.id)
        db.flush()
        _audit(router_module, db, current_user=current_user, action="ASSESSMENT_POLICY_SAVE", entity_type="TrainingAssessmentAttemptPolicy", entity_id=str(row.id), details={**values, "status": row.status})
        db.commit(); db.refresh(row)
        return _policy_payload(row)

    @router.post("/operating/assessment-templates/{template_id}/attempt-policy/activate")
    def activate_attempt_policy(
        template_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_APPROVE)),
    ):
        amo_id = tenant_id_for(current_user)
        template = _template(db, amo_id=amo_id, template_id=template_id)
        _validate_template_for_attempt(template)
        row = db.query(assessment_policy_models.TrainingAssessmentAttemptPolicy).filter(
            assessment_policy_models.TrainingAssessmentAttemptPolicy.amo_id == amo_id,
            assessment_policy_models.TrainingAssessmentAttemptPolicy.template_id == template_id,
        ).first()
        if row is None:
            raise HTTPException(status_code=409, detail="Assessment attempt policy must be configured before approval.")
        if row.updated_by_user_id and str(row.updated_by_user_id) == str(current_user.id) and str(row.created_by_user_id or "") == str(current_user.id):
            raise HTTPException(status_code=409, detail="Assessment policy author cannot approve their own initial policy revision.")
        row.status = "ACTIVE"
        row.approved_by_user_id = str(current_user.id)
        row.approved_at = _now()
        _audit(router_module, db, current_user=current_user, action="ASSESSMENT_POLICY_ACTIVATE", entity_type="TrainingAssessmentAttemptPolicy", entity_id=str(row.id), details={"template_id": template_id})
        db.commit(); db.refresh(row)
        return _policy_payload(row)

    @router.post("/assessments/{assessment_id}/attempt/start")
    def start_assessment_attempt(
        assessment_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = tenant_id_for(current_user)
        instance = _scoped(db, operating_models.TrainingAssessmentInstance, amo_id=amo_id, row_id=assessment_id, label="Assessment")
        if str(instance.candidate_user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Only the assigned candidate may start this assessment.")
        template = _template(db, amo_id=amo_id, template_id=str(instance.template_id))
        _validate_template_for_attempt(template)
        policy = _active_policy(db, amo_id=amo_id, template_id=str(template.id))
        results = dict(instance.results or {})
        engine = dict(results.get("_engine") or {})
        previous_attempt = int(engine.get("attempt_no") or 0)
        if instance.status == "IN_PROGRESS":
            return _assessment_read(db, instance, include_answers=True)
        if _enum(instance.outcome) == "PASSED":
            raise HTTPException(status_code=409, detail="A passed assessment cannot be restarted as another attempt.")
        if instance.status in {"SUBMITTED", "REVIEW_REQUIRED"}:
            raise HTTPException(status_code=409, detail="Assessment is awaiting controlled review and cannot be restarted.")
        if previous_attempt >= policy.attempt_limit:
            raise HTTPException(status_code=409, detail="Assessment attempt limit has been reached.")
        cooldown_until_raw = engine.get("cooldown_until")
        if cooldown_until_raw:
            cooldown_until = datetime.fromisoformat(str(cooldown_until_raw))
            if cooldown_until.tzinfo is None:
                cooldown_until = cooldown_until.replace(tzinfo=UTC)
            if _now() < cooldown_until:
                raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_COOLDOWN", "next_allowed_at": cooldown_until.isoformat()})
        attempt_no = previous_attempt + 1
        started = _now()
        deadline = started + timedelta(minutes=policy.time_limit_minutes) if policy.time_limit_minutes is not None else None
        questions = _question_snapshot(db, instance=instance, attempt_no=attempt_no, policy=policy)
        engine = {
            "attempt_no": attempt_no,
            "attempt_limit": policy.attempt_limit,
            "started_at": started.isoformat(),
            "deadline_at": deadline.isoformat() if deadline else None,
            "time_limit_minutes": policy.time_limit_minutes,
            "cooldown_hours": policy.cooldown_hours,
            "randomize_questions": bool(policy.randomize_questions),
            "question_count": policy.question_count,
            "policy_id": str(policy.id),
            "policy_approved_at": policy.approved_at.isoformat() if policy.approved_at else None,
            "questions": questions,
            "autosave_revision": 0,
        }
        results["_engine"] = engine
        results["answers"] = {}
        results.setdefault("_attempt_history", [])
        instance.results = results
        instance.status = "IN_PROGRESS"
        instance.outcome = None
        _audit(router_module, db, current_user=current_user, action="ASSESSMENT_ATTEMPT_START", entity_type="TrainingAssessmentInstance", entity_id=str(instance.id), details={"attempt_no": attempt_no, "deadline_at": engine["deadline_at"], "policy_id": str(policy.id)})
        db.commit()
        return _assessment_read(db, instance, include_answers=True)

    def assert_open_attempt(db: Session, instance, current_user: account_models.User) -> tuple[dict[str, Any], dict[str, Any]]:
        if str(instance.candidate_user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Only the candidate may modify this assessment attempt.")
        if instance.status != "IN_PROGRESS":
            raise HTTPException(status_code=409, detail="Assessment is not currently in progress.")
        results = dict(instance.results or {})
        engine = dict(results.get("_engine") or {})
        deadline_raw = engine.get("deadline_at")
        if deadline_raw:
            deadline = datetime.fromisoformat(str(deadline_raw))
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            if _now() > deadline:
                instance.status = "TIMED_OUT"
                instance.outcome = "FAILED"
                instance.performed_at = _now()
                cooldown_hours = int(engine.get("cooldown_hours") or 0)
                engine["cooldown_until"] = (_now() + timedelta(hours=cooldown_hours)).isoformat() if cooldown_hours else _now().isoformat()
                engine["timed_out_at"] = _now().isoformat()
                results["_engine"] = engine
                instance.results = results
                db.flush()
                raise HTTPException(status_code=409, detail="Assessment time limit has expired.")
        return results, engine

    @router.put("/assessments/{assessment_id}/attempt/autosave")
    def autosave_assessment_attempt(
        assessment_id: str,
        payload: AssessmentAutosave,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = tenant_id_for(current_user)
        instance = _scoped(db, operating_models.TrainingAssessmentInstance, amo_id=amo_id, row_id=assessment_id, label="Assessment")
        try:
            results, engine = assert_open_attempt(db, instance, current_user)
        except HTTPException:
            db.commit()
            raise
        if payload.client_revision is not None and payload.client_revision < int(engine.get("autosave_revision") or 0):
            raise HTTPException(status_code=409, detail="Autosave revision is stale; reload the governed attempt before saving again.")
        allowed_ids = {str(question.get("id")) for question in engine.get("questions") or []}
        unknown = set(payload.answers) - allowed_ids
        if unknown:
            raise HTTPException(status_code=422, detail="Answers contain questions outside this governed attempt snapshot.")
        answers = dict(results.get("answers") or {})
        answers.update(payload.answers)
        results["answers"] = answers
        engine["autosave_revision"] = int(engine.get("autosave_revision") or 0) + 1
        engine["autosaved_at"] = _now().isoformat()
        results["_engine"] = engine
        instance.results = results
        db.commit()
        return {"ok": True, "autosave_revision": engine["autosave_revision"], "saved_at": engine["autosaved_at"]}

    @router.post("/assessments/{assessment_id}/attempt/submit")
    def submit_assessment_attempt(
        assessment_id: str,
        payload: AssessmentAutosave,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = tenant_id_for(current_user)
        instance = _scoped(db, operating_models.TrainingAssessmentInstance, amo_id=amo_id, row_id=assessment_id, label="Assessment")
        try:
            results, engine = assert_open_attempt(db, instance, current_user)
        except HTTPException:
            db.commit()
            raise
        answers = dict(results.get("answers") or {})
        answers.update(payload.answers)
        allowed_ids = {str(question.get("id")) for question in engine.get("questions") or []}
        if set(answers) - allowed_ids:
            raise HTTPException(status_code=422, detail="Answers contain questions outside this governed attempt snapshot.")
        template = _template(db, amo_id=amo_id, template_id=str(instance.template_id))
        _validate_template_for_attempt(template)
        policy = _active_policy(db, amo_id=amo_id, template_id=str(template.id))
        if str(engine.get("policy_id") or "") != str(policy.id):
            raise HTTPException(status_code=409, detail="Assessment policy changed after the attempt began; controlled review is required before submission.")
        question_ids = [str(question.get("id")) for question in engine.get("questions") or []]
        questions = db.query(operating_models.TrainingAssessmentQuestion).filter(
            operating_models.TrainingAssessmentQuestion.amo_id == amo_id,
            operating_models.TrainingAssessmentQuestion.id.in_(question_ids or [""]),
        ).all()
        by_id = {str(question.id): question for question in questions}
        earned = Decimal("0")
        total = Decimal("0")
        manual_required = _enum(template.outcome_scheme) not in {"NUMERIC", "PASS_FAIL"}
        item_results: list[dict[str, Any]] = []
        for snapshot in engine.get("questions") or []:
            question = by_id.get(str(snapshot.get("id")))
            if question is None:
                raise HTTPException(status_code=409, detail="A controlled question in this frozen attempt no longer exists.")
            marks = Decimal(str(question.marks or 0))
            total += marks
            answer = answers.get(str(question.id))
            correct = _is_objective_correct(question, answer)
            if correct is True:
                earned += marks
            elif correct is None:
                manual_required = True
            item_results.append({"question_id": str(question.id), "correct": correct, "marks": str(marks)})
        score = (earned / total * Decimal("100")) if total > 0 and not manual_required else None
        results["answers"] = answers
        history = list(results.get("_attempt_history") or [])
        history.append({
            "attempt_no": engine.get("attempt_no"),
            "submitted_at": _now().isoformat(),
            "answers": answers,
            "item_results": item_results,
            "auto_score": float(score) if score is not None else None,
            "policy_id": str(policy.id),
        })
        results["_attempt_history"] = history
        if manual_required:
            instance.status = "SUBMITTED"
            instance.outcome = "REVIEW_REQUIRED"
            instance.score = None
        else:
            threshold = Decimal(str(template.pass_threshold))
            passed = bool(score is not None and score >= threshold)
            instance.score = score
            instance.outcome = "PASSED" if passed else "FAILED"
            instance.status = "COMPLETED" if passed else "FAILED"
            if not passed and int(engine.get("attempt_no") or 0) < policy.attempt_limit:
                engine["cooldown_until"] = (_now() + timedelta(hours=policy.cooldown_hours)).isoformat() if policy.cooldown_hours else _now().isoformat()
        engine["submitted_at"] = _now().isoformat()
        results["_engine"] = engine
        instance.results = results
        instance.performed_at = _now()
        _audit(router_module, db, current_user=current_user, action="ASSESSMENT_ATTEMPT_SUBMIT", entity_type="TrainingAssessmentInstance", entity_id=str(instance.id), details={"attempt_no": engine.get("attempt_no"), "status": instance.status, "outcome": instance.outcome, "score": float(score) if score is not None else None, "policy_id": str(policy.id)})
        db.commit()
        return _assessment_read(db, instance, include_answers=True)

    @router.post("/assessments/{assessment_id}/review")
    def review_assessment_attempt(
        assessment_id: str,
        payload: AssessmentReviewPayload,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_REVIEW)),
    ):
        amo_id = tenant_id_for(current_user)
        instance = _scoped(db, operating_models.TrainingAssessmentInstance, amo_id=amo_id, row_id=assessment_id, label="Assessment")
        if str(instance.candidate_user_id) == str(current_user.id):
            raise HTTPException(status_code=409, detail="Candidate cannot assess/review their own assessment.")
        if instance.status not in {"SUBMITTED", "REVIEW_REQUIRED", "FAILED", "COMPLETED"}:
            raise HTTPException(status_code=409, detail=f"Assessment in {instance.status} is not ready for review.")
        template = _template(db, amo_id=amo_id, template_id=str(instance.template_id))
        if payload.outcome == "PASSED" and _enum(template.outcome_scheme) in {"NUMERIC", "PASS_FAIL"} and template.pass_threshold is not None and payload.score is not None and payload.score < template.pass_threshold:
            raise HTTPException(status_code=422, detail="A passed review cannot record a score below the controlled pass threshold.")
        results = dict(instance.results or {})
        engine = dict(results.get("_engine") or {})
        engine["proctor_signoff"] = payload.proctor_signoff
        engine["moderation_decision"] = payload.moderation_decision
        engine["reviewed_by_user_id"] = str(current_user.id)
        engine["reviewed_at"] = _now().isoformat()
        results["_engine"] = engine
        instance.results = results
        instance.score = payload.score
        instance.outcome = payload.outcome
        instance.comments = payload.comments
        instance.review_decision = payload.outcome
        instance.reviewer_user_id = str(current_user.id)
        instance.reviewed_at = _now()
        instance.status = "COMPLETED" if payload.outcome == "PASSED" else ("FAILED" if payload.outcome == "FAILED" else "REVIEW_REQUIRED")
        if payload.outcome == "PASSED":
            instance.approved_at = _now()
        _audit(router_module, db, current_user=current_user, action="ASSESSMENT_REVIEW", entity_type="TrainingAssessmentInstance", entity_id=str(instance.id), details=payload.model_dump(mode="json"))
        db.commit()
        return _assessment_read(db, instance, include_answers=False)

    @router.post("/assessments/{assessment_id}/appeal", status_code=201)
    def appeal_assessment(
        assessment_id: str,
        payload: AssessmentAppealPayload,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = tenant_id_for(current_user)
        instance = _scoped(db, operating_models.TrainingAssessmentInstance, amo_id=amo_id, row_id=assessment_id, label="Assessment")
        if str(instance.candidate_user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Only the candidate may appeal this assessment.")
        if _enum(instance.outcome) not in {"FAILED", "REVIEW_REQUIRED"}:
            raise HTTPException(status_code=409, detail="Only failed/review-required outcomes may be appealed.")
        workflow = _workflow_appeal(db, instance=instance, user=current_user, reason=payload.reason)
        _audit(router_module, db, current_user=current_user, action="ASSESSMENT_APPEAL_SUBMIT", entity_type="TrainingWorkflowInstance", entity_id=str(workflow.id), details=dict(workflow.data_json or {}))
        db.commit(); db.refresh(workflow)
        return {"id": str(workflow.id), "status": workflow.status, "data": workflow.data_json}


__all__ = ["install_training_canonical_assessment_routes"]
