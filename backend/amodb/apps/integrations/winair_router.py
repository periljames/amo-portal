from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import AccountRole, User
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user, require_roles

from . import winair_services
from .winair_schemas import (
    WinAirConflictDecision,
    WinAirConflictRead,
    WinAirDashboardRead,
    WinAirExportRequest,
    WinAirInboundBatch,
    WinAirProfileCreate,
    WinAirProfileRead,
    WinAirProfileUpdate,
    WinAirReconcileRequest,
    WinAirRecordRead,
    WinAirRunRead,
)


router = APIRouter(
    prefix="/integrations/winair",
    tags=["winair_integration"],
    dependencies=[Depends(require_module("work"))],
)

PROFILE_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
)
SYNC_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
    AccountRole.PRODUCTION_ENGINEER,
)
CONFLICT_REVIEW_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.QUALITY_MANAGER,
    AccountRole.PLANNING_ENGINEER,
)


@router.get("/dashboard", response_model=WinAirDashboardRead)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return winair_services.dashboard(db, amo_id=current_user.effective_amo_id)


@router.get("/profiles", response_model=list[WinAirProfileRead])
def list_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return winair_services.list_profiles(db, amo_id=current_user.effective_amo_id)


@router.post(
    "/profiles",
    response_model=WinAirProfileRead,
    status_code=status.HTTP_201_CREATED,
)
def create_profile(
    payload: WinAirProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*PROFILE_ROLES)),
):
    row = winair_services.create_profile(
        db,
        amo_id=current_user.effective_amo_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return row


@router.patch("/profiles/{profile_id}", response_model=WinAirProfileRead)
def update_profile(
    profile_id: str,
    payload: WinAirProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*PROFILE_ROLES)),
):
    row = winair_services.update_profile(
        db,
        amo_id=current_user.effective_amo_id,
        profile_id=profile_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/profiles/{profile_id}/ingest", response_model=WinAirRunRead)
def ingest_batch(
    profile_id: str,
    payload: WinAirInboundBatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*SYNC_ROLES)),
):
    run = winair_services.ingest_batch(
        db,
        amo_id=current_user.effective_amo_id,
        profile_id=profile_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(run)
    return run


@router.post("/profiles/{profile_id}/export", response_model=WinAirRunRead)
def export_snapshot(
    profile_id: str,
    payload: WinAirExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*SYNC_ROLES)),
):
    run = winair_services.export_snapshot(
        db,
        amo_id=current_user.effective_amo_id,
        profile_id=profile_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(run)
    return run


@router.post("/profiles/{profile_id}/reconcile", response_model=WinAirRunRead)
def reconcile(
    profile_id: str,
    payload: WinAirReconcileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*SYNC_ROLES)),
):
    run = winair_services.reconcile(
        db,
        amo_id=current_user.effective_amo_id,
        profile_id=profile_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(run)
    return run


@router.get("/runs", response_model=list[WinAirRunRead])
def list_runs(
    profile_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return winair_services.list_runs(
        db,
        amo_id=current_user.effective_amo_id,
        profile_id=profile_id,
        limit=limit,
    )


@router.get("/runs/{run_id}/records", response_model=list[WinAirRecordRead])
def list_run_records(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return winair_services.list_records(
        db,
        amo_id=current_user.effective_amo_id,
        run_id=run_id,
    )


@router.get("/conflicts", response_model=list[WinAirConflictRead])
def list_conflicts(
    profile_id: str | None = Query(None),
    status_filter: str | None = Query("OPEN", max_length=24),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return winair_services.list_conflicts(
        db,
        amo_id=current_user.effective_amo_id,
        profile_id=profile_id,
        status_filter=status_filter,
    )


@router.post("/conflicts/{conflict_id}/decision", response_model=WinAirConflictRead)
def decide_conflict(
    conflict_id: str,
    payload: WinAirConflictDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CONFLICT_REVIEW_ROLES)),
):
    row = winair_services.decide_conflict(
        db,
        amo_id=current_user.effective_amo_id,
        conflict_id=conflict_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return row
