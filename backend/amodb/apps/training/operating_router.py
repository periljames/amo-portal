from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, selectinload

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import operating_models as models
from . import operating_schemas as schemas
from . import operating_service as service
from . import operating_reports as reports
from . import readiness_service
from . import exchange_rates
from . import models as legacy_models
from .permissions import (
    TrainingCapability as Cap,
    require_training_capability,
    tenant_id_for,
    training_capabilities_for,
)


router = APIRouter(prefix="/operating", tags=["training-operating-system"])


def _page(*, items: list, total: int, limit: int, offset: int, filtered_totals: dict | None = None) -> dict:
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
        "filtered_totals": filtered_totals or {},
    }


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


@router.get("/reference/exchange-rate", response_model=schemas.ExchangeRateQuoteRead)
def reference_exchange_rate(
    base: Annotated[str, Query(min_length=3, max_length=3)],
    quote: Annotated[str, Query(min_length=3, max_length=3)],
    current_user: account_models.User = Depends(require_training_capability(Cap.BUDGET_VIEW)),
):
    del current_user
    try:
        return schemas.ExchangeRateQuoteRead(**exchange_rates.get_exchange_rate_quote(base, quote))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_CURRENCY", "message": str(exc)}) from exc
    except exchange_rates.ExchangeRateUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "EXCHANGE_RATE_UNAVAILABLE",
                "message": str(exc),
                "action": "Retry the live quote or enter an approved finance rate and source.",
            },
        ) from exc


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
    offset: Annotated[int, Query(ge=0)] = 0,
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
    rows = query.order_by(account_models.User.full_name).offset(offset).limit(limit).all()
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


@router.get("/source-health", response_model=schemas.SourceHealthRead)
def training_source_health(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    """Expose dependency health so an outage is never rendered as a truthful zero."""
    return readiness_service.source_health(db, actor=current_user)


@router.get("/people", response_model=schemas.PersonCompliancePage)
def paged_people_compliance(
    search: str | None = None,
    active: bool | None = True,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PEOPLE_VIEW)),
):
    return readiness_service.people_compliance_page(
        db, actor=current_user, search=search, active=active, limit=limit, offset=offset,
    )


@router.get("/reference/search")
def search_canonical_reference(
    source: Annotated[str, Query(pattern="^(PEOPLE|COURSES|PROVIDERS|LOCATIONS|INSTRUCTORS|AUTHORIZATION_TYPES|DMS|QMS)$")],
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    return readiness_service.canonical_references(db, actor=current_user, source=source, search=search, limit=limit)


@router.get("/settings", response_model=schemas.TrainingOperatingSettingsRead)
def get_settings(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    return service.read_settings(db, amo_id=tenant_id_for(current_user))


@router.put("/settings", response_model=schemas.TrainingOperatingSettingsRead)
def put_settings(
    payload: schemas.TrainingOperatingSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
):
    row = service.update_settings(db, actor=current_user, payload=payload)
    db.commit()
    db.refresh(row)
    data = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    data["configured"] = True
    return schemas.TrainingOperatingSettingsRead.model_validate(data)


@router.get("/setup/versions", response_model=list[schemas.SetupVersionRead])
def list_setup_versions(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    return db.query(models.TrainingSetupVersion).filter(
        models.TrainingSetupVersion.amo_id == tenant_id_for(current_user),
    ).order_by(models.TrainingSetupVersion.version_no.desc()).all()


@router.post("/setup/versions", response_model=schemas.SetupVersionRead, status_code=201)
def create_setup_version(
    payload: schemas.SetupVersionCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
):
    row = readiness_service.create_setup_version(db, actor=current_user, payload=payload)
    db.commit(); db.refresh(row)
    return row


@router.post("/setup/versions/{version_id}/validate", response_model=schemas.SetupVersionRead)
def validate_setup_version(
    version_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
):
    row = db.query(models.TrainingSetupVersion).filter(
        models.TrainingSetupVersion.id == version_id,
        models.TrainingSetupVersion.amo_id == tenant_id_for(current_user),
    ).first()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Setup version was not found in this tenant.")
    readiness_service.validate_setup_version(db, actor=current_user, row=row)
    db.commit(); db.refresh(row)
    return row


@router.post("/setup/versions/{version_id}/transition", response_model=schemas.SetupVersionRead)
def transition_setup_version(
    version_id: str,
    payload: schemas.SetupVersionTransition,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
):
    row = db.query(models.TrainingSetupVersion).filter(
        models.TrainingSetupVersion.id == version_id,
        models.TrainingSetupVersion.amo_id == tenant_id_for(current_user),
    ).first()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Setup version was not found in this tenant.")
    row = readiness_service.transition_setup_version(db, actor=current_user, row=row, payload=payload)
    db.commit(); db.refresh(row)
    return row


@router.get("/setup/configuration-export")
def export_training_configuration(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
):
    version = db.query(models.TrainingSetupVersion).filter(
        models.TrainingSetupVersion.amo_id == tenant_id_for(current_user),
        models.TrainingSetupVersion.status == "ACTIVE",
    ).order_by(models.TrainingSetupVersion.version_no.desc()).first()
    if version:
        return {"version": version.version_no, "status": version.status, "snapshot": version.snapshot, "validation": version.validation_result}
    return {"version": None, "status": "NOT_CONFIGURED", "snapshot": {}, "validation": {"status": "NOT_RUN"}}


@router.get("/changes", response_model=list[schemas.ChangeRequestRead])
def list_change_requests(
    object_type: str | None = None,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    query = db.query(models.TrainingChangeRequest).filter(models.TrainingChangeRequest.amo_id == tenant_id_for(current_user))
    if object_type:
        query = query.filter(models.TrainingChangeRequest.object_type == object_type.upper())
    if status:
        query = query.filter(models.TrainingChangeRequest.status == status.upper())
    return query.order_by(models.TrainingChangeRequest.created_at.desc()).limit(limit).all()


@router.post("/changes/preview", response_model=schemas.ChangeRequestRead, status_code=201)
def preview_controlled_change(
    payload: schemas.ChangePreviewCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    row = readiness_service.create_change_preview(db, actor=current_user, payload=payload)
    db.commit(); db.refresh(row)
    return row


@router.post("/changes/{change_id}/decision", response_model=schemas.ChangeRequestRead)
def decide_controlled_change(
    change_id: str,
    payload: schemas.ChangeDecision,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    row = db.query(models.TrainingChangeRequest).filter(
        models.TrainingChangeRequest.id == change_id,
        models.TrainingChangeRequest.amo_id == tenant_id_for(current_user),
    ).first()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Controlled change preview was not found.")
    row = readiness_service.decide_change_request(db, actor=current_user, row=row, payload=payload)
    db.commit(); db.refresh(row)
    return row


@router.get("/workflows", response_model=schemas.WorkflowPage)
def list_workflows(
    workflow_type: str | None = None,
    status: str | None = None,
    subject_user_id: str | None = None,
    owner_user_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    query = db.query(models.TrainingWorkflowInstance).filter(models.TrainingWorkflowInstance.amo_id == tenant_id_for(current_user))
    if workflow_type:
        query = query.filter(models.TrainingWorkflowInstance.workflow_type == workflow_type)
    if status:
        query = query.filter(models.TrainingWorkflowInstance.status == status)
    if subject_user_id:
        query = query.filter(models.TrainingWorkflowInstance.subject_user_id == subject_user_id)
    if owner_user_id:
        query = query.filter(models.TrainingWorkflowInstance.owner_user_id == owner_user_id)
    total = int(query.count())
    rows = query.order_by(models.TrainingWorkflowInstance.due_at.asc().nullslast(), models.TrainingWorkflowInstance.created_at.desc()).offset(offset).limit(limit).all()
    items = [readiness_service.workflow_read(db, row) for row in rows]
    return _page(items=items, total=total, limit=limit, offset=offset)


@router.get("/my-tasks", response_model=schemas.WorkflowPage)
def list_my_training_tasks(
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = tenant_id_for(current_user)
    query = db.query(models.TrainingWorkflowInstance).filter(
        models.TrainingWorkflowInstance.amo_id == amo_id,
        or_(models.TrainingWorkflowInstance.subject_user_id == str(current_user.id), models.TrainingWorkflowInstance.owner_user_id == str(current_user.id)),
        models.TrainingWorkflowInstance.status.in_(["DRAFT", "RETURNED", "SUBMITTED", "APPROVED"]),
    )
    total = int(query.count())
    rows = query.order_by(models.TrainingWorkflowInstance.due_at.asc().nullslast(), models.TrainingWorkflowInstance.created_at.desc()).offset(offset).limit(limit).all()
    return _page(items=[readiness_service.workflow_read(db, row) for row in rows], total=total, limit=limit, offset=offset)


@router.post("/workflows", response_model=schemas.WorkflowInstanceRead, status_code=201)
def create_workflow(
    payload: schemas.WorkflowInstanceCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PEOPLE_MANAGE)),
):
    row = readiness_service.create_workflow(db, actor=current_user, payload=payload)
    db.commit(); db.refresh(row)
    return readiness_service.workflow_read(db, row)


@router.post("/workflows/{workflow_id}/steps/{step_id}/complete", response_model=schemas.WorkflowStepRead)
def complete_workflow_step(
    workflow_id: str,
    step_id: str,
    payload: schemas.WorkflowStepComplete,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = tenant_id_for(current_user)
    workflow = db.query(models.TrainingWorkflowInstance).filter(models.TrainingWorkflowInstance.id == workflow_id, models.TrainingWorkflowInstance.amo_id == amo_id).first()
    step = db.query(models.TrainingWorkflowStep).filter(models.TrainingWorkflowStep.id == step_id, models.TrainingWorkflowStep.amo_id == amo_id, models.TrainingWorkflowStep.workflow_instance_id == workflow_id).first()
    if not workflow or not step:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Workflow step was not found in this tenant.")
    row = readiness_service.complete_workflow_step(db, actor=current_user, workflow=workflow, step=step, payload=payload)
    db.commit(); db.refresh(row)
    return row


@router.post("/workflows/{workflow_id}/transition", response_model=schemas.WorkflowInstanceRead)
def transition_workflow(
    workflow_id: str,
    payload: schemas.WorkflowTransition,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    row = db.query(models.TrainingWorkflowInstance).filter(models.TrainingWorkflowInstance.id == workflow_id, models.TrainingWorkflowInstance.amo_id == tenant_id_for(current_user)).first()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Workflow was not found in this tenant.")
    row = readiness_service.transition_workflow(db, actor=current_user, row=row, payload=payload)
    db.commit(); db.refresh(row)
    return readiness_service.workflow_read(db, row)


@router.post("/sessions/{event_id}/invitations", response_model=list[schemas.InvitationRead])
def send_session_invitations(
    event_id: str,
    payload: schemas.InvitationCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.SESSION_MANAGE)),
):
    rows = readiness_service.send_session_invitations(db, actor=current_user, event_id=event_id, payload=payload)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


@router.get("/sessions/{event_id}/invitations", response_model=schemas.InvitationPage)
def list_session_invitations(
    event_id: str,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.SESSION_VIEW)),
):
    query = db.query(models.TrainingSessionInvitation).filter(models.TrainingSessionInvitation.amo_id == tenant_id_for(current_user), models.TrainingSessionInvitation.event_id == event_id)
    if status:
        query = query.filter(models.TrainingSessionInvitation.delivery_status == status)
    total = int(query.count())
    rows = query.order_by(models.TrainingSessionInvitation.created_at.desc()).offset(offset).limit(limit).all()
    return _page(items=rows, total=total, limit=limit, offset=offset)


@router.post("/invitations/{invitation_id}/rsvp", response_model=schemas.InvitationRead)
def respond_to_invitation(
    invitation_id: str,
    payload: schemas.InvitationRsvp,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    row = db.query(models.TrainingSessionInvitation).filter(models.TrainingSessionInvitation.id == invitation_id, models.TrainingSessionInvitation.amo_id == tenant_id_for(current_user)).first()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Training invitation was not found.")
    row = readiness_service.invitation_rsvp(db, actor=current_user, invitation=row, response=payload.response)
    db.commit(); db.refresh(row)
    return row


@router.get("/report-definitions", response_model=list[schemas.ReportDefinitionRead])
def list_report_definitions(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.REPORT_VIEW)),
):
    return db.query(models.TrainingReportDefinition).filter(models.TrainingReportDefinition.amo_id == tenant_id_for(current_user)).order_by(models.TrainingReportDefinition.name).all()


@router.post("/report-definitions", response_model=schemas.ReportDefinitionRead, status_code=201)
def create_report_definition(
    payload: schemas.ReportDefinitionCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
):
    row = models.TrainingReportDefinition(amo_id=tenant_id_for(current_user), created_by_user_id=str(current_user.id), **payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return row


@router.get("/report-jobs", response_model=schemas.ReportJobPage)
def list_report_jobs(
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.REPORT_VIEW)),
):
    query = db.query(models.TrainingReportJob).filter(models.TrainingReportJob.amo_id == tenant_id_for(current_user))
    if status:
        query = query.filter(models.TrainingReportJob.status == status)
    total = int(query.count())
    rows = query.order_by(models.TrainingReportJob.created_at.desc()).offset(offset).limit(limit).all()
    return _page(items=rows, total=total, limit=limit, offset=offset)


@router.post("/report-jobs", response_model=schemas.ReportJobRead, status_code=202)
def queue_report_job(
    payload: schemas.ReportJobCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.REPORT_EXPORT)),
):
    row = readiness_service.create_report_job(db, actor=current_user, payload=payload)
    db.commit(); db.refresh(row)
    return row


@router.get("/report-jobs/{job_id}/download")
def download_report_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.REPORT_EXPORT)),
):
    row = db.query(models.TrainingReportJob).filter(
        models.TrainingReportJob.id == job_id,
        models.TrainingReportJob.amo_id == tenant_id_for(current_user),
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Training report job was not found in this tenant.")
    if row.status != "COMPLETED":
        raise HTTPException(status_code=409, detail="Training report artifact is not ready for download.")
    from amodb.jobs import training_report_jobs
    try:
        path = training_report_jobs.resolved_artifact_path(row)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    media_types = {".pdf": "application/pdf", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".csv": "text/csv"}
    filename = f"training-{row.report_code.lower().replace('_', '-')}-{row.id}{path.suffix}"
    return FileResponse(path, media_type=media_types.get(path.suffix.lower(), "application/octet-stream"), filename=filename)


@router.get("/saved-views", response_model=list[schemas.SavedViewRead])
def list_saved_views(
    workspace: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    query = db.query(models.TrainingSavedView).filter(models.TrainingSavedView.amo_id == tenant_id_for(current_user), models.TrainingSavedView.user_id == str(current_user.id))
    if workspace:
        query = query.filter(models.TrainingSavedView.workspace == workspace)
    return query.order_by(models.TrainingSavedView.is_default.desc(), models.TrainingSavedView.name).all()


@router.post("/saved-views", response_model=schemas.SavedViewRead)
def save_workspace_view(
    payload: schemas.SavedViewCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    row = readiness_service.upsert_saved_view(db, actor=current_user, payload=payload)
    db.commit(); db.refresh(row)
    return row


@router.get("/registers/{register_name}")
def paged_training_register(
    register_name: str,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    """Uniform tenant pagination contract for every high-volume operating register."""
    registry = {
        "assessments": (models.TrainingAssessmentInstance, models.TrainingAssessmentInstance.created_at),
        "authorizations": (models.TrainingAuthorizationCase, models.TrainingAuthorizationCase.created_at),
        "budgets": (models.TrainingBudget, models.TrainingBudget.created_at),
        "certificates": (legacy_models.TrainingCertificateIssue, legacy_models.TrainingCertificateIssue.issued_at),
        "records": (legacy_models.TrainingRecord, legacy_models.TrainingRecord.created_at),
        "sessions": (legacy_models.TrainingEvent, legacy_models.TrainingEvent.starts_on),
    }
    key = register_name.strip().lower()
    if key not in registry:
        raise HTTPException(status_code=404, detail="Unsupported Training register.")
    model, order_column = registry[key]
    query = db.query(model).filter(model.amo_id == tenant_id_for(current_user))
    if status and hasattr(model, "status"):
        query = query.filter(model.status == status.upper())
    elif status and hasattr(model, "record_status"):
        query = query.filter(model.record_status == status.upper())
    total = int(query.count())
    rows = query.order_by(order_column.desc()).offset(offset).limit(limit).all()
    if key == "budgets":
        items = [_budget_read(row).model_dump(mode="json") for row in rows]
    else:
        items = [{column.name: getattr(row, column.name) for column in row.__table__.columns} for row in rows]
    return _page(items=items, total=total, limit=limit, offset=offset)


@router.get("/setup/readiness", response_model=schemas.SetupReadinessRead)
def get_setup_readiness(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    return service.setup_readiness(db, actor=current_user)


@router.get("/settings/revisions", response_model=list[schemas.ConfigurationRevisionRead])
def list_configuration_revisions(
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
):
    return db.query(models.TrainingConfigurationRevision).filter(
        models.TrainingConfigurationRevision.amo_id == tenant_id_for(current_user),
    ).order_by(models.TrainingConfigurationRevision.revision_no.desc()).limit(limit).all()


@router.get("/reference/resources", response_model=list[schemas.TrainingReferenceResourceRead])
def list_reference_resources(
    resource_type: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    query = db.query(models.TrainingReferenceResource).filter(models.TrainingReferenceResource.amo_id == tenant_id_for(current_user))
    if resource_type:
        query = query.filter(models.TrainingReferenceResource.resource_type == resource_type.upper())
    if not include_inactive:
        query = query.filter(models.TrainingReferenceResource.active.is_(True))
    return query.order_by(models.TrainingReferenceResource.resource_type, models.TrainingReferenceResource.name).all()


@router.post("/reference/resources", response_model=schemas.TrainingReferenceResourceRead, status_code=201)
def create_reference_resource(
    payload: schemas.TrainingReferenceResourceCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
):
    row = service.create_reference_resource(db, actor=current_user, payload=payload)
    db.commit()
    db.refresh(row)
    return row


@router.put("/reference/resources/{resource_id}", response_model=schemas.TrainingReferenceResourceRead)
def update_reference_resource(
    resource_id: str,
    payload: schemas.TrainingReferenceResourceCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
):
    row = service.update_reference_resource(db, actor=current_user, resource_id=resource_id, payload=payload)
    db.commit()
    db.refresh(row)
    return row


@router.get("/controlled-forms", response_model=list[schemas.ControlledFormTemplateRead])
def list_controlled_forms(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
):
    return db.query(models.TrainingControlledFormTemplate).filter(
        models.TrainingControlledFormTemplate.amo_id == tenant_id_for(current_user),
    ).order_by(models.TrainingControlledFormTemplate.code, models.TrainingControlledFormTemplate.revision_no.desc()).all()


@router.post("/controlled-forms", response_model=schemas.ControlledFormTemplateRead, status_code=201)
def create_controlled_form(
    payload: schemas.ControlledFormTemplateCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
):
    row = service.create_controlled_form(db, actor=current_user, payload=payload)
    db.commit()
    db.refresh(row)
    return row


@router.post("/controlled-forms/{form_id}/transition", response_model=schemas.ControlledFormTemplateRead)
def transition_controlled_form(
    form_id: str,
    payload: schemas.ControlledFormTransition,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
):
    row = service.transition_controlled_form(db, actor=current_user, form_id=form_id, target=payload.target)
    db.commit()
    db.refresh(row)
    return row


@router.get("/automation/status", response_model=schemas.AutomationStatusRead)
def get_automation_status(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PLAN_VIEW)),
):
    return service.automation_status(db, actor=current_user)


@router.post("/automation/run", response_model=schemas.AutomationRunRead)
def run_automation(
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PLAN_MANAGE)),
):
    row = service.run_monthly_plan_automation(db, actor=current_user, trigger="MANUAL", force=force)
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


@router.get("/plans/summaries", response_model=list[schemas.TrainingPlanSummaryRead])
def list_plan_summaries(
    year: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PLAN_VIEW)),
):
    amo_id = tenant_id_for(current_user)
    query = db.query(
        models.TrainingPlan,
        func.count(models.TrainingPlanItem.id),
        func.coalesce(func.sum(models.TrainingPlanItem.participant_count), 0),
        func.coalesce(func.sum(models.TrainingPlanItem.estimated_total_cost), 0),
        func.coalesce(func.min(models.TrainingPlanItem.original_currency), "USD"),
    ).outerjoin(
        models.TrainingPlanItem,
        and_(models.TrainingPlanItem.plan_id == models.TrainingPlan.id, models.TrainingPlanItem.amo_id == amo_id),
    ).filter(models.TrainingPlan.amo_id == amo_id)
    if year:
        query = query.filter(models.TrainingPlan.plan_year == year)
    rows = query.group_by(models.TrainingPlan.id).order_by(
        models.TrainingPlan.plan_year.desc(), models.TrainingPlan.revision_no.desc()
    ).offset(offset).limit(limit).all()
    return [
        schemas.TrainingPlanSummaryRead(
            id=str(plan.id), plan_year=plan.plan_year, revision_no=plan.revision_no,
            title=plan.title, status=plan.status, form_reference=plan.form_reference,
            notes=plan.notes, item_count=int(item_count or 0),
            participant_count=int(participant_count or 0), estimated_total_cost=estimated_total_cost or 0,
            original_currency=original_currency or "USD", created_at=plan.created_at, updated_at=plan.updated_at,
        )
        for plan, item_count, participant_count, estimated_total_cost, original_currency in rows
    ]


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


@router.get("/plans/{plan_id}/obligations", response_model=schemas.TrainingPlanObligationPage)
def list_plan_obligations(
    plan_id: str,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PLAN_VIEW)),
):
    amo_id = tenant_id_for(current_user)
    service._get_scoped(db, models.TrainingPlan, plan_id, amo_id, "Training plan")
    base_query = db.query(models.TrainingPlanParticipant, models.TrainingPlanItem).join(
        models.TrainingPlanItem,
        models.TrainingPlanParticipant.plan_item_id == models.TrainingPlanItem.id,
    ).filter(
        models.TrainingPlanParticipant.amo_id == amo_id,
        models.TrainingPlanItem.amo_id == amo_id,
        models.TrainingPlanItem.plan_id == plan_id,
    )
    month_rows = db.query(
        models.TrainingPlanItem.planned_month,
        func.count(models.TrainingPlanParticipant.id),
    ).join(
        models.TrainingPlanParticipant,
        models.TrainingPlanParticipant.plan_item_id == models.TrainingPlanItem.id,
    ).filter(
        models.TrainingPlanItem.amo_id == amo_id,
        models.TrainingPlanParticipant.amo_id == amo_id,
        models.TrainingPlanItem.plan_id == plan_id,
    ).group_by(models.TrainingPlanItem.planned_month).all()
    month_counts = [0] * 12
    for month_number, count in month_rows:
        month_counts[(int(month_number or 1) - 1)] = int(count or 0)
    if month:
        base_query = base_query.filter(models.TrainingPlanItem.planned_month == month)
    total = base_query.count()
    rows = base_query.order_by(
        models.TrainingPlanItem.planned_month.asc(),
        models.TrainingPlanParticipant.planned_due_date.asc().nullslast(),
        models.TrainingPlanParticipant.person_name_snapshot.asc(),
    ).offset(offset).limit(limit).all()
    items = [
        schemas.TrainingPlanObligationRead(
            key=f"{item.id}:{participant.id}", plan_item_id=str(item.id), participant_id=str(participant.id),
            month=int(item.planned_month or 1), course_code=item.course_code_snapshot,
            course_name=item.course_name_snapshot, manual_reference=item.manual_reference,
            user_id=str(participant.user_id), person_name=participant.person_name_snapshot,
            staff_code=participant.staff_code_snapshot, last_completion_date=participant.last_completion_date,
            expiry_date=participant.expiry_date, planned_due_date=participant.planned_due_date,
            obligation_status=participant.obligation_status, source_type=participant.source_type,
            source_record_id=participant.source_record_id, source_reference=participant.source_reference,
            status=participant.status,
        )
        for participant, item in rows
    ]
    return schemas.TrainingPlanObligationPage(items=items, total=total, limit=limit, offset=offset, month_counts=month_counts)


def _plan_course_key():
    return func.coalesce(
        models.TrainingPlanItem.course_id,
        models.TrainingPlanItem.course_code_snapshot,
        models.TrainingPlanItem.course_name_snapshot,
    )


@router.get("/plans/{plan_id}/matrix", response_model=schemas.TrainingPlanMatrixPage)
def get_plan_matrix(
    plan_id: str,
    search: str | None = None,
    training_kind: str | None = None,
    preview_limit: Annotated[int, Query(ge=0, le=5)] = 5,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PLAN_VIEW)),
):
    amo_id = tenant_id_for(current_user)
    plan = service._get_scoped(db, models.TrainingPlan, plan_id, amo_id, "Training plan")
    course_key = _plan_course_key()
    scoped = db.query(models.TrainingPlanItem, models.TrainingPlanParticipant).join(
        models.TrainingPlanParticipant,
        models.TrainingPlanParticipant.plan_item_id == models.TrainingPlanItem.id,
    ).filter(
        models.TrainingPlanItem.amo_id == amo_id,
        models.TrainingPlanParticipant.amo_id == amo_id,
        models.TrainingPlanItem.plan_id == plan_id,
    )

    kind_counts = {
        str(kind or "OTHER"): int(count or 0)
        for kind, count in scoped.with_entities(
            models.TrainingPlanItem.training_kind,
            func.count(func.distinct(course_key)),
        ).group_by(models.TrainingPlanItem.training_kind).all()
    }
    if search and search.strip():
        token = f"%{search.strip()}%"
        scoped = scoped.filter(or_(
            models.TrainingPlanItem.course_code_snapshot.ilike(token),
            models.TrainingPlanItem.course_name_snapshot.ilike(token),
        ))
    if training_kind and training_kind.strip():
        scoped = scoped.filter(models.TrainingPlanItem.training_kind == training_kind.strip().upper())

    grouped = scoped.with_entities(
        course_key.label("course_key"),
        func.min(models.TrainingPlanItem.course_id).label("course_id"),
        func.min(models.TrainingPlanItem.course_code_snapshot).label("course_code"),
        func.min(models.TrainingPlanItem.course_name_snapshot).label("course_name"),
        func.min(models.TrainingPlanItem.training_kind).label("training_kind"),
        func.min(models.TrainingPlanItem.provider_mode).label("provider_mode"),
        func.count(func.distinct(models.TrainingPlanParticipant.user_id)).label("personnel_count"),
    ).group_by(course_key).subquery()
    total = int(db.query(func.count()).select_from(grouped).scalar() or 0)
    course_rows = db.query(grouped).order_by(grouped.c.course_code.asc().nullslast(), grouped.c.course_name.asc()).offset(offset).limit(limit).all()
    selected_keys = [str(row.course_key) for row in course_rows]

    counts_by_cell: dict[tuple[str, int], int] = {}
    preview_by_cell: dict[tuple[str, int], list[schemas.TrainingPlanMatrixPerson]] = {}
    if selected_keys:
        cell_rows = scoped.with_entities(
            course_key.label("course_key"),
            models.TrainingPlanItem.planned_month,
            func.count(func.distinct(models.TrainingPlanParticipant.user_id)),
        ).filter(course_key.in_(selected_keys)).group_by(course_key, models.TrainingPlanItem.planned_month).all()
        counts_by_cell = {
            (str(key), int(month or 1)): int(count or 0)
            for key, month, count in cell_rows
        }
        if preview_limit:
            deduplicated = scoped.with_entities(
                course_key.label("course_key"),
                models.TrainingPlanItem.planned_month.label("planned_month"),
                models.TrainingPlanParticipant.user_id.label("user_id"),
                func.min(models.TrainingPlanParticipant.person_name_snapshot).label("person_name"),
                func.min(models.TrainingPlanParticipant.staff_code_snapshot).label("staff_code"),
                func.min(models.TrainingPlanParticipant.planned_due_date).label("planned_due_date"),
                func.min(models.TrainingPlanParticipant.expiry_date).label("expiry_date"),
                func.min(models.TrainingPlanParticipant.obligation_status).label("obligation_status"),
            ).filter(course_key.in_(selected_keys)).group_by(
                course_key,
                models.TrainingPlanItem.planned_month,
                models.TrainingPlanParticipant.user_id,
            ).subquery()
            ranked = db.query(
                deduplicated,
                func.row_number().over(
                    partition_by=(deduplicated.c.course_key, deduplicated.c.planned_month),
                    order_by=(
                        deduplicated.c.planned_due_date.asc().nullslast(),
                        deduplicated.c.person_name.asc(),
                    ),
                ).label("row_no"),
            ).subquery()
            for row in db.query(ranked).filter(ranked.c.row_no <= preview_limit).all():
                key = (str(row.course_key), int(row.planned_month or 1))
                preview_by_cell.setdefault(key, []).append(schemas.TrainingPlanMatrixPerson(
                    user_id=str(row.user_id),
                    person_name=row.person_name,
                    staff_code=row.staff_code,
                    planned_due_date=row.planned_due_date,
                    expiry_date=row.expiry_date,
                    obligation_status=row.obligation_status,
                ))

    items = []
    for row in course_rows:
        key = str(row.course_key)
        cells = [
            schemas.TrainingPlanMatrixCell(
                month=month,
                personnel_count=counts_by_cell.get((key, month), 0),
                preview=preview_by_cell.get((key, month), []),
            )
            for month in range(1, 13)
        ]
        items.append(schemas.TrainingPlanMatrixCourse(
            course_key=key,
            course_id=row.course_id,
            course_code=row.course_code,
            course_name=row.course_name,
            training_kind=row.training_kind or "OTHER",
            provider_mode=row.provider_mode or "INTERNAL",
            personnel_count=int(row.personnel_count or 0),
            cells=cells,
        ))
    return schemas.TrainingPlanMatrixPage(
        plan_id=plan_id,
        plan_year=plan.plan_year,
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
        kind_counts=kind_counts,
    )


@router.get("/plans/{plan_id}/matrix/cell", response_model=schemas.TrainingPlanMatrixPersonPage)
def get_plan_matrix_cell(
    plan_id: str,
    course_key: Annotated[str, Query(min_length=1, max_length=255)],
    month: Annotated[int, Query(ge=1, le=12)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PLAN_VIEW)),
):
    amo_id = tenant_id_for(current_user)
    service._get_scoped(db, models.TrainingPlan, plan_id, amo_id, "Training plan")
    derived_key = _plan_course_key()
    grouped = db.query(
        models.TrainingPlanParticipant.user_id.label("user_id"),
        func.min(models.TrainingPlanParticipant.person_name_snapshot).label("person_name"),
        func.min(models.TrainingPlanParticipant.staff_code_snapshot).label("staff_code"),
        func.min(models.TrainingPlanParticipant.planned_due_date).label("planned_due_date"),
        func.min(models.TrainingPlanParticipant.expiry_date).label("expiry_date"),
        func.min(models.TrainingPlanParticipant.obligation_status).label("obligation_status"),
    ).join(
        models.TrainingPlanItem,
        models.TrainingPlanParticipant.plan_item_id == models.TrainingPlanItem.id,
    ).filter(
        models.TrainingPlanParticipant.amo_id == amo_id,
        models.TrainingPlanItem.amo_id == amo_id,
        models.TrainingPlanItem.plan_id == plan_id,
        models.TrainingPlanItem.planned_month == month,
        derived_key == course_key,
    ).group_by(models.TrainingPlanParticipant.user_id)
    total = grouped.count()
    rows = grouped.order_by(func.min(models.TrainingPlanParticipant.person_name_snapshot).asc()).offset(offset).limit(limit).all()
    items = [schemas.TrainingPlanMatrixPerson(
        user_id=str(row.user_id),
        person_name=row.person_name,
        staff_code=row.staff_code,
        planned_due_date=row.planned_due_date,
        expiry_date=row.expiry_date,
        obligation_status=row.obligation_status,
    ) for row in rows]
    return schemas.TrainingPlanMatrixPersonPage(
        course_key=course_key,
        month=month,
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.post("/plans/{plan_id}/revise", response_model=schemas.TrainingPlanRead)
def revise_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PLAN_MANAGE)),
):
    row = service.revise_plan(db, actor=current_user, plan_id=plan_id)
    db.commit()
    return _plans(db, tenant_id_for(current_user)).filter(models.TrainingPlan.id == row.id).one()


@router.post("/plans/{plan_id}/refresh", response_model=schemas.TrainingPlanRead)
def refresh_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.PLAN_MANAGE)),
):
    row = service.refresh_plan_from_obligations(db, actor=current_user, plan_id=plan_id)
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
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.BUDGET_VIEW)),
):
    rows = db.query(models.TrainingBudget).options(selectinload(models.TrainingBudget.lines)).filter(models.TrainingBudget.amo_id == tenant_id_for(current_user)).order_by(models.TrainingBudget.created_at.desc()).offset(offset).limit(limit).all()
    return [_budget_read(row) for row in rows]


@router.put("/budgets/{budget_id}/lines/{line_id}", response_model=schemas.TrainingBudgetRead)
def update_budget_line(
    budget_id: str,
    line_id: str,
    payload: schemas.TrainingBudgetLineUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.BUDGET_MANAGE)),
):
    service.update_budget_line(db, actor=current_user, budget_id=budget_id, line_id=line_id, payload=payload)
    db.commit()
    budget = db.query(models.TrainingBudget).options(selectinload(models.TrainingBudget.lines)).filter(
        models.TrainingBudget.id == budget_id,
        models.TrainingBudget.amo_id == tenant_id_for(current_user),
    ).one()
    return _budget_read(budget)


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
    row, code, sign_in_path, notifications_sent = service.open_attendance_window(db, actor=current_user, payload=payload)
    db.commit()
    data = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    data["attendance_code"] = code
    data["sign_in_path"] = sign_in_path
    data["notifications_sent"] = 0
    data["notifications_queued"] = notifications_sent
    data["notification_delivery_status"] = "QUEUED" if notifications_sent else "NONE"
    return schemas.AttendanceWindowRead.model_validate(data)


@router.get("/attendance/events/{event_id}/window", response_model=schemas.AttendanceWindowRead | None)
def get_current_attendance_window(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ATTENDANCE_VIEW)),
):
    row = service.current_attendance_window(db, actor=current_user, event_id=event_id)
    return row


@router.post("/attendance/windows/{window_id}/close", response_model=schemas.AttendanceWindowRead)
def close_attendance_window(
    window_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.SESSION_CLOSE)),
):
    row = service.close_attendance_window(db, actor=current_user, window_id=window_id)
    db.commit()
    db.refresh(row)
    return row


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


@router.get("/attendance/events/{event_id}/roster", response_model=schemas.AttendanceRosterPage)
def attendance_roster(
    event_id: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ATTENDANCE_VIEW)),
):
    amo_id = tenant_id_for(current_user)
    service._get_scoped(db, legacy_models.TrainingEvent, event_id, amo_id, "Training session")
    participant_query = db.query(legacy_models.TrainingEventParticipant).filter(
        legacy_models.TrainingEventParticipant.amo_id == amo_id,
        legacy_models.TrainingEventParticipant.event_id == event_id,
    )
    total = participant_query.count()
    signed_count = db.query(func.count(models.TrainingAttendanceEntry.id)).filter(
        models.TrainingAttendanceEntry.amo_id == amo_id,
        models.TrainingAttendanceEntry.event_id == event_id,
    ).scalar() or 0
    rows = db.query(
        legacy_models.TrainingEventParticipant,
        account_models.User,
        models.TrainingAttendanceEntry,
    ).join(
        account_models.User,
        account_models.User.id == legacy_models.TrainingEventParticipant.user_id,
    ).outerjoin(
        models.TrainingAttendanceEntry,
        and_(
            models.TrainingAttendanceEntry.participant_id == legacy_models.TrainingEventParticipant.id,
            models.TrainingAttendanceEntry.amo_id == amo_id,
        ),
    ).filter(
        legacy_models.TrainingEventParticipant.amo_id == amo_id,
        legacy_models.TrainingEventParticipant.event_id == event_id,
    ).order_by(account_models.User.full_name.asc()).offset(offset).limit(limit).all()
    items = [
        schemas.AttendanceRosterItemRead(
            participant_id=str(participant.id), user_id=str(user.id), full_name=user.full_name,
            staff_code=user.staff_code, participant_status=str(getattr(participant.status, "value", participant.status)),
            attendance_entry_id=str(entry.id) if entry else None,
            attendance_status=entry.status if entry else None, method=entry.method if entry else None,
            signed_at=entry.signed_at if entry else None,
        )
        for participant, user, entry in rows
    ]
    return schemas.AttendanceRosterPage(items=items, total=total, signed_count=int(signed_count), limit=limit, offset=offset)


@router.get("/attendance/events/{event_id}", response_model=list[schemas.AttendanceEntryRead])
def attendance_register(
    event_id: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ATTENDANCE_VIEW)),
):
    return db.query(models.TrainingAttendanceEntry).filter(models.TrainingAttendanceEntry.amo_id == tenant_id_for(current_user), models.TrainingAttendanceEntry.event_id == event_id).order_by(models.TrainingAttendanceEntry.signed_at).offset(offset).limit(limit).all()


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
    from .router import _ensure_completion_artifacts_for_participant, _extract_training_event_metadata

    event_notes = db.query(legacy_models.TrainingEvent.notes).filter(
        legacy_models.TrainingEvent.id == event_id,
        legacy_models.TrainingEvent.amo_id == tenant_id_for(current_user),
    ).scalar()
    event_metadata, _plain_notes = _extract_training_event_metadata(event_notes)

    present_participants = db.query(legacy_models.TrainingEventParticipant).join(
        models.TrainingAttendanceEntry,
        models.TrainingAttendanceEntry.participant_id == legacy_models.TrainingEventParticipant.id,
    ).filter(
        models.TrainingAttendanceEntry.amo_id == tenant_id_for(current_user),
        models.TrainingAttendanceEntry.event_id == event_id,
        models.TrainingAttendanceEntry.status == "PRESENT",
    ).all()
    for participant in present_participants:
        _ensure_completion_artifacts_for_participant(
            db,
            participant=participant,
            actor_user_id=str(current_user.id),
            auto_issue_certificate=bool(event_metadata.get("auto_issue_certificates", True)),
        )
    db.commit()
    db.refresh(row)
    return row


@router.get("/assessment-templates", response_model=list[schemas.AssessmentTemplateRead])
def list_assessment_templates(
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_VIEW)),
):
    query = db.query(models.TrainingAssessmentTemplate).filter(models.TrainingAssessmentTemplate.amo_id == tenant_id_for(current_user))
    if not include_inactive:
        query = query.filter(models.TrainingAssessmentTemplate.active.is_(True))
    return query.order_by(models.TrainingAssessmentTemplate.code, models.TrainingAssessmentTemplate.revision_no.desc()).offset(offset).limit(limit).all()


@router.post("/certificates/records/{record_id}/revoke", response_model=schemas.CertificateIssueRead)
def revoke_certificate(
    record_id: str,
    payload: schemas.CertificateLifecycleAction,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.CERTIFICATE_REVOKE)),
):
    row = service.revoke_certificate(db, actor=current_user, record_id=record_id, reason=payload.reason)
    db.commit()
    db.refresh(row)
    return row


@router.post("/certificates/records/{record_id}/reissue", response_model=schemas.CertificateIssueRead)
def reissue_certificate(
    record_id: str,
    payload: schemas.CertificateLifecycleAction,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.CERTIFICATE_REISSUE)),
):
    row = service.reissue_certificate(db, actor=current_user, record_id=record_id, reason=payload.reason)
    db.commit()
    db.refresh(row)
    return row


@router.get("/certificates/eligibility", response_model=schemas.CertificateEligibilityPage)
def list_certificate_eligibility(
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.CERTIFICATE_ISSUE)),
):
    amo_id = tenant_id_for(current_user)
    issued_record_ids = db.query(legacy_models.TrainingCertificateIssue.record_id).filter(legacy_models.TrainingCertificateIssue.amo_id == amo_id)
    query = db.query(legacy_models.TrainingRecord).options(selectinload(legacy_models.TrainingRecord.course)).join(
        account_models.User, account_models.User.id == legacy_models.TrainingRecord.user_id,
    ).join(
        legacy_models.TrainingCourse, legacy_models.TrainingCourse.id == legacy_models.TrainingRecord.course_id,
    ).filter(
        legacy_models.TrainingRecord.amo_id == amo_id,
        or_(legacy_models.TrainingRecord.record_status.is_(None), legacy_models.TrainingRecord.record_status == "ACTIVE"),
        legacy_models.TrainingRecord.certificate_reference.is_(None),
        ~legacy_models.TrainingRecord.id.in_(issued_record_ids),
    )
    if search:
        token = f"%{search.strip()}%"
        query = query.filter(or_(
            account_models.User.full_name.ilike(token), account_models.User.staff_code.ilike(token),
            legacy_models.TrainingCourse.course_id.ilike(token), legacy_models.TrainingCourse.course_name.ilike(token),
        ))
    total = int(query.count())
    records = query.order_by(legacy_models.TrainingRecord.completion_date.desc(), legacy_models.TrainingRecord.id).offset(offset).limit(limit).all()
    users = db.query(account_models.User).filter(account_models.User.amo_id == amo_id, account_models.User.id.in_([row.user_id for row in records] or [""])).all()
    user_by_id = {str(user.id): user for user in users}
    items = []
    for record in records:
        blockers = service.completion_gate(db, record=record)
        user = user_by_id.get(str(record.user_id))
        items.append(schemas.CertificateEligibilityItem(
            record_id=str(record.id), user_id=str(record.user_id), person_name=user.full_name if user else "Unavailable person",
            staff_code=user.staff_code if user else None, course_id=str(record.course_id),
            course_code=record.course.course_id if record.course else "Unknown", course_name=record.course.course_name if record.course else "Unavailable course",
            completion_date=record.completion_date, valid_until=record.valid_until, eligible=not blockers, blockers=blockers,
        ))
    return _page(items=items, total=total, limit=limit, offset=offset, filtered_totals={"eligible_on_page": sum(item.eligible for item in items), "blocked_on_page": sum(not item.eligible for item in items)})


@router.post("/certificates/batch-issue", response_model=schemas.CertificateBatchIssueRead)
def batch_issue_certificates(
    payload: schemas.CertificateBatchIssueCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.CERTIFICATE_ISSUE)),
):
    amo_id = tenant_id_for(current_user)
    record_ids = list(dict.fromkeys(payload.record_ids))
    records = db.query(legacy_models.TrainingRecord).filter(
        legacy_models.TrainingRecord.amo_id == amo_id,
        legacy_models.TrainingRecord.id.in_(record_ids),
    ).all()
    record_by_id = {str(row.id): row for row in records}
    existing = db.query(legacy_models.TrainingCertificateIssue).filter(
        legacy_models.TrainingCertificateIssue.amo_id == amo_id,
        legacy_models.TrainingCertificateIssue.record_id.in_(record_ids),
    ).all()
    existing_by_record = {str(row.record_id): row for row in existing}
    from .router import _issue_certificate_for_record
    results: list[schemas.CertificateBatchIssueItem] = []
    issued = 0
    for record_id in record_ids:
        record = record_by_id.get(record_id)
        if record is None:
            results.append(schemas.CertificateBatchIssueItem(record_id=record_id, status="NOT_FOUND"))
            continue
        current = existing_by_record.get(record_id)
        if current is not None or record.certificate_reference:
            results.append(schemas.CertificateBatchIssueItem(record_id=record_id, status="ALREADY_ISSUED", certificate_id=str(current.id) if current else None, certificate_number=current.certificate_number if current else record.certificate_reference))
            continue
        blockers = service.completion_gate(db, record=record)
        if blockers:
            results.append(schemas.CertificateBatchIssueItem(record_id=record_id, status="BLOCKED", blockers=blockers))
            continue
        issue = _issue_certificate_for_record(db, record=record, amo_id=amo_id, actor_user_id=str(current_user.id))
        service._audit(db, amo_id=amo_id, actor_user_id=str(current_user.id), entity_type="training.certificate", entity_id=str(issue.id), action="BATCH_ISSUED", after={"record_id": record_id, "reason": payload.reason}, critical=True)
        results.append(schemas.CertificateBatchIssueItem(record_id=record_id, status="ISSUED", certificate_id=str(issue.id), certificate_number=issue.certificate_number))
        issued += 1
    db.commit()
    return schemas.CertificateBatchIssueRead(requested=len(record_ids), issued=issued, blocked=len(record_ids) - issued, items=results)


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


@router.post("/assessment-templates/{template_id}/revise", response_model=schemas.AssessmentTemplateRead, status_code=201)
def revise_assessment_template(
    template_id: str,
    payload: schemas.AssessmentTemplateCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_CREATE)),
):
    source = db.query(models.TrainingAssessmentTemplate).filter(
        models.TrainingAssessmentTemplate.id == template_id,
        models.TrainingAssessmentTemplate.amo_id == tenant_id_for(current_user),
    ).first()
    if not source:
        raise HTTPException(status_code=404, detail="Assessment template was not found in this tenant.")
    if source.code.upper() != payload.code.upper():
        raise HTTPException(status_code=422, detail="A template revision must retain its controlled code.")
    source.active = False
    row = service.create_assessment_template(db, actor=current_user, payload=payload)
    db.commit(); db.refresh(row)
    return row


@router.post("/assessment-templates/{template_id}/retire", response_model=schemas.AssessmentTemplateRead)
def retire_assessment_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_CREATE)),
):
    row = db.query(models.TrainingAssessmentTemplate).filter(
        models.TrainingAssessmentTemplate.id == template_id,
        models.TrainingAssessmentTemplate.amo_id == tenant_id_for(current_user),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Assessment template was not found in this tenant.")
    row.active = False
    service._audit(db, amo_id=tenant_id_for(current_user), actor_user_id=str(current_user.id), entity_type="training.assessment_template", entity_id=str(row.id), action="RETIRED", critical=True)
    db.commit(); db.refresh(row)
    return row


@router.get("/assessments", response_model=list[schemas.AssessmentRead])
def list_assessments(
    candidate_user_id: str | None = None,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_VIEW)),
):
    query = db.query(models.TrainingAssessmentInstance).filter(models.TrainingAssessmentInstance.amo_id == tenant_id_for(current_user))
    if candidate_user_id:
        query = query.filter(models.TrainingAssessmentInstance.candidate_user_id == candidate_user_id)
    if status:
        query = query.filter(models.TrainingAssessmentInstance.status == status.upper())
    return query.order_by(models.TrainingAssessmentInstance.created_at.desc()).offset(offset).limit(limit).all()


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
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.AUTHORIZATION_VIEW)),
):
    query = db.query(models.TrainingAuthorizationCase).filter(models.TrainingAuthorizationCase.amo_id == tenant_id_for(current_user))
    if status:
        query = query.filter(models.TrainingAuthorizationCase.status == status.upper())
    return query.order_by(models.TrainingAuthorizationCase.updated_at.desc()).offset(offset).limit(limit).all()


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


@router.post("/authorization-cases/{case_id}/recommend", response_model=schemas.AuthorizationCaseRead)
def recommend_authorization(
    case_id: str,
    payload: schemas.AuthorizationRecommendationCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.AUTHORIZATION_RECOMMEND)),
):
    row = service.recommend_authorization(db, actor=current_user, case_id=case_id, payload=payload)
    db.commit(); db.refresh(row)
    return row


@router.post("/authorization-cases/{case_id}/restrict", response_model=schemas.AuthorizationCaseRead)
def restrict_authorization(
    case_id: str,
    payload: schemas.AuthorizationLifecycleAction,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.AUTHORIZATION_RESTRICT)),
):
    if payload.action not in {"RESTRICT", "SUSPEND"}:
        raise HTTPException(status_code=422, detail="This endpoint accepts RESTRICT or SUSPEND.")
    row = service.authorization_lifecycle(db, actor=current_user, case_id=case_id, payload=payload)
    db.commit(); db.refresh(row)
    return row


@router.post("/authorization-cases/{case_id}/withdraw", response_model=schemas.AuthorizationCaseRead)
def withdraw_authorization(
    case_id: str,
    payload: schemas.AuthorizationLifecycleAction,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.AUTHORIZATION_WITHDRAW)),
):
    if payload.action != "WITHDRAW":
        raise HTTPException(status_code=422, detail="This endpoint accepts WITHDRAW only.")
    row = service.authorization_lifecycle(db, actor=current_user, case_id=case_id, payload=payload)
    db.commit(); db.refresh(row)
    return row


@router.get("/effectiveness", response_model=list[schemas.EffectivenessRead])
def list_effectiveness(
    course_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_VIEW)),
):
    query = db.query(models.TrainingEffectivenessEvaluation).filter(models.TrainingEffectivenessEvaluation.amo_id == tenant_id_for(current_user))
    if course_id:
        query = query.filter(models.TrainingEffectivenessEvaluation.course_id == course_id)
    return query.order_by(models.TrainingEffectivenessEvaluation.created_at.desc()).offset(offset).limit(limit).all()


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
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_VIEW)),
):
    query = db.query(models.TrainingRemedialAction).filter(models.TrainingRemedialAction.amo_id == tenant_id_for(current_user))
    if status:
        query = query.filter(models.TrainingRemedialAction.status == status.upper())
    rows = query.order_by(models.TrainingRemedialAction.due_date.asc()).offset(offset).limit(limit).all()
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


@router.get("/reports/budgets/{budget_id}.pdf")
def export_budget_pdf(
    budget_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_training_capability(Cap.REPORT_EXPORT)),
):
    amo_id = tenant_id_for(current_user)
    budget = db.query(models.TrainingBudget).options(selectinload(models.TrainingBudget.lines)).filter(
        models.TrainingBudget.id == budget_id,
        models.TrainingBudget.amo_id == amo_id,
    ).first()
    if not budget:
        return Response(status_code=404)
    amo = db.query(account_models.AMO).filter(account_models.AMO.id == amo_id).one()
    return Response(
        content=reports.budget_pdf(budget=budget, amo=amo),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="training-budget-rev-{budget.revision_no}.pdf"'},
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
