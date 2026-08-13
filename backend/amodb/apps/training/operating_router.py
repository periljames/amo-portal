from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session, selectinload

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import operating_models as models
from . import operating_schemas as schemas
from . import operating_service as service
from . import operating_reports as reports
from . import models as legacy_models
from .permissions import (
    TrainingCapability as Cap,
    require_training_capability,
    tenant_id_for,
    training_capabilities_for,
)


router = APIRouter(prefix="/operating", tags=["training-operating-system"])


def _plans(db: Session, amo_id: str):
    return db.query(models.TrainingPlan).options(
        selectinload(models.TrainingPlan.items).selectinload(models.TrainingPlanItem.participants)
    ).filter(models.TrainingPlan.amo_id == amo_id)


def _budget_read(row: models.TrainingBudget) -> schemas.TrainingBudgetRead:
    quarter, annual = service.budget_totals(row)
    payload = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    payload.update(lines=row.lines, quarter_totals=quarter, annual_totals=annual)
    return schemas.TrainingBudgetRead.model_validate(payload)


@router.get("/access", response_model=schemas.TrainingAccessRead)
def access(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    capabilities = sorted(training_capabilities_for(db, user=current_user))
    return schemas.TrainingAccessRead(
        capabilities=capabilities,
        can_open_operating_system=Cap.VIEW.value in capabilities,
        self_service_only=Cap.VIEW.value not in capabilities,
        tenant_id=tenant_id_for(current_user),
    )


@router.get("/control-room", response_model=schemas.TrainingControlRoomRead)
def control_room(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    return service.control_room(db, actor=current_user)


@router.get("/reference/people")
def reference_people(
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PEOPLE_VIEW)),
):
    query = db.query(account_models.User).filter(
        account_models.User.amo_id == tenant_id_for(current_user),
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    )
    if search:
        token = f"%{search.strip()}%"
        query = query.filter(account_models.User.full_name.ilike(token) | account_models.User.staff_code.ilike(token) | account_models.User.email.ilike(token))
    rows = query.order_by(account_models.User.full_name).limit(limit).all()
    return [{"id": str(row.id), "full_name": row.full_name, "staff_code": row.staff_code, "role": str(getattr(row.role, "value", row.role)), "position_title": row.position_title, "department": getattr(row.department, "code", None)} for row in rows]


@router.get("/people/{user_id}/auditor-qualification", response_model=schemas.AuditorQualificationRead)
def auditor_qualification(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PEOPLE_VIEW)),
):
    return service.auditor_qualification_progress(
        db,
        amo_id=tenant_id_for(current_user),
        user_id=user_id,
    )


@router.get("/reference/authorization-types")
def reference_authorization_types(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.AUTHORIZATION_VIEW)),
):
    rows = db.query(account_models.AuthorisationType).filter(account_models.AuthorisationType.amo_id == tenant_id_for(current_user), account_models.AuthorisationType.is_active.is_(True)).order_by(account_models.AuthorisationType.code).all()
    return [{"id": str(row.id), "code": row.code, "name": row.name, "requires_valid_licence": row.requires_valid_licence} for row in rows]


@router.get("/settings", response_model=schemas.TrainingOperatingSettingsRead)
def get_settings(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    row = service.get_or_create_settings(db, amo_id=tenant_id_for(current_user))
    db.commit()
    db.refresh(row)
    return row


@router.put("/settings", response_model=schemas.TrainingOperatingSettingsRead)
def put_settings(
    payload: schemas.TrainingOperatingSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
):
    row = service.update_settings(db, actor=current_user, payload=payload)
    db.commit()
    db.refresh(row)
    return row


@router.get("/plans", response_model=list[schemas.TrainingPlanRead])
def list_plans(
    year: int | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PLAN_VIEW)),
):
    query = _plans(db, tenant_id_for(current_user))
    if year:
        query = query.filter(models.TrainingPlan.plan_year == year)
    return query.order_by(models.TrainingPlan.plan_year.desc(), models.TrainingPlan.revision_no.desc()).all()


@router.post("/plans", response_model=schemas.TrainingPlanRead, status_code=201)
def create_plan(
    payload: schemas.TrainingPlanCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PLAN_MANAGE)),
):
    row = service.create_plan(db, actor=current_user, payload=payload)
    db.commit()
    return _plans(db, tenant_id_for(current_user)).filter(models.TrainingPlan.id == row.id).one()


@router.get("/plans/{plan_id}", response_model=schemas.TrainingPlanRead)
def get_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PLAN_VIEW)),
):
    return service._get_scoped(db, models.TrainingPlan, plan_id, tenant_id_for(current_user), "Training plan")


@router.post("/plans/{plan_id}/revise", response_model=schemas.TrainingPlanRead)
def revise_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PLAN_MANAGE)),
):
    row = service.revise_plan(db, actor=current_user, plan_id=plan_id)
    db.commit()
    return _plans(db, tenant_id_for(current_user)).filter(models.TrainingPlan.id == row.id).one()


def _plan_transition(plan_id: str, target: str, payload: schemas.WorkflowDecision, db: Session, user: account_models.User):
    row = service.transition_plan(db, actor=user, plan_id=plan_id, target=target, comment=payload.comment)
    db.commit()
    return _plans(db, tenant_id_for(user)).filter(models.TrainingPlan.id == row.id).one()


@router.post("/plans/{plan_id}/submit", response_model=schemas.TrainingPlanRead)
def submit_plan(plan_id: str, payload: schemas.WorkflowDecision, db: Session = Depends(get_db), current_user: account_models.User = Depends(require_training_capability(Cap.PLAN_MANAGE))):
    return _plan_transition(plan_id, "SUBMITTED", payload, db, current_user)


@router.post("/plans/{plan_id}/review", response_model=schemas.TrainingPlanRead)
def review_plan(plan_id: str, payload: schemas.WorkflowDecision, db: Session = Depends(get_db), current_user: account_models.User = Depends(require_training_capability(Cap.PLAN_REVIEW))):
    return _plan_transition(plan_id, "REVIEWED", payload, db, current_user)


@router.post("/plans/{plan_id}/approve", response_model=schemas.TrainingPlanRead)
def approve_plan(plan_id: str, payload: schemas.WorkflowDecision, db: Session = Depends(get_db), current_user: account_models.User = Depends(require_training_capability(Cap.PLAN_APPROVE))):
    return _plan_transition(plan_id, "APPROVED", payload, db, current_user)


@router.post("/budgets/build", response_model=schemas.TrainingBudgetRead, status_code=201)
def build_budget(
    payload: schemas.BudgetBuildCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.BUDGET_MANAGE)),
):
    row = service.build_budget(db, actor=current_user, payload=payload)
    db.commit()
    row = db.query(models.TrainingBudget).options(selectinload(models.TrainingBudget.lines)).filter(models.TrainingBudget.id == row.id).one()
    return _budget_read(row)


@router.get("/budgets", response_model=list[schemas.TrainingBudgetRead])
def list_budgets(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.BUDGET_VIEW)),
):
    rows = db.query(models.TrainingBudget).options(selectinload(models.TrainingBudget.lines)).filter(models.TrainingBudget.amo_id == tenant_id_for(current_user)).order_by(models.TrainingBudget.created_at.desc()).all()
    return [_budget_read(row) for row in rows]


@router.post("/budgets/{budget_id}/revise", response_model=schemas.TrainingBudgetRead)
def revise_budget(
    budget_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.BUDGET_MANAGE)),
):
    row = service.revise_budget(db, actor=current_user, budget_id=budget_id)
    db.commit()
    row = db.query(models.TrainingBudget).options(selectinload(models.TrainingBudget.lines)).filter(
        models.TrainingBudget.id == row.id,
        models.TrainingBudget.amo_id == tenant_id_for(current_user),
    ).one()
    return _budget_read(row)


def _budget_transition(
    budget_id: str,
    target: str,
    payload: schemas.WorkflowDecision,
    db: Session,
    user: account_models.User,
):
    row = service.transition_budget(
        db,
        actor=user,
        budget_id=budget_id,
        target=target,
        comment=payload.comment,
    )
    db.commit()
    row = db.query(models.TrainingBudget).options(selectinload(models.TrainingBudget.lines)).filter(
        models.TrainingBudget.id == row.id,
        models.TrainingBudget.amo_id == tenant_id_for(user),
    ).one()
    return _budget_read(row)


@router.post("/budgets/{budget_id}/submit", response_model=schemas.TrainingBudgetRead)
def submit_budget(budget_id: str, payload: schemas.WorkflowDecision, db: Session = Depends(get_db), current_user: account_models.User = Depends(require_training_capability(Cap.BUDGET_MANAGE))):
    return _budget_transition(budget_id, "SUBMITTED", payload, db, current_user)


@router.post("/budgets/{budget_id}/review", response_model=schemas.TrainingBudgetRead)
def review_budget(budget_id: str, payload: schemas.WorkflowDecision, db: Session = Depends(get_db), current_user: account_models.User = Depends(require_training_capability(Cap.BUDGET_REVIEW))):
    return _budget_transition(budget_id, "REVIEWED", payload, db, current_user)


@router.post("/budgets/{budget_id}/approve", response_model=schemas.TrainingBudgetRead)
def approve_budget(budget_id: str, payload: schemas.WorkflowDecision, db: Session = Depends(get_db), current_user: account_models.User = Depends(require_training_capability(Cap.BUDGET_APPROVE))):
    return _budget_transition(budget_id, "APPROVED", payload, db, current_user)


@router.post("/attendance/windows", response_model=schemas.AttendanceWindowRead, status_code=201)
def open_attendance(
    payload: schemas.AttendanceWindowCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ATTENDANCE_MANAGE)),
):
    row, code = service.open_attendance_window(db, actor=current_user, payload=payload)
    db.commit()
    data = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    data["attendance_code"] = code
    return schemas.AttendanceWindowRead.model_validate(data)


@router.post("/attendance/self-sign", response_model=schemas.AttendanceEntryRead)
def self_sign(
    payload: schemas.AttendanceSelfSignCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ATTENDANCE_SIGN_SELF)),
):
    row = service.self_sign_attendance(db, actor=current_user, payload=payload)
    db.commit()
    db.refresh(row)
    return row


@router.post("/attendance/events/{event_id}/mark", response_model=schemas.AttendanceEntryRead)
def mark_attendance(
    event_id: str,
    payload: schemas.AttendanceAdminMarkCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ATTENDANCE_MANAGE)),
):
    row = service.mark_attendance(db, actor=current_user, event_id=event_id, payload=payload)
    db.commit()
    db.refresh(row)
    return row


@router.get("/attendance/events/{event_id}", response_model=list[schemas.AttendanceEntryRead])
def attendance_register(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ATTENDANCE_VIEW)),
):
    return db.query(models.TrainingAttendanceEntry).filter(models.TrainingAttendanceEntry.amo_id == tenant_id_for(current_user), models.TrainingAttendanceEntry.event_id == event_id).order_by(models.TrainingAttendanceEntry.signed_at).all()


@router.post("/attendance/{entry_id}/correct", response_model=schemas.AttendanceEntryRead)
def correct_attendance(
    entry_id: str,
    payload: schemas.AttendanceCorrectionCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ATTENDANCE_CORRECT)),
):
    row = service.correct_attendance(db, actor=current_user, entry_id=entry_id, payload=payload)
    db.commit()
    db.refresh(row)
    return row


@router.post("/attendance/events/{event_id}/certify", response_model=schemas.AttendanceWindowRead)
def certify_attendance(
    event_id: str,
    payload: schemas.AttendanceCertificationCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.SESSION_CLOSE)),
):
    row = service.certify_attendance(db, actor=current_user, event_id=event_id, note=payload.note)
    db.commit()
    db.refresh(row)
    return row


@router.get("/assessment-templates", response_model=list[schemas.AssessmentTemplateRead])
def list_assessment_templates(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_VIEW)),
):
    return db.query(models.TrainingAssessmentTemplate).filter(models.TrainingAssessmentTemplate.amo_id == tenant_id_for(current_user), models.TrainingAssessmentTemplate.active.is_(True)).order_by(models.TrainingAssessmentTemplate.code, models.TrainingAssessmentTemplate.revision_no.desc()).all()


@router.post("/assessment-templates", response_model=schemas.AssessmentTemplateRead, status_code=201)
def create_assessment_template(
    payload: schemas.AssessmentTemplateCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_CREATE)),
):
    row = service.create_assessment_template(db, actor=current_user, payload=payload)
    db.commit()
    db.refresh(row)
    return row


@router.get("/assessments", response_model=list[schemas.AssessmentRead])
def list_assessments(
    candidate_user_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_VIEW)),
):
    query = db.query(models.TrainingAssessmentInstance).filter(models.TrainingAssessmentInstance.amo_id == tenant_id_for(current_user))
    if candidate_user_id:
        query = query.filter(models.TrainingAssessmentInstance.candidate_user_id == candidate_user_id)
    if status:
        query = query.filter(models.TrainingAssessmentInstance.status == status.upper())
    return query.order_by(models.TrainingAssessmentInstance.created_at.desc()).limit(500).all()


@router.post("/assessments", response_model=schemas.AssessmentRead, status_code=201)
def create_assessment(
    payload: schemas.AssessmentCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_CREATE)),
):
    row = service.create_assessment(db, actor=current_user, payload=payload)
    db.commit()
    db.refresh(row)
    return row


@router.post("/assessments/{assessment_id}/submit", response_model=schemas.AssessmentRead)
def submit_assessment(
    assessment_id: str,
    payload: schemas.AssessmentSubmit,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_PERFORM)),
):
    row = service.submit_assessment(db, actor=current_user, assessment_id=assessment_id, payload=payload)
    db.commit()
    db.refresh(row)
    return row


@router.post("/assessments/{assessment_id}/review", response_model=schemas.AssessmentRead)
def review_assessment(
    assessment_id: str,
    payload: schemas.AssessmentReview,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_REVIEW)),
):
    row = service.review_assessment(db, actor=current_user, assessment_id=assessment_id, payload=payload)
    db.commit()
    db.refresh(row)
    return row


@router.post("/experience/logs", status_code=201)
def create_experience_log(
    payload: schemas.ExperienceLogCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_PERFORM)),
):
    row = service.create_experience_log(db, actor=current_user, payload=payload)
    db.commit()
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


@router.post("/experience/reviews", status_code=201)
def create_experience_review(
    payload: schemas.ExperienceReviewCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_REVIEW)),
):
    row = service.review_experience(db, actor=current_user, payload=payload)
    db.commit()
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


@router.get("/authorization-cases", response_model=list[schemas.AuthorizationCaseRead])
def list_authorization_cases(
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.AUTHORIZATION_VIEW)),
):
    query = db.query(models.TrainingAuthorizationCase).filter(models.TrainingAuthorizationCase.amo_id == tenant_id_for(current_user))
    if status:
        query = query.filter(models.TrainingAuthorizationCase.status == status.upper())
    return query.order_by(models.TrainingAuthorizationCase.updated_at.desc()).limit(500).all()


@router.post("/authorization-cases", response_model=schemas.AuthorizationCaseRead, status_code=201)
def create_authorization_case(
    payload: schemas.AuthorizationCaseCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.AUTHORIZATION_PREPARE)),
):
    row = service.create_authorization_case(db, actor=current_user, payload=payload)
    db.commit()
    db.refresh(row)
    return row


@router.get("/authorization-cases/{case_id}/readiness", response_model=schemas.AuthorizationReadiness)
def authorization_readiness(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.AUTHORIZATION_VIEW)),
):
    row = service._get_scoped(db, models.TrainingAuthorizationCase, case_id, tenant_id_for(current_user), "Authorization case")
    result = service.compute_authorization_readiness(db, case=row)
    db.commit()
    return result


@router.post("/authorization-cases/{case_id}/committee-decisions", status_code=201)
def committee_decision(
    case_id: str,
    payload: schemas.CommitteeDecisionCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.AUTHORIZATION_COMMITTEE_DECIDE)),
):
    row = service.decide_committee(db, actor=current_user, case_id=case_id, payload=payload)
    db.commit()
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


@router.post("/authorization-cases/{case_id}/issue")
def issue_authorization(
    case_id: str,
    payload: schemas.AuthorizationIssueCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.AUTHORIZATION_ISSUE)),
):
    row = service.issue_authorization(db, actor=current_user, case_id=case_id, payload=payload)
    db.commit()
    return {
        "id": str(row.id), "user_id": str(row.user_id), "authorisation_type_id": str(row.authorisation_type_id),
        "scope_text": row.scope_text, "effective_from": row.effective_from,
        "expires_at": row.expires_at, "granted_by_user_id": row.granted_by_user_id,
    }


@router.get("/effectiveness", response_model=list[schemas.EffectivenessRead])
def list_effectiveness(
    course_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_VIEW)),
):
    query = db.query(models.TrainingEffectivenessEvaluation).filter(models.TrainingEffectivenessEvaluation.amo_id == tenant_id_for(current_user))
    if course_id:
        query = query.filter(models.TrainingEffectivenessEvaluation.course_id == course_id)
    return query.order_by(models.TrainingEffectivenessEvaluation.created_at.desc()).limit(500).all()


@router.post("/effectiveness", response_model=schemas.EffectivenessRead, status_code=201)
def create_effectiveness(
    payload: schemas.EffectivenessCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_PERFORM)),
):
    row = service.create_effectiveness(db, actor=current_user, payload=payload)
    db.commit()
    db.refresh(row)
    return row


@router.post("/competence-reviews", status_code=201)
def create_competence_review(
    payload: schemas.CompetenceReviewCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_PERFORM)),
):
    row = service.create_competence_review(db, actor=current_user, payload=payload)
    db.commit()
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


@router.get("/remedial-actions")
def list_remedial_actions(
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_VIEW)),
):
    query = db.query(models.TrainingRemedialAction).filter(models.TrainingRemedialAction.amo_id == tenant_id_for(current_user))
    if status:
        query = query.filter(models.TrainingRemedialAction.status == status.upper())
    rows = query.order_by(models.TrainingRemedialAction.due_date.asc()).limit(500).all()
    return [{column.name: getattr(row, column.name) for column in row.__table__.columns} for row in rows]


@router.post("/remedial-actions", status_code=201)
def create_remedial_action(
    payload: schemas.RemedialActionCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_CREATE)),
):
    row = service.create_remedial_action(db, actor=current_user, payload=payload)
    db.commit()
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


@router.get("/courses/{course_id}/next-batch", response_model=schemas.NextBatchRead)
def next_batch(
    course_id: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PLAN_VIEW)),
):
    return service.next_batch(db, amo_id=tenant_id_for(current_user), course_id=course_id, limit=limit)


@router.get("/courses/{course_id}/audit", response_model=schemas.CourseAuditRead)
def course_audit(
    course_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.REPORT_VIEW)),
):
    return service.course_audit(db, amo_id=tenant_id_for(current_user), course_id=course_id)


@router.get("/reports/plans/{plan_id}.pdf")
def export_plan_pdf(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.REPORT_EXPORT)),
):
    amo_id = tenant_id_for(current_user)
    plan = _plans(db, amo_id).filter(models.TrainingPlan.id == plan_id).first()
    if not plan:
        return Response(status_code=404)
    amo = db.query(account_models.AMO).filter(account_models.AMO.id == amo_id).one()
    return Response(
        content=reports.plan_pdf(db, plan=plan, amo=amo), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="training-plan-{plan.plan_year}-rev-{plan.revision_no}.pdf"'},
    )


@router.get("/reports/budgets/{budget_id}.xlsx")
def export_budget_xlsx(
    budget_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.REPORT_EXPORT)),
):
    amo_id = tenant_id_for(current_user)
    budget = db.query(models.TrainingBudget).options(selectinload(models.TrainingBudget.lines)).filter(models.TrainingBudget.id == budget_id, models.TrainingBudget.amo_id == amo_id).first()
    if not budget:
        return Response(status_code=404)
    amo = db.query(account_models.AMO).filter(account_models.AMO.id == amo_id).one()
    return Response(
        content=reports.budget_xlsx(budget=budget, amo=amo),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="training-budget-rev-{budget.revision_no}.xlsx"'},
    )


@router.get("/reports/attendance/{event_id}.pdf")
def export_attendance_pdf(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.REPORT_EXPORT)),
):
    amo_id = tenant_id_for(current_user)
    event = db.query(legacy_models.TrainingEvent).filter(legacy_models.TrainingEvent.id == event_id, legacy_models.TrainingEvent.amo_id == amo_id).first()
    if not event:
        return Response(status_code=404)
    entries = db.query(models.TrainingAttendanceEntry).filter(models.TrainingAttendanceEntry.amo_id == amo_id, models.TrainingAttendanceEntry.event_id == event_id).order_by(models.TrainingAttendanceEntry.signed_at).all()
    window = db.query(models.TrainingAttendanceWindow).filter(models.TrainingAttendanceWindow.amo_id == amo_id, models.TrainingAttendanceWindow.event_id == event_id).order_by(models.TrainingAttendanceWindow.opened_at.desc()).first()
    amo = db.query(account_models.AMO).filter(account_models.AMO.id == amo_id).one()
    return Response(
        content=reports.attendance_pdf(db, event=event, entries=entries, window=window, amo=amo), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="attendance-register-{event_id}.pdf"'},
    )
