from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import AccountRole, User
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user, require_roles

from . import rollout_services
from .rollout_schemas import (
    RolloutAircraftTransition,
    RolloutChecklistRead,
    RolloutChecklistUpdate,
    RolloutDashboardRead,
    RolloutGroupCreate,
    RolloutGroupRead,
    RolloutWaveCreate,
    RolloutWaveRead,
    RolloutWaveTransition,
    RolloutWaveAircraftRead,
    SpreadsheetCreate,
    SpreadsheetRead,
    SpreadsheetTransition,
)

router = APIRouter(
    prefix="/rollout",
    tags=["rollout_retirement"],
    dependencies=[Depends(require_module("work"))],
)

ROLLOUT_EDITOR_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
    AccountRole.PRODUCTION_ENGINEER,
)
ROLLOUT_APPROVER_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.QUALITY_MANAGER,
    AccountRole.PLANNING_ENGINEER,
)


@router.get("/dashboard", response_model=RolloutDashboardRead)
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return rollout_services.dashboard(db, amo_id=current_user.effective_amo_id)


@router.get("/groups", response_model=list[RolloutGroupRead])
def list_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return rollout_services.list_groups(db, amo_id=current_user.effective_amo_id)


@router.post("/groups", response_model=RolloutGroupRead, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: RolloutGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ROLLOUT_EDITOR_ROLES)),
):
    row = rollout_services.create_group(
        db,
        amo_id=current_user.effective_amo_id,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/groups/{group_id}/waves", response_model=RolloutWaveRead, status_code=status.HTTP_201_CREATED)
def create_wave(
    group_id: str,
    payload: RolloutWaveCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ROLLOUT_EDITOR_ROLES)),
):
    group = rollout_services._get_group(db, amo_id=current_user.effective_amo_id, group_id=group_id)
    row = rollout_services.create_wave(db, group=group, payload=payload, actor=current_user)
    db.commit()
    db.refresh(row)
    return row


@router.post("/waves/{wave_id}/assess", response_model=RolloutWaveRead)
def assess_wave(
    wave_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ROLLOUT_EDITOR_ROLES)),
):
    wave = rollout_services._get_wave(db, amo_id=current_user.effective_amo_id, wave_id=wave_id)
    rollout_services.assess_wave(db, wave=wave)
    db.commit()
    db.refresh(wave)
    return wave


@router.post("/waves/{wave_id}/transition", response_model=RolloutWaveRead)
def transition_wave(
    wave_id: str,
    payload: RolloutWaveTransition,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ROLLOUT_APPROVER_ROLES)),
):
    wave = rollout_services._get_wave(db, amo_id=current_user.effective_amo_id, wave_id=wave_id)
    rollout_services.transition_wave(db, wave=wave, payload=payload, actor=current_user)
    db.commit()
    db.refresh(wave)
    return wave


@router.put("/checklist/{checklist_id}", response_model=RolloutChecklistRead)
def update_checklist(
    checklist_id: str,
    payload: RolloutChecklistUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ROLLOUT_APPROVER_ROLES)),
):
    row = rollout_services.update_checklist(
        db,
        amo_id=current_user.effective_amo_id,
        checklist_id=checklist_id,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/aircraft/{row_id}/transition", response_model=RolloutWaveAircraftRead)
def transition_aircraft(
    row_id: str,
    payload: RolloutAircraftTransition,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ROLLOUT_APPROVER_ROLES)),
):
    row = rollout_services._get_wave_aircraft(db, amo_id=current_user.effective_amo_id, row_id=row_id)
    rollout_services.transition_aircraft(db, row=row, payload=payload, actor=current_user)
    db.commit()
    db.refresh(row)
    return row


@router.get("/spreadsheets", response_model=list[SpreadsheetRead])
def list_spreadsheets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return rollout_services.list_spreadsheets(db, amo_id=current_user.effective_amo_id)


@router.post("/spreadsheets", response_model=SpreadsheetRead, status_code=status.HTTP_201_CREATED)
def create_spreadsheet(
    payload: SpreadsheetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ROLLOUT_EDITOR_ROLES)),
):
    row = rollout_services.create_spreadsheet(
        db,
        amo_id=current_user.effective_amo_id,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/spreadsheets/{spreadsheet_id}/transition", response_model=SpreadsheetRead)
def transition_spreadsheet(
    spreadsheet_id: str,
    payload: SpreadsheetTransition,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ROLLOUT_APPROVER_ROLES)),
):
    row = rollout_services._get_spreadsheet(
        db,
        amo_id=current_user.effective_amo_id,
        spreadsheet_id=spreadsheet_id,
    )
    rollout_services.transition_spreadsheet(db, row=row, payload=payload, actor=current_user)
    db.commit()
    db.refresh(row)
    return row
