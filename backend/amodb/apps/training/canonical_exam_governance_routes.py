"""Governed examination bridge using the canonical Training assessment runtime.

The controlled question bank, revisions, blueprints, forms and generated exam sets
remain governance metadata. Learner attempt state, answers, scores and review state
are persisted only in TrainingAssessmentInstance/TrainingWorkflowInstance.

This deliberately leaves the legacy governed-attempt tables dormant for migration
compatibility; runtime code in this installer never reads from or writes to them.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import exam_governance
from . import exam_governance_models as exam_models
from . import exam_governance_schemas as schemas
from . import governance_models as governance_models
from . import governance_rules
from . import governance_service
from . import models as legacy_models
from . import operating_models
from .permissions import TrainingCapability as Cap, require_training_capability, tenant_id_for

UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(UTC)


def _dict(row: object) -> dict[str, Any]:
    return governance_service._dict(row)


def _scoped(db: Session, model: type, *, amo_id: str, row_id: str, label: str):
    return governance_service._tenant_row(db, model, amo_id=amo_id, row_id=row_id, label=label)


def _question_revision_rows(db: Session, *, amo_id: str, course_revision_id: str):
    return (
        db.query(governance_models.TrainingQuestionBankItem, governance_models.TrainingQuestionRevision)
        .join(
            governance_models.TrainingQuestionRevision,
            governance_models.TrainingQuestionRevision.question_id == governance_models.TrainingQuestionBankItem.id,
        )
        .filter(
            governance_models.TrainingQuestionBankItem.amo_id == amo_id,
            governance_models.TrainingQuestionBankItem.course_revision_id == course_revision_id,
            governance_models.TrainingQuestionBankItem.status == "ACTIVE",
            governance_models.TrainingQuestionRevision.amo_id == amo_id,
            governance_models.TrainingQuestionRevision.status == "ACTIVE",
        )
        .all()
    )


def _candidate_payload(question, revision) -> dict[str, object]:
    return {"question": _dict(question), "revision": _dict(revision)}


def _blueprint(db: Session, *, amo_id: str, blueprint_id: str):
    return _scoped(
        db,
        governance_models.TrainingExamBlueprint,
        amo_id=amo_id,
        row_id=blueprint_id,
        label="Exam blueprint",
    )


def _blueprint_blockers(blueprint, *, on_date: date) -> list[str]:
    blockers: list[str] = []
    if str(blueprint.status or "").upper() != "ACTIVE":
        blockers.append("Exam blueprint is not ACTIVE.")
    if blueprint.effective_from and on_date < blueprint.effective_from:
        blockers.append("Exam blueprint is not yet effective.")
    if blueprint.effective_to and on_date > blueprint.effective_to:
        blockers.append("Exam blueprint is superseded or expired.")
    return blockers


def _controlled_policy(blueprint) -> dict[str, Any]:
    result = dict(blueprint.result_rules or {})
    security = dict(blueprint.security_rules or {})
    required = {
        "pass_threshold": result.get("pass_threshold"),
        "max_attempts": result.get("max_attempts"),
    }
    missing = [key for key, value in required.items() if value is None]
    if missing:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "EXAM_POLICY_INCOMPLETE",
                "message": "The approved exam blueprint must define every controlled result value used by the attempt engine.",
                "missing": missing,
            },
        )
    threshold = Decimal(str(required["pass_threshold"]))
    max_attempts = int(required["max_attempts"])
    if threshold < 0 or threshold > 100 or max_attempts <= 0:
        raise HTTPException(status_code=409, detail="Approved exam result policy contains invalid controlled values.")
    return {
        "pass_threshold": threshold,
        "max_attempts": max_attempts,
        "cooldown_hours": result.get("cooldown_hours"),
        "time_limit_minutes": security.get("time_limit_minutes", result.get("time_limit_minutes")),
        "proctor_required": bool(security.get("proctor_required")),
    }


def _revision_to_answer_key(revision) -> Any:
    answer = dict(revision.answer_key_json or {})
    if "correct_option" in answer:
        return {"value": answer.get("correct_option")}
    if "correct_options" in answer:
        return {"values": list(answer.get("correct_options") or [])}
    if "value" in answer:
        return {"value": answer.get("value")}
    return answer or None


def _response_is_correct(revision, response: Any) -> bool | None:
    response_payload = response if isinstance(response, Mapping) else {"selected_option": response}
    selected = response_payload.get("selected_option")
    answer = dict(revision.answer_key_json or {})
    if "correct_option" in answer:
        return str(selected) == str(answer.get("correct_option"))
    if "correct_options" in answer:
        selected_values = response_payload.get("selected_options")
        if selected_values is None:
            selected_values = [selected] if selected is not None else []
        return {str(value) for value in selected_values or []} == {str(value) for value in answer.get("correct_options") or []}
    if "value" in answer:
        return str(response_payload.get("value", selected)) == str(answer.get("value"))
    return None


def _canonical_template_for_generation(db: Session, *, amo_id: str, generation, blueprint, actor_user_id: str):
    code = f"GOVEX-{str(generation.id)[:24]}"
    existing = (
        db.query(operating_models.TrainingAssessmentTemplate)
        .filter(
            operating_models.TrainingAssessmentTemplate.amo_id == amo_id,
            operating_models.TrainingAssessmentTemplate.code == code,
            operating_models.TrainingAssessmentTemplate.revision_no == 1,
        )
        .first()
    )
    if existing:
        return existing

    policy = _controlled_policy(blueprint)
    template = operating_models.TrainingAssessmentTemplate(
        amo_id=amo_id,
        code=code,
        name=f"{blueprint.title} · {generation.generation_code}"[:255],
        purpose="Frozen governed examination generated from an approved Training exam blueprint.",
        assessment_type="WRITTEN",
        outcome_scheme="PASS_FAIL",
        revision_no=1,
        effective_from=blueprint.effective_from,
        effective_to=blueprint.effective_to,
        pass_threshold=policy["pass_threshold"],
        mandatory_criteria={
            "attempt_policy": {
                "attempt_limit": policy["max_attempts"],
                **({"cooldown_hours": policy["cooldown_hours"]} if policy["cooldown_hours"] is not None else {}),
                **({"time_limit_minutes": policy["time_limit_minutes"]} if policy["time_limit_minutes"] is not None else {}),
                "randomize_questions": False,
                "question_count": len(generation.question_revision_ids or []),
            },
            "governed_exam": {
                "generation_id": str(generation.id),
                "blueprint_id": str(blueprint.id),
                "course_revision_id": str(blueprint.course_revision_id),
            },
        },
        evidence_requirements=[],
        assessor_capability=Cap.ASSESSMENT_PERFORM.value,
        approval_required=True,
        manual_reference=f"training-exam-blueprint:{blueprint.id}",
        active=True,
        created_by_user_id=actor_user_id,
    )
    db.add(template)
    db.flush()

    revision_ids = list(generation.question_revision_ids or [])
    rows = (
        db.query(governance_models.TrainingQuestionRevision)
        .filter(
            governance_models.TrainingQuestionRevision.amo_id == amo_id,
            governance_models.TrainingQuestionRevision.id.in_(revision_ids or [""]),
        )
        .all()
    )
    by_id = {str(row.id): row for row in rows}
    if set(revision_ids) != set(by_id):
        raise HTTPException(status_code=409, detail="Frozen exam generation references a missing question revision.")
    for sequence_no, revision_id in enumerate(revision_ids, start=1):
        revision = by_id[revision_id]
        db.add(
            operating_models.TrainingAssessmentQuestion(
                amo_id=amo_id,
                template_id=template.id,
                sequence_no=sequence_no,
                question_text=revision.prompt,
                response_type="MULTIPLE_CHOICE" if revision.options_json else "TEXT",
                answer_options=list(revision.options_json or []),
                evaluation_rule={"source_question_revision_id": revision_id},
                answer_key=_revision_to_answer_key(revision),
                marks=revision.marks,
                mandatory=True,
                manual_reference=f"training-question-revision:{revision_id}",
                active=True,
            )
        )
    db.flush()
    return template


def _canonical_attempt(db: Session, *, amo_id: str, attempt_id: str):
    return _scoped(
        db,
        operating_models.TrainingAssessmentInstance,
        amo_id=amo_id,
        row_id=attempt_id,
        label="Exam assessment attempt",
    )


def _exam_metadata(instance) -> dict[str, Any]:
    return dict((instance.results or {}).get("_governed_exam") or {})


def _workflow(db: Session, *, amo_id: str, workflow_type: str, idempotency_key: str, title: str, subject_user_id: str | None, data: dict[str, Any], created_by_user_id: str | None):
    row = (
        db.query(operating_models.TrainingWorkflowInstance)
        .filter(
            operating_models.TrainingWorkflowInstance.amo_id == amo_id,
            operating_models.TrainingWorkflowInstance.workflow_type == workflow_type,
            operating_models.TrainingWorkflowInstance.idempotency_key == idempotency_key,
        )
        .first()
    )
    if row:
        return row
    row = operating_models.TrainingWorkflowInstance(
        amo_id=amo_id,
        workflow_type=workflow_type,
        title=title[:255],
        status="SUBMITTED",
        subject_user_id=subject_user_id,
        data_json=data,
        validation_result={},
        provenance={"module": "training", "canonical_assessment": True},
        idempotency_key=idempotency_key,
        revision_no=1,
        submitted_at=_now(),
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    db.flush()
    return row


def install_training_canonical_exam_governance_routes(router_module) -> None:
    router = router_module.router
    if getattr(router_module, "_training_canonical_exam_governance_routes_installed", False):
        return
    router_module._training_canonical_exam_governance_routes_installed = True

    @router.get("/operating/governance/exams/blueprints", response_model=list[schemas.ExamBlueprintRead])
    def list_exam_blueprints(
        course_revision_id: str | None = None,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_VIEW)),
    ):
        query = db.query(governance_models.TrainingExamBlueprint).filter(
            governance_models.TrainingExamBlueprint.amo_id == tenant_id_for(current_user)
        )
        if course_revision_id:
            query = query.filter(governance_models.TrainingExamBlueprint.course_revision_id == course_revision_id)
        return query.order_by(
            governance_models.TrainingExamBlueprint.course_revision_id,
            governance_models.TrainingExamBlueprint.revision_no.desc(),
        ).all()

    @router.post("/operating/governance/exams/blueprints", response_model=schemas.ExamBlueprintRead, status_code=201)
    def create_exam_blueprint(
        payload: schemas.ExamBlueprintCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_CREATE)),
    ):
        amo_id = tenant_id_for(current_user)
        _scoped(db, governance_models.TrainingCourseRevision, amo_id=amo_id, row_id=payload.course_revision_id, label="Course revision")
        row = governance_models.TrainingExamBlueprint(amo_id=amo_id, **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return row

    @router.post("/operating/governance/exams/blueprints/{blueprint_id}/activate", response_model=schemas.ExamBlueprintRead)
    def activate_exam_blueprint(
        blueprint_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_APPROVE)),
    ):
        amo_id = tenant_id_for(current_user)
        row = _blueprint(db, amo_id=amo_id, blueprint_id=blueprint_id)
        revision = _scoped(db, governance_models.TrainingCourseRevision, amo_id=amo_id, row_id=row.course_revision_id, label="Course revision")
        if str(revision.status or "").upper() != "ACTIVE":
            raise HTTPException(status_code=409, detail="Exam blueprint cannot be activated against a non-active course revision.")
        _controlled_policy(row)
        selection = exam_governance.select_question_revisions(
            [_candidate_payload(q, r) for q, r in _question_revision_rows(db, amo_id=amo_id, course_revision_id=str(row.course_revision_id))],
            on_date=row.effective_from or date.today(),
            selection_rules=row.selection_rules or {},
        )
        if not selection["ready"]:
            raise HTTPException(status_code=409, detail={"code": "EXAM_BLUEPRINT_NOT_GENERATABLE", **selection})
        db.query(governance_models.TrainingExamBlueprint).filter(
            governance_models.TrainingExamBlueprint.amo_id == amo_id,
            governance_models.TrainingExamBlueprint.course_revision_id == row.course_revision_id,
            governance_models.TrainingExamBlueprint.id != row.id,
            governance_models.TrainingExamBlueprint.status == "ACTIVE",
        ).update({governance_models.TrainingExamBlueprint.status: "SUPERSEDED"}, synchronize_session=False)
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
        blueprint = _blueprint(db, amo_id=amo_id, blueprint_id=payload.blueprint_id)
        candidate_map = {str(revision.id): (question, revision) for question, revision in _question_revision_rows(db, amo_id=amo_id, course_revision_id=str(blueprint.course_revision_id))}
        blockers: list[dict[str, object]] = []
        for revision_id in payload.question_revision_ids:
            pair = candidate_map.get(revision_id)
            reasons = ["Question revision is not ACTIVE for this course revision."] if not pair else governance_rules.question_eligibility_reasons(_dict(pair[0]), _dict(pair[1]), on_date=date.today())
            if reasons:
                blockers.append({"question_revision_id": revision_id, "reasons": reasons})
        if blockers:
            raise HTTPException(status_code=409, detail={"code": "EXAM_FORM_BLOCKED", "blockers": blockers})
        row = exam_models.TrainingExamForm(amo_id=amo_id, **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return _dict(row)

    @router.post("/operating/governance/exams/forms/{form_id}/activate")
    def activate_exam_form(
        form_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_APPROVE)),
    ):
        amo_id = tenant_id_for(current_user)
        form = _scoped(db, exam_models.TrainingExamForm, amo_id=amo_id, row_id=form_id, label="Exam form")
        blueprint = _blueprint(db, amo_id=amo_id, blueprint_id=form.blueprint_id)
        blockers = _blueprint_blockers(blueprint, on_date=date.today())
        if blockers:
            raise HTTPException(status_code=409, detail={"code": "EXAM_FORM_BLOCKED", "blockers": blockers})
        required_count = int((blueprint.selection_rules or {}).get("question_count") or 0)
        if len(form.question_revision_ids or []) != required_count:
            raise HTTPException(status_code=409, detail="Exam form question count does not match its approved blueprint.")
        form.status = "ACTIVE"; form.approved_by_user_id = str(current_user.id)
        db.commit(); db.refresh(form)
        return _dict(form)

    @router.post("/operating/governance/exams/generations", response_model=schemas.ExamGenerationRead, status_code=201)
    def generate_exam(
        payload: schemas.ExamGenerationCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_CREATE)),
    ):
        amo_id = tenant_id_for(current_user)
        event = _scoped(db, legacy_models.TrainingEvent, amo_id=amo_id, row_id=payload.event_id, label="Training session")
        blueprint = _blueprint(db, amo_id=amo_id, blueprint_id=payload.blueprint_id)
        blockers = _blueprint_blockers(blueprint, on_date=event.starts_on)
        if blockers:
            raise HTTPException(status_code=409, detail={"code": "EXAM_BLUEPRINT_BLOCKED", "blockers": blockers})
        _controlled_policy(blueprint)
        envelope = db.query(governance_models.TrainingSessionGovernance).filter(
            governance_models.TrainingSessionGovernance.amo_id == amo_id,
            governance_models.TrainingSessionGovernance.event_id == event.id,
        ).first()
        if not envelope or str(envelope.course_revision_id) != str(blueprint.course_revision_id):
            raise HTTPException(status_code=409, detail="Exam blueprint does not match the governed course revision for this session.")
        excluded: list[dict[str, object]] = []
        if payload.form_id:
            form = _scoped(db, exam_models.TrainingExamForm, amo_id=amo_id, row_id=payload.form_id, label="Exam form")
            if str(form.blueprint_id) != str(blueprint.id) or str(form.status or "").upper() != "ACTIVE":
                raise HTTPException(status_code=409, detail="Exam form is not an active form for this blueprint.")
            selected_ids = list(form.question_revision_ids or [])
        else:
            selection = exam_governance.select_question_revisions(
                [_candidate_payload(q, r) for q, r in _question_revision_rows(db, amo_id=amo_id, course_revision_id=str(blueprint.course_revision_id))],
                on_date=event.starts_on,
                selection_rules=blueprint.selection_rules or {},
            )
            if not selection["ready"]:
                raise HTTPException(status_code=409, detail={"code": "EXAM_GENERATION_BLOCKED", **selection})
            selected_ids = list(selection["selected_revision_ids"])
            excluded = list(selection["excluded"])
        row = governance_models.TrainingExamGeneration(
            amo_id=amo_id,
            event_id=event.id,
            blueprint_id=blueprint.id,
            generation_code=payload.generation_code,
            question_revision_ids=selected_ids,
            generated_by_user_id=str(current_user.id),
            security_metadata=payload.security_metadata,
        )
        db.add(row)
        questions = db.query(governance_models.TrainingQuestionBankItem).join(
            governance_models.TrainingQuestionRevision,
            governance_models.TrainingQuestionRevision.question_id == governance_models.TrainingQuestionBankItem.id,
        ).filter(
            governance_models.TrainingQuestionBankItem.amo_id == amo_id,
            governance_models.TrainingQuestionRevision.id.in_(selected_ids),
        ).all()
        for question in questions:
            question.exposure_count = int(question.exposure_count or 0) + 1
            question.last_used_at = _now()
        db.commit(); db.refresh(row)
        return {**_dict(row), "excluded": excluded}

    @router.post("/operating/governance/exams/attempts", status_code=201)
    def create_exam_attempt(
        payload: schemas.ExamAttemptCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = tenant_id_for(current_user)
        generation = _scoped(db, governance_models.TrainingExamGeneration, amo_id=amo_id, row_id=payload.generation_id, label="Exam generation")
        if str(generation.event_id) != payload.event_id or str(generation.status or "").upper() != "ACTIVE":
            raise HTTPException(status_code=409, detail="Exam generation is not active for this session.")
        participant = db.query(legacy_models.TrainingEventParticipant).filter(
            legacy_models.TrainingEventParticipant.amo_id == amo_id,
            legacy_models.TrainingEventParticipant.event_id == payload.event_id,
            legacy_models.TrainingEventParticipant.user_id == str(current_user.id),
        ).first()
        if participant is None:
            raise HTTPException(status_code=403, detail="Only an enrolled learner may start this examination.")
        blueprint = _blueprint(db, amo_id=amo_id, blueprint_id=generation.blueprint_id)
        policy = _controlled_policy(blueprint)
        if policy["proctor_required"] and not payload.proctor_user_id:
            raise HTTPException(status_code=409, detail="This examination requires a proctor under the approved blueprint.")
        existing = db.query(operating_models.TrainingAssessmentInstance).filter(
            operating_models.TrainingAssessmentInstance.amo_id == amo_id,
            operating_models.TrainingAssessmentInstance.candidate_user_id == str(current_user.id),
            operating_models.TrainingAssessmentInstance.event_id == payload.event_id,
        ).all()
        governed_existing = [row for row in existing if str(_exam_metadata(row).get("generation_id") or "") == str(generation.id)]
        if len(governed_existing) >= policy["max_attempts"]:
            raise HTTPException(status_code=409, detail="Controlled maximum examination attempts has been reached.")
        if governed_existing and policy["cooldown_hours"] is not None:
            latest = max(governed_existing, key=lambda row: row.performed_at or row.created_at)
            if latest.performed_at:
                from datetime import timedelta
                next_allowed = latest.performed_at + timedelta(hours=float(policy["cooldown_hours"]))
                if _now() < next_allowed:
                    raise HTTPException(status_code=409, detail={"code": "EXAM_COOLDOWN", "next_allowed_at": next_allowed.isoformat()})
        template = _canonical_template_for_generation(
            db,
            amo_id=amo_id,
            generation=generation,
            blueprint=blueprint,
            actor_user_id=str(current_user.id),
        )
        course_revision = _scoped(db, governance_models.TrainingCourseRevision, amo_id=amo_id, row_id=blueprint.course_revision_id, label="Course revision")
        attempt_no = len(governed_existing) + 1
        started = _now()
        instance = operating_models.TrainingAssessmentInstance(
            amo_id=amo_id,
            template_id=template.id,
            candidate_user_id=str(current_user.id),
            course_id=str(course_revision.course_id),
            event_id=payload.event_id,
            assessor_user_id=payload.proctor_user_id,
            planned_at=started,
            status="IN_PROGRESS",
            results={
                "answers": {},
                "_governed_exam": {
                    "generation_id": str(generation.id),
                    "blueprint_id": str(blueprint.id),
                    "question_revision_ids": list(generation.question_revision_ids or []),
                    "attempt_no": attempt_no,
                    "started_at": started.isoformat(),
                    "proctor_user_id": payload.proctor_user_id,
                },
            },
            created_by_user_id=str(current_user.id),
        )
        db.add(instance)
        router_module._audit(db, amo_id=amo_id, actor_user_id=str(current_user.id), action="GOVERNED_EXAM_ATTEMPT_START", entity_type="TrainingAssessmentInstance", entity_id=None, details={"generation_id": str(generation.id), "attempt_no": attempt_no})
        db.commit(); db.refresh(instance)
        return {"id": str(instance.id), "event_id": str(instance.event_id), "attempt_no": attempt_no, "status": "IN_PROGRESS", "started_at": started}

    @router.get("/operating/governance/exams/attempts/{attempt_id}/learner", response_model=schemas.ExamAttemptLearnerRead)
    def learner_exam_attempt(
        attempt_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = tenant_id_for(current_user)
        instance = _canonical_attempt(db, amo_id=amo_id, attempt_id=attempt_id)
        if str(instance.candidate_user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="You cannot read another learner's examination attempt.")
        metadata = _exam_metadata(instance)
        revision_ids = list(metadata.get("question_revision_ids") or [])
        revisions = db.query(governance_models.TrainingQuestionRevision).filter(
            governance_models.TrainingQuestionRevision.amo_id == amo_id,
            governance_models.TrainingQuestionRevision.id.in_(revision_ids or [""]),
        ).all()
        by_id = {str(row.id): row for row in revisions}
        questions = []
        for revision_id in revision_ids:
            revision = by_id.get(revision_id)
            if revision is None:
                raise HTTPException(status_code=409, detail="Frozen exam form references a missing question revision.")
            questions.append(governance_service.learner_question_projection(revision))
        return {"attempt_id": str(instance.id), "event_id": str(instance.event_id), "status": instance.status, "questions": questions}

    @router.post("/operating/governance/exams/attempts/{attempt_id}/security-events", status_code=201)
    def record_exam_security_event(
        attempt_id: str,
        payload: schemas.ExamSecurityEventCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = tenant_id_for(current_user)
        instance = _canonical_attempt(db, amo_id=amo_id, attempt_id=attempt_id)
        if str(instance.candidate_user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="You cannot record a security event against another learner's attempt.")
        workflow = _workflow(
            db,
            amo_id=amo_id,
            workflow_type="EXAM_SECURITY_EVENT",
            idempotency_key=f"exam-security:{attempt_id}:{uuid.uuid4()}",
            title=f"Exam security event · {payload.event_type}",
            subject_user_id=str(current_user.id),
            data={"assessment_id": attempt_id, **payload.model_dump(mode="json")},
            created_by_user_id=str(current_user.id),
        )
        db.commit(); db.refresh(workflow)
        return {"id": str(workflow.id), "status": workflow.status, "data": workflow.data_json}

    @router.post("/operating/governance/exams/attempts/{attempt_id}/submit")
    def submit_exam_attempt(
        attempt_id: str,
        payload: schemas.ExamAttemptSubmit,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = tenant_id_for(current_user)
        instance = _canonical_attempt(db, amo_id=amo_id, attempt_id=attempt_id)
        if str(instance.candidate_user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="You cannot submit another learner's examination attempt.")
        if str(instance.status or "").upper() != "IN_PROGRESS":
            raise HTTPException(status_code=409, detail="Examination attempt is not in progress.")
        metadata = _exam_metadata(instance)
        blueprint = _blueprint(db, amo_id=amo_id, blueprint_id=str(metadata.get("blueprint_id") or ""))
        policy = _controlled_policy(blueprint)
        revision_ids = list(metadata.get("question_revision_ids") or [])
        if set(payload.responses) - set(revision_ids):
            raise HTTPException(status_code=422, detail="Responses contain questions outside this frozen governed examination.")
        revisions = db.query(governance_models.TrainingQuestionRevision).filter(
            governance_models.TrainingQuestionRevision.amo_id == amo_id,
            governance_models.TrainingQuestionRevision.id.in_(revision_ids or [""]),
        ).all()
        by_id = {str(row.id): row for row in revisions}
        total_marks = Decimal("0")
        earned_marks = Decimal("0")
        manual_required = False
        item_results: list[dict[str, Any]] = []
        for revision_id in revision_ids:
            revision = by_id.get(revision_id)
            if revision is None:
                raise HTTPException(status_code=409, detail="Frozen exam form references a missing question revision.")
            marks = Decimal(str(revision.marks or 0))
            total_marks += marks
            response = payload.responses.get(revision_id)
            correct = _response_is_correct(revision, response)
            if correct is True:
                earned_marks += marks
            elif correct is None:
                manual_required = True
            item_results.append({"question_revision_id": revision_id, "response": response, "correct": correct, "marks": str(marks)})
        score = (earned_marks / total_marks * Decimal("100")) if total_marks > 0 and not manual_required else None
        results = dict(instance.results or {})
        metadata.update({
            "submitted_at": _now().isoformat(),
            "item_results": item_results,
            "total_marks": str(total_marks),
            "earned_marks": str(earned_marks),
        })
        results["answers"] = dict(payload.responses)
        results["_governed_exam"] = metadata
        instance.results = results
        instance.performed_at = _now()
        if manual_required:
            instance.status = "SUBMITTED"
            instance.outcome = "REVIEW_REQUIRED"
            instance.score = None
            response_status = "REVIEW_REQUIRED"
            result_label = "REVIEW_REQUIRED"
        else:
            passed = bool(score is not None and score >= policy["pass_threshold"])
            instance.score = score
            instance.outcome = "PASSED" if passed else "FAILED"
            instance.status = "COMPLETED" if passed else "FAILED"
            response_status = "GRADED"
            result_label = "PASS" if passed else "FAIL"
        router_module._audit(db, amo_id=amo_id, actor_user_id=str(current_user.id), action="GOVERNED_EXAM_ATTEMPT_SUBMIT", entity_type="TrainingAssessmentInstance", entity_id=str(instance.id), details={"status": instance.status, "outcome": instance.outcome, "score": str(score) if score is not None else None})
        db.commit(); db.refresh(instance)
        return {"id": str(instance.id), "status": response_status, "result": result_label, "score": str(score) if score is not None else None}

    @router.post("/operating/governance/exams/analysis", response_model=schemas.ExamAnalysisRead, status_code=201)
    def run_exam_analysis(
        payload: schemas.ExamAnalysisRun,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_REVIEW)),
    ):
        amo_id = tenant_id_for(current_user)
        _scoped(db, governance_models.TrainingQuestionRevision, amo_id=amo_id, row_id=payload.question_revision_id, label="Question revision")
        instances = db.query(operating_models.TrainingAssessmentInstance).filter(
            operating_models.TrainingAssessmentInstance.amo_id == amo_id,
            operating_models.TrainingAssessmentInstance.status.in_(["COMPLETED", "FAILED"]),
        ).all()
        response_rows: list[dict[str, Any]] = []
        for instance in instances:
            metadata = _exam_metadata(instance)
            for item in metadata.get("item_results") or []:
                if str(item.get("question_revision_id")) != payload.question_revision_id or item.get("correct") is None:
                    continue
                response = item.get("response")
                selected = response.get("selected_option") if isinstance(response, Mapping) else response
                response_rows.append({"selected_option": selected, "correct": bool(item.get("correct")), "total_score": instance.score or 0})
        analysis = exam_governance.item_analysis(
            response_rows,
            policy=payload.policy,
            source_superseded=payload.source_superseded,
            complaint_count=payload.complaint_count,
        )
        row = db.query(exam_models.TrainingExamItemAnalysis).filter(
            exam_models.TrainingExamItemAnalysis.amo_id == amo_id,
            exam_models.TrainingExamItemAnalysis.question_revision_id == payload.question_revision_id,
            exam_models.TrainingExamItemAnalysis.analysis_window == payload.analysis_window,
        ).first()
        values = {**analysis, "complaint_count": payload.complaint_count, "source_superseded": payload.source_superseded}
        if row is None:
            row = exam_models.TrainingExamItemAnalysis(amo_id=amo_id, question_revision_id=payload.question_revision_id, analysis_window=payload.analysis_window, **values)
            db.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
            row.computed_at = _now()
        db.commit(); db.refresh(row)
        return row

    @router.get("/operating/governance/exams/quality-queue")
    def exam_quality_queue(
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_REVIEW)),
    ):
        amo_id = tenant_id_for(current_user)
        analyses = db.query(exam_models.TrainingExamItemAnalysis).filter(
            exam_models.TrainingExamItemAnalysis.amo_id == amo_id,
            exam_models.TrainingExamItemAnalysis.review_status != "CLEAR",
        ).order_by(exam_models.TrainingExamItemAnalysis.computed_at.asc()).limit(200).all()
        moderations = db.query(exam_models.TrainingExamModeration).filter(
            exam_models.TrainingExamModeration.amo_id == amo_id,
            exam_models.TrainingExamModeration.status == "OPEN",
        ).order_by(exam_models.TrainingExamModeration.created_at.asc()).limit(200).all()
        appeals = db.query(operating_models.TrainingWorkflowInstance).filter(
            operating_models.TrainingWorkflowInstance.amo_id == amo_id,
            operating_models.TrainingWorkflowInstance.workflow_type == "ASSESSMENT_APPEAL",
            operating_models.TrainingWorkflowInstance.status.in_(["SUBMITTED", "UNDER_REVIEW"]),
        ).order_by(operating_models.TrainingWorkflowInstance.created_at.asc()).limit(200).all()
        return {"analysis": [_dict(row) for row in analyses], "moderations": [_dict(row) for row in moderations], "appeals": [_dict(row) for row in appeals]}

    @router.post("/operating/governance/exams/moderations", status_code=201)
    def create_moderation(
        payload: schemas.ModerationCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_REVIEW)),
    ):
        amo_id = tenant_id_for(current_user)
        if payload.question_revision_id:
            _scoped(db, governance_models.TrainingQuestionRevision, amo_id=amo_id, row_id=payload.question_revision_id, label="Question revision")
        if payload.generation_id:
            _scoped(db, governance_models.TrainingExamGeneration, amo_id=amo_id, row_id=payload.generation_id, label="Exam generation")
        row = exam_models.TrainingExamModeration(amo_id=amo_id, opened_by_user_id=str(current_user.id), **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return _dict(row)

    @router.post("/operating/governance/exams/moderations/{moderation_id}/decision")
    def decide_moderation(
        moderation_id: str,
        payload: schemas.ModerationDecision,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_APPROVE)),
    ):
        amo_id = tenant_id_for(current_user)
        row = _scoped(db, exam_models.TrainingExamModeration, amo_id=amo_id, row_id=moderation_id, label="Exam moderation")
        if row.opened_by_user_id and str(row.opened_by_user_id) == str(current_user.id):
            raise HTTPException(status_code=409, detail="The moderation originator cannot approve their own moderation decision.")
        row.status = "DECIDED"; row.decision = payload.decision; row.decision_reason = payload.decision_reason
        row.decided_by_user_id = str(current_user.id); row.decided_at = _now()
        db.commit(); db.refresh(row)
        return _dict(row)

    @router.post("/operating/governance/exams/appeals", status_code=201)
    def create_exam_appeal(
        payload: schemas.AppealCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = tenant_id_for(current_user)
        instance = _canonical_attempt(db, amo_id=amo_id, attempt_id=payload.attempt_id)
        if str(instance.candidate_user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="You may appeal only your own examination attempt.")
        if instance.outcome not in {"FAILED", "REVIEW_REQUIRED"}:
            raise HTTPException(status_code=409, detail="Only failed or review-required governed examinations may be appealed.")
        workflow = _workflow(
            db,
            amo_id=amo_id,
            workflow_type="ASSESSMENT_APPEAL",
            idempotency_key=f"assessment-appeal:{instance.id}",
            title="Governed examination appeal",
            subject_user_id=str(current_user.id),
            data={"assessment_id": str(instance.id), "grounds": payload.grounds, "evidence_json": payload.evidence_json, "outcome": instance.outcome, "score": str(instance.score) if instance.score is not None else None},
            created_by_user_id=str(current_user.id),
        )
        db.commit(); db.refresh(workflow)
        return {"id": str(workflow.id), "status": workflow.status, "data": workflow.data_json}

    @router.post("/operating/governance/exams/appeals/{appeal_id}/decision")
    def decide_exam_appeal(
        appeal_id: str,
        payload: schemas.AppealDecision,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_REVIEW)),
    ):
        amo_id = tenant_id_for(current_user)
        workflow = _scoped(db, operating_models.TrainingWorkflowInstance, amo_id=amo_id, row_id=appeal_id, label="Assessment appeal")
        if workflow.workflow_type != "ASSESSMENT_APPEAL":
            raise HTTPException(status_code=404, detail="Assessment appeal was not found.")
        if str(workflow.subject_user_id or "") == str(current_user.id):
            raise HTTPException(status_code=409, detail="Appellant cannot decide their own assessment appeal.")
        data = dict(workflow.data_json or {})
        data.update({"decision": payload.decision, "decision_reason": payload.decision_reason, "decided_by_user_id": str(current_user.id), "decided_at": _now().isoformat()})
        workflow.data_json = data; workflow.status = "DECIDED"; workflow.reviewer_user_id = str(current_user.id); workflow.completed_at = _now(); workflow.revision_no = int(workflow.revision_no or 0) + 1
        db.commit(); db.refresh(workflow)
        return {"id": str(workflow.id), "status": workflow.status, "data": workflow.data_json}


__all__ = ["install_training_canonical_exam_governance_routes"]
