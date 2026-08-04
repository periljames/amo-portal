from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import AccountRole, User

from ...database import get_db
from ...entitlements import require_module
from ...security import get_current_active_user, require_roles
from . import revision_services
from .revision_schemas import (
    AmpBaselineApply,
    AmpBaselineRead,
    AmpCoverageRead,
    AmpRevisionApproval,
    AmpRevisionCreate,
    AmpRevisionRead,
    AmpRevisionUpdate,
)

router = APIRouter(
    prefix="/maintenance-program",
    tags=["maintenance_program_revisions"],
    dependencies=[Depends(require_module("maintenance_program"))],
)

REVISION_EDITOR_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
)
REVISION_APPROVER_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.QUALITY_MANAGER,
)


@router.get("/revisions", response_model=list[AmpRevisionRead])
def list_revisions(
    template_code: str | None = Query(None, max_length=50),
    status_filter: str | None = Query(None, max_length=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return revision_services.list_revisions(
        db,
        amo_id=current_user.effective_amo_id,
        template_code=template_code,
        status_filter=status_filter,
    )


@router.post(
    "/revisions",
    response_model=AmpRevisionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_revision(
    payload: AmpRevisionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REVISION_EDITOR_ROLES)),
):
    revision = revision_services.create_revision(
        db,
        amo_id=current_user.effective_amo_id,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(revision)
    return revision_services._revision_read(db, revision)


@router.patch("/revisions/{revision_id}", response_model=AmpRevisionRead)
def update_revision(
    revision_id: int,
    payload: AmpRevisionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REVISION_EDITOR_ROLES)),
):
    revision = revision_services._get_revision(
        db,
        amo_id=current_user.effective_amo_id,
        revision_id=revision_id,
    )
    revision_services.update_revision(
        db,
        revision=revision,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(revision)
    return revision_services._revision_read(db, revision)


@router.post("/revisions/{revision_id}/approve", response_model=AmpRevisionRead)
def approve_revision(
    revision_id: int,
    payload: AmpRevisionApproval,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REVISION_APPROVER_ROLES)),
):
    revision = revision_services._get_revision(
        db,
        amo_id=current_user.effective_amo_id,
        revision_id=revision_id,
    )
    revision_services.approve_revision(
        db,
        revision=revision,
        actor=current_user,
        approval_notes=payload.notes,
    )
    db.commit()
    db.refresh(revision)
    return revision_services._revision_read(db, revision)


@router.post("/revisions/{revision_id}/apply", response_model=AmpBaselineRead)
def apply_revision(
    revision_id: int,
    payload: AmpBaselineApply,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REVISION_EDITOR_ROLES)),
):
    revision = revision_services._get_revision(
        db,
        amo_id=current_user.effective_amo_id,
        revision_id=revision_id,
    )
    baseline = revision_services.apply_revision_to_aircraft(
        db,
        revision=revision,
        aircraft_serial_number=payload.aircraft_serial_number,
        notes=payload.notes,
        actor=current_user,
    )
    db.commit()
    return baseline


@router.get("/baselines", response_model=list[AmpBaselineRead])
def list_baselines(
    aircraft_serial_number: str | None = Query(None, max_length=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return revision_services.list_baselines(
        db,
        amo_id=current_user.effective_amo_id,
        aircraft_serial_number=aircraft_serial_number,
    )


@router.get("/coverage", response_model=AmpCoverageRead)
def get_amp_coverage(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return revision_services.coverage(
        db,
        amo_id=current_user.effective_amo_id,
    )
