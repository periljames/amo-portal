from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import AccountRole, User

from ...database import get_db
from ...entitlements import require_module
from ...security import get_current_active_user, require_roles
from . import control_services
from .control_models import AircraftUsageCorrection
from .control_schemas import (
    CanonicalUtilisationCreate,
    CanonicalUtilisationRead,
    ReconciliationScanResult,
    ReconciliationSummary,
    UsageCorrectionCreate,
    UsageCorrectionDecision,
    UsageCorrectionRead,
)

router = APIRouter(
    prefix="/records",
    tags=["technical_records_control"],
    dependencies=[Depends(require_module("work"))],
)

UTILISATION_ENTRY_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
    AccountRole.PRODUCTION_ENGINEER,
    AccountRole.CERTIFYING_ENGINEER,
    AccountRole.CERTIFYING_TECHNICIAN,
)
CORRECTION_REVIEW_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.QUALITY_MANAGER,
    AccountRole.PLANNING_ENGINEER,
)


@router.get(
    "/aircraft/{tail_id}/utilisation",
    response_model=list[CanonicalUtilisationRead],
)
def list_utilisation(
    tail_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return control_services.list_canonical_utilisation(
        db,
        amo_id=current_user.effective_amo_id,
        aircraft_serial_number=tail_id,
    )


@router.post(
    "/aircraft/{tail_id}/utilisation",
    response_model=CanonicalUtilisationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_utilisation(
    tail_id: str,
    payload: CanonicalUtilisationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*UTILISATION_ENTRY_ROLES)),
):
    row = control_services.create_canonical_utilisation(
        db,
        amo_id=current_user.effective_amo_id,
        actor_user_id=current_user.id,
        aircraft_serial_number=tail_id,
        payload=payload,
    )
    db.commit()
    db.refresh(row)
    return control_services.utilisation_read(row)


@router.get(
    "/utilisation/corrections",
    response_model=list[UsageCorrectionRead],
)
def list_usage_corrections(
    status_filter: str | None = Query(None, max_length=16),
    aircraft_serial_number: str | None = Query(None, max_length=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = db.query(AircraftUsageCorrection).filter(
        AircraftUsageCorrection.amo_id == current_user.effective_amo_id
    )
    if status_filter:
        query = query.filter(AircraftUsageCorrection.status == status_filter.upper())
    if aircraft_serial_number:
        query = query.filter(
            AircraftUsageCorrection.aircraft_serial_number == aircraft_serial_number
        )
    return query.order_by(AircraftUsageCorrection.requested_at.desc()).all()


@router.post(
    "/utilisation/{usage_id}/corrections",
    response_model=UsageCorrectionRead,
    status_code=status.HTTP_201_CREATED,
)
def request_usage_correction(
    usage_id: int,
    payload: UsageCorrectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*UTILISATION_ENTRY_ROLES)),
):
    row = control_services.request_usage_correction(
        db,
        amo_id=current_user.effective_amo_id,
        usage_id=usage_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    db.commit()
    db.refresh(row)
    return row


@router.post(
    "/utilisation/corrections/{correction_id}/decision",
    response_model=UsageCorrectionRead,
)
def decide_usage_correction(
    correction_id: int,
    payload: UsageCorrectionDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CORRECTION_REVIEW_ROLES)),
):
    row = control_services.decide_usage_correction(
        db,
        amo_id=current_user.effective_amo_id,
        correction_id=correction_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    db.commit()
    db.refresh(row)
    return row


@router.get("/reconciliation/summary", response_model=ReconciliationSummary)
def get_reconciliation_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return control_services.reconciliation_summary(
        db,
        amo_id=current_user.effective_amo_id,
    )


@router.post("/reconciliation/scan", response_model=ReconciliationScanResult)
def run_reconciliation_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CORRECTION_REVIEW_ROLES)),
):
    result = control_services.scan_reconciliation(
        db,
        amo_id=current_user.effective_amo_id,
        actor_user_id=current_user.id,
    )
    db.commit()
    return result
