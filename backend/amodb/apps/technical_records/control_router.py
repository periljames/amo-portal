from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import AccountRole, User
from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.audit import services as audit_services
from amodb.apps.maintenance_program import projection

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


def _audit_correction_decision(
    db: Session,
    *,
    correction: AircraftUsageCorrection,
    actor_user_id: str | None,
    decision: str,
) -> None:
    audit_services.create_audit_event(
        db,
        amo_id=correction.amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type="AircraftUsageCorrection",
            entity_id=str(correction.id),
            action="decision",
            actor_user_id=actor_user_id,
            before_json={"status": "PENDING"},
            after_json={
                "decision": decision,
                "status": correction.status,
                "usage_id": correction.usage_id,
                "aircraft_serial_number": correction.aircraft_serial_number,
                "review_notes": correction.review_notes,
            },
        ),
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
    previous = control_services._usage_before(
        db,
        amo_id=current_user.effective_amo_id,
        aircraft_serial_number=tail_id,
        entry_date=payload.entry_date,
        techlog_no=payload.techlog_no,
    )
    effective_payload = payload
    if previous is None:
        effective_payload = payload.model_copy(
            update={
                "block_hours": payload.block_hours if payload.block_hours is not None else 0.0,
                "entry_cycles": payload.entry_cycles if payload.entry_cycles is not None else 0.0,
            }
        )
    else:
        expected_hours = payload.hours - float(previous.ttaf_after or 0)
        expected_cycles = payload.cycles - float(previous.tca_after or 0)
        if expected_hours < -control_services.HOURS_TOLERANCE or expected_cycles < -control_services.CYCLES_TOLERANCE:
            raise HTTPException(
                status_code=400,
                detail="Cumulative hours and cycles cannot be below the preceding accepted entry.",
            )
        if payload.block_hours is not None and abs(payload.block_hours - expected_hours) > control_services.HOURS_TOLERANCE:
            raise HTTPException(
                status_code=400,
                detail="Block hours do not reconcile with the preceding cumulative airframe hours.",
            )
        if payload.entry_cycles is not None and abs(payload.entry_cycles - expected_cycles) > control_services.CYCLES_TOLERANCE:
            raise HTTPException(
                status_code=400,
                detail="Entry cycles do not reconcile with the preceding cumulative cycle total.",
            )
        effective_payload = payload.model_copy(
            update={
                "block_hours": payload.block_hours if payload.block_hours is not None else expected_hours,
                "entry_cycles": payload.entry_cycles if payload.entry_cycles is not None else expected_cycles,
            }
        )

    row = control_services.create_canonical_utilisation(
        db,
        amo_id=current_user.effective_amo_id,
        actor_user_id=current_user.id,
        aircraft_serial_number=tail_id,
        payload=effective_payload,
    )
    projection.recompute_due_for_aircraft(
        db,
        amo_id=current_user.effective_amo_id,
        aircraft_serial_number=tail_id,
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
    if row.status == "APPLIED":
        projection.recompute_due_for_aircraft(
            db,
            amo_id=current_user.effective_amo_id,
            aircraft_serial_number=row.aircraft_serial_number,
        )
    _audit_correction_decision(
        db,
        correction=row,
        actor_user_id=current_user.id,
        decision=payload.decision,
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
