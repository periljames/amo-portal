# backend/amodb/apps/rostering/router.py
from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import models, schemas, services

router = APIRouter(prefix="/rostering", tags=["rostering"])


def _amo(user: account_models.User) -> str:
    return services.effective_amo_id(user)


def _require_view(user: account_models.User) -> None:
    if not services.can_view_roster(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Roster access denied")


def _require_manager(user: account_models.User) -> None:
    if not services.can_manage_roster(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Roster management access denied")


def _require_approver(user: account_models.User) -> None:
    if not services.can_approve_roster(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Roster approval access denied")


@router.get("/contracts", response_model=schemas.RosterContractResponse)
def get_roster_contracts() -> schemas.RosterContractResponse:
    return services.roster_contracts()


@router.get("/shift-templates", response_model=List[schemas.ShiftTemplateRead])
def list_shift_templates(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_view(current_user)
    return services.list_shift_templates(db, amo_id=_amo(current_user), include_inactive=include_inactive)


@router.post("/shift-templates", response_model=schemas.ShiftTemplateRead, status_code=status.HTTP_201_CREATED)
def create_shift_template(
    payload: schemas.ShiftTemplateCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    try:
        row = services.create_shift_template(db, amo_id=_amo(current_user), actor_user_id=current_user.id, payload=payload)
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Shift template code already exists for this AMO") from exc


@router.put("/shift-templates/{template_id}", response_model=schemas.ShiftTemplateRead)
def update_shift_template(
    template_id: str,
    payload: schemas.ShiftTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    row = db.query(models.ShiftTemplate).filter(models.ShiftTemplate.id == template_id, models.ShiftTemplate.amo_id == _amo(current_user)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Shift template not found")
    try:
        row = services.update_shift_template(db, row=row, actor_user_id=current_user.id, payload=payload)
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Shift template code already exists for this AMO") from exc


@router.get("/periods", response_model=List[schemas.RosterPeriodRead])
def list_periods(
    status_filter: Optional[models.RosterPeriodStatus] = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_view(current_user)
    periods = services.list_periods(db, amo_id=_amo(current_user), status=status_filter)
    return [
        schemas.RosterPeriodRead(
            id=p.id,
            amo_id=p.amo_id,
            period_code=p.period_code,
            name=p.name,
            starts_on=p.starts_on,
            ends_on=p.ends_on,
            status=p.status,
            notes=p.notes,
            created_by_user_id=p.created_by_user_id,
            created_at=p.created_at,
            updated_at=p.updated_at,
            versions=[services.summarize_version(v) for v in p.versions],
        )
        for p in periods
    ]


@router.post("/periods", response_model=schemas.RosterPeriodRead, status_code=status.HTTP_201_CREATED)
def create_period(
    payload: schemas.RosterPeriodCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    try:
        row = services.create_period(db, amo_id=_amo(current_user), actor_user_id=current_user.id, payload=payload)
        db.commit()
        db.refresh(row)
        return schemas.RosterPeriodRead(
            id=row.id,
            amo_id=row.amo_id,
            period_code=row.period_code,
            name=row.name,
            starts_on=row.starts_on,
            ends_on=row.ends_on,
            status=row.status,
            notes=row.notes,
            created_by_user_id=row.created_by_user_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            versions=[services.summarize_version(v) for v in row.versions],
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Roster period already exists for this AMO") from exc


@router.put("/periods/{period_id}", response_model=schemas.RosterPeriodRead)
def update_period(
    period_id: str,
    payload: schemas.RosterPeriodUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    row = services.get_period(db, amo_id=_amo(current_user), period_id=period_id)
    if not row:
        raise HTTPException(status_code=404, detail="Roster period not found")
    row = services.update_period(db, period=row, payload=payload)
    db.commit()
    db.refresh(row)
    return schemas.RosterPeriodRead(
        id=row.id,
        amo_id=row.amo_id,
        period_code=row.period_code,
        name=row.name,
        starts_on=row.starts_on,
        ends_on=row.ends_on,
        status=row.status,
        notes=row.notes,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        versions=[services.summarize_version(v) for v in row.versions],
    )


@router.get("/periods/{period_id}/versions", response_model=List[schemas.RosterVersionRead])
def list_versions(
    period_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_view(current_user)
    return [services.summarize_version(row) for row in services.list_versions(db, amo_id=_amo(current_user), period_id=period_id)]


@router.post("/periods/{period_id}/versions", response_model=schemas.RosterVersionRead, status_code=status.HTTP_201_CREATED)
def create_version(
    period_id: str,
    payload: schemas.RosterVersionCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    period = services.get_period(db, amo_id=_amo(current_user), period_id=period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Roster period not found")
    row = services.create_version(db, amo_id=_amo(current_user), period=period, actor_user_id=current_user.id, payload=payload)
    db.commit()
    db.refresh(row)
    return services.summarize_version(row)


@router.get("/versions/{version_id}/assignments", response_model=List[schemas.RosterAssignmentRead])
def list_assignments(
    version_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_view(current_user)
    return [services.serialize_assignment(row) for row in services.list_assignments_for_version(db, amo_id=_amo(current_user), version_id=version_id)]


@router.post("/versions/{version_id}/assignments", response_model=schemas.RosterAssignmentRead, status_code=status.HTTP_201_CREATED)
def create_assignment(
    version_id: str,
    payload: schemas.RosterAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    version = services.get_version(db, amo_id=_amo(current_user), version_id=version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Roster version not found")
    try:
        row = services.create_assignment(db, amo_id=_amo(current_user), version=version, actor_user_id=current_user.id, payload=payload)
        db.commit()
        db.refresh(row)
        return services.serialize_assignment(row)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/assignments/{assignment_id}", response_model=schemas.RosterAssignmentRead)
def update_assignment(
    assignment_id: str,
    payload: schemas.RosterAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    row = db.query(models.RosterAssignment).filter(models.RosterAssignment.id == assignment_id, models.RosterAssignment.amo_id == _amo(current_user)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Roster assignment not found")
    try:
        row = services.update_assignment(db, amo_id=_amo(current_user), assignment=row, actor_user_id=current_user.id, payload=payload)
        db.commit()
        db.refresh(row)
        return services.serialize_assignment(row)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/versions/{version_id}/validate", response_model=schemas.RosterValidationResult)
def validate_version(
    version_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_view(current_user)
    version = services.get_version(db, amo_id=_amo(current_user), version_id=version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Roster version not found")
    result = services.validate_version(db, amo_id=_amo(current_user), version=version)
    db.commit()
    return result


@router.post("/versions/{version_id}/submit", response_model=schemas.RosterVersionRead)
def submit_version(
    version_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    version = services.get_version(db, amo_id=_amo(current_user), version_id=version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Roster version not found")
    try:
        row = services.submit_version(db, version=version, actor_user_id=current_user.id)
        db.commit()
        db.refresh(row)
        return services.summarize_version(row)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/versions/{version_id}/approve", response_model=schemas.RosterVersionRead)
def approve_version(
    version_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_approver(current_user)
    version = services.get_version(db, amo_id=_amo(current_user), version_id=version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Roster version not found")
    try:
        row = services.approve_version(db, version=version, actor_user_id=current_user.id)
        db.commit()
        db.refresh(row)
        return services.summarize_version(row)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/versions/{version_id}/publish", response_model=schemas.RosterVersionRead)
def publish_version(
    version_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_approver(current_user)
    version = services.get_version(db, amo_id=_amo(current_user), version_id=version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Roster version not found")
    try:
        row = services.publish_version(db, version=version, actor_user_id=current_user.id)
        db.commit()
        db.refresh(row)
        return services.summarize_version(row)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/versions/{version_id}/acknowledge", response_model=schemas.RosterAcknowledgementRead)
def acknowledge_version(
    version_id: str,
    payload: schemas.RosterAcknowledgeRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_view(current_user)
    version = services.get_version(db, amo_id=_amo(current_user), version_id=version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Roster version not found")
    try:
        row = services.acknowledge_version(db, amo_id=_amo(current_user), version=version, user_id=current_user.id, note=payload.acknowledgement_note)
        db.commit()
        db.refresh(row)
        return row
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/my-roster", response_model=schemas.MyRosterResponse)
def my_roster(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_view(current_user)
    assignments = services.published_assignments_for_user(db, amo_id=_amo(current_user), user_id=current_user.id, from_date=from_date, to_date=to_date)
    return schemas.MyRosterResponse(
        user_id=current_user.id,
        from_date=from_date,
        to_date=to_date,
        assignments=[services.serialize_assignment(row) for row in assignments],
        training_due_next_month=services.training_due_next_month(db, user=current_user, base_date=from_date),
    )


@router.get("/assignments/{assignment_id}/task-links", response_model=List[schemas.RosterTaskAssignmentLinkRead])
def list_assignment_task_links(
    assignment_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_view(current_user)
    return services.list_task_links_for_assignment(db, amo_id=_amo(current_user), assignment_id=assignment_id)


@router.post("/assignments/{assignment_id}/task-links", response_model=schemas.RosterTaskAssignmentLinkRead, status_code=status.HTTP_201_CREATED)
def link_assignment_to_existing_task_assignment(
    assignment_id: str,
    payload: schemas.RosterTaskLinkCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    try:
        row = services.link_existing_task_assignment(
            db,
            amo_id=_amo(current_user),
            actor_user_id=current_user.id,
            roster_assignment_id=assignment_id,
            payload=payload,
        )
        db.commit()
        return services.list_task_links_for_assignment(db, amo_id=_amo(current_user), assignment_id=assignment_id)[-1]
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Roster assignment is already linked to that task assignment") from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/assignments/{assignment_id}/task-allocations", response_model=schemas.RosterTaskAssignmentLinkRead, status_code=status.HTTP_201_CREATED)
def allocate_rostered_user_to_task(
    assignment_id: str,
    payload: schemas.RosterTaskAllocationCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    try:
        row = services.create_task_allocation_from_roster(
            db,
            amo_id=_amo(current_user),
            actor_user_id=current_user.id,
            roster_assignment_id=assignment_id,
            payload=payload,
        )
        db.commit()
        return services.list_task_links_for_assignment(db, amo_id=_amo(current_user), assignment_id=assignment_id)[-1]
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Task allocation already exists or conflicts with an existing task link") from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/planning-board", response_model=schemas.RosterPlanningBoardResponse)
def planning_board(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    base_station_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_view(current_user)
    return services.planning_board(db, amo_id=_amo(current_user), from_date=from_date, to_date=to_date, base_station_id=base_station_id)
