# backend/amodb/apps/crs/router.py

from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..work import models as work_models
from ..fleet import models as fleet_models
from ..accounts import services as accounts_services, models as accounts_models
from . import models as crs_models
from . import schemas as crs_schemas
from .utils import generate_crs_serial
from .pdf_renderer import create_crs_pdf

router = APIRouter(prefix="/crs", tags=["crs"])


# --------------------------------------------------------------------------
# PREFILL ENDPOINT
# --------------------------------------------------------------------------

@router.get(
    "/prefill/{wo_no}",
    response_model=crs_schemas.CRSPrefill,
    summary="Prefill CRS fields from Aircraft + Components + WorkOrder",
)
def prefill_crs_for_work_order(
    wo_no: str,
    db: Session = Depends(get_db),
):
    """
    Given a work order number, pull:

      - WorkOrder (to get check_type, aircraft_serial_number, dates)
      - Aircraft (type, registration, MSN, total hours/cycles, base, owner)
      - AircraftComponent (L/R engines with hours/cycles)

    and return a CRSPrefill object the UI can use to initialise a new
    CRS form. This keeps users from re-typing aircraft & engine data.
    """
    work_order = (
        db.query(work_models.WorkOrder)
        .filter(work_models.WorkOrder.wo_number == wo_no)
        .first()
    )
    if not work_order:
        raise HTTPException(
            status_code=404,
            detail=f"Work order {wo_no} not found.",
        )

    ac = (
        db.query(fleet_models.Aircraft)
        .filter(fleet_models.Aircraft.serial_number == work_order.aircraft_serial_number)
        .first()
    )
    if not ac:
        raise HTTPException(
            status_code=400,
            detail=f"Aircraft with serial {work_order.aircraft_serial_number} not found.",
        )

    # Pull all components for this aircraft
    components = (
        db.query(fleet_models.AircraftComponent)
        .filter(
            fleet_models.AircraftComponent.aircraft_serial_number
            == ac.serial_number
        )
        .all()
    )

    def find_engine(side_keywords: List[str]) -> Optional[fleet_models.AircraftComponent]:
        side_keywords_upper = [k.upper() for k in side_keywords]
        for c in components:
            pos = (c.position or "").upper()
            if "ENG" in pos or "ENGINE" in pos:
                if any(k in pos for k in side_keywords_upper):
                    return c
        return None

    lh = find_engine(["LH", "L "])
    rh = find_engine(["RH", "R "])

    # Default next_maintenance_due text based on WO.check_type
    nmd_map = {
        "200HR": "200 HRS CHECK",
        "A": "A CHECK",
        "C": "C CHECK",
    }
    next_due = nmd_map.get(work_order.check_type or "", None)

    # Default airframe limit unit – almost always hours for you
    default_unit = crs_schemas.AirframeLimitUnit.HOURS

    today = datetime.utcnow().date()
    completion_date = work_order.due_date or work_order.open_date or today

    return crs_schemas.CRSPrefill(
        aircraft_serial_number=ac.serial_number,
        wo_no=work_order.wo_number,
        releasing_authority=crs_schemas.ReleasingAuthority.KCAA,  # can make configurable later
        operator_contractor=ac.owner or "SAFARILINK AVIATION LTD",
        job_no=work_order.wo_number,
        location=ac.home_base or "",
        aircraft_type=ac.template or ac.make or "",
        aircraft_reg=ac.registration,
        msn=ac.serial_number,
        lh_engine_type=lh.part_number if lh else None,
        rh_engine_type=rh.part_number if rh else None,
        lh_engine_sno=lh.serial_number if lh else None,
        rh_engine_sno=rh.serial_number if rh else None,
        aircraft_tat=ac.total_hours,
        aircraft_tac=ac.total_cycles,
        lh_hrs=lh.current_hours if lh else None,
        lh_cyc=lh.current_cycles if lh else None,
        rh_hrs=rh.current_hours if rh else None,
        rh_cyc=rh.current_cycles if rh else None,
        airframe_limit_unit=default_unit,
        next_maintenance_due=next_due,
        date_of_completion=completion_date,
        crs_issue_date=today,
    )


# --------------------------------------------------------------------------
# CREATE
# --------------------------------------------------------------------------

@router.post(
    "/",
    response_model=crs_schemas.CRSRead,
    status_code=status.HTTP_201_CREATED,
)
def create_crs(
    payload: crs_schemas.CRSCreate,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    # ----------------------------------------------------------
    # 0) Ensure current user is allowed to issue a CRS
    # ----------------------------------------------------------
    try:
        # We use the CRS issue date as the "as-of" date for authorisation.
        auth = accounts_services.require_user_can_issue_crs(
            db,
            user=current_user,
            at_date=payload.crs_issue_date,
            maintenance_scope=None,
            regulatory_authority=current_user.regulatory_authority,
        )
    except accounts_services.AuthorisationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )

    if not current_user.licence_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Certifying staff must have a licence_number configured before issuing a CRS.",
        )

    # ----------------------------------------------------------
    # 1) Enforce chain: Aircraft -> WorkOrder (+tasks) -> CRS
    # ----------------------------------------------------------

    # Work order number comes from the form (wo_no field)
    if not payload.wo_no:
        raise HTTPException(
            status_code=400,
            detail="wo_no (work order number) is required to create a CRS.",
        )

    work_order = (
        db.query(work_models.WorkOrder)
        .filter(work_models.WorkOrder.wo_number == payload.wo_no)
        .first()
    )
    if not work_order:
        raise HTTPException(
            status_code=404,
            detail=f"Work order {payload.wo_no} not found.",
        )

    # Confirm aircraft exists and matches
    ac = (
        db.query(fleet_models.Aircraft)
        .filter(fleet_models.Aircraft.serial_number == work_order.aircraft_serial_number)
        .first()
    )
    if not ac:
        raise HTTPException(
            status_code=400,
            detail=f"Aircraft with serial {work_order.aircraft_serial_number} not found.",
        )

    # Cross-check payload.aircraft_serial_number (from UI) with WO's aircraft
    if payload.aircraft_serial_number and payload.aircraft_serial_number != ac.serial_number:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Aircraft mismatch: payload has {payload.aircraft_serial_number} "
                f"but work order {work_order.wo_number} is for {ac.serial_number}."
            ),
        )

    # Ensure there is at least one task under this WO
    has_task = (
        db.query(work_models.WorkOrderTask.id)
        .filter(work_models.WorkOrderTask.work_order_id == work_order.id)
        .first()
    )
    if not has_task:
        raise HTTPException(
            status_code=400,
            detail="Cannot create CRS: work order has no tasks.",
        )

    # Only certain check types get a CRS
    allowed_types = {"200HR", "A", "C"}
    if not work_order.check_type or work_order.check_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Work order {work_order.wo_number} has check_type "
                f"'{work_order.check_type}'. No CRS required for this type."
            ),
        )

    # ----------------------------------------------------------
    # 2) Create CRS row (without serial first)
    # ----------------------------------------------------------
    crs = crs_models.CRS(
        aircraft_serial_number=ac.serial_number,  # from WO, not from client
        work_order_id=work_order.id,
        check_type=work_order.check_type,
        releasing_authority=payload.releasing_authority.value,
        operator_contractor=payload.operator_contractor,
        job_no=payload.job_no,
        wo_no=payload.wo_no,
        location=payload.location,
        aircraft_type=payload.aircraft_type,
        aircraft_reg=payload.aircraft_reg,
        msn=payload.msn,
        lh_engine_type=payload.lh_engine_type,
        rh_engine_type=payload.rh_engine_type,
        lh_engine_sno=payload.lh_engine_sno,
        rh_engine_sno=payload.rh_engine_sno,
        aircraft_tat=payload.aircraft_tat,
        aircraft_tac=payload.aircraft_tac,
        lh_hrs=payload.lh_hrs,
        lh_cyc=payload.lh_cyc,
        rh_hrs=payload.rh_hrs,
        rh_cyc=payload.rh_cyc,
        maintenance_carried_out=payload.maintenance_carried_out,
        deferred_maintenance=payload.deferred_maintenance,
        date_of_completion=payload.date_of_completion,
        amp_used=payload.amp_used,
        amm_used=payload.amm_used,
        mtx_data_used=payload.mtx_data_used,
        amp_reference=payload.amp_reference,
        amp_revision=payload.amp_revision,
        amp_issue_date=payload.amp_issue_date,
        amm_reference=payload.amm_reference,
        amm_revision=payload.amm_revision,
        amm_issue_date=payload.amm_issue_date,
        add_mtx_data=payload.add_mtx_data,
        work_order_no=payload.work_order_no or payload.wo_no,
        airframe_limit_unit=payload.airframe_limit_unit.value,
        expiry_date=payload.expiry_date,
        hrs_to_expiry=payload.hrs_to_expiry,
        sum_airframe_tat_expiry=payload.sum_airframe_tat_expiry,
        next_maintenance_due=payload.next_maintenance_due,
        # Certificate issued by – derived from authenticated user + authorisation
        issuer_full_name=current_user.full_name,
        issuer_auth_ref=str(auth.id),
        issuer_license=current_user.licence_number,
        crs_issue_date=payload.crs_issue_date,
        crs_issuing_stamp=payload.crs_issuing_stamp,
    )

    db.add(crs)
    db.flush()  # get crs.id in the same transaction

    # ----------------------------------------------------------
    # 3) Generate CRS serial in YYXNNN format
    # ----------------------------------------------------------
    crs.crs_serial = generate_crs_serial(
        db=db,
        check_type=work_order.check_type,
        issue_date=payload.crs_issue_date,
    )
    crs.barcode_value = crs.crs_serial

    # Child sign-off rows – default to the same certifying staff if fields are missing
    for s in payload.signoffs:
        signoff = crs_models.CRSSignoff(
            crs=crs,
            category=s.category,
            sign_date=s.sign_date,
            full_name_and_signature=s.full_name_and_signature or current_user.full_name,
            internal_auth_ref=s.internal_auth_ref or str(auth.id),
            stamp=s.stamp or payload.crs_issuing_stamp,
        )
        db.add(signoff)

    db.commit()
    db.refresh(crs)
    return crs


# --------------------------------------------------------------------------
# LIST / GET / UPDATE / ARCHIVE
# --------------------------------------------------------------------------

@router.get("/", response_model=List[crs_schemas.CRSRead])
def list_crs(
    skip: int = 0,
    limit: int = 100,
    only_active: bool = True,
    db: Session = Depends(get_db),
):
    query = db.query(crs_models.CRS)
    if only_active:
        query = query.filter(crs_models.CRS.is_archived.is_(False))
    return (
        query.order_by(crs_models.CRS.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{crs_id}", response_model=crs_schemas.CRSRead)
def get_crs(crs_id: int, db: Session = Depends(get_db)):
    crs = db.query(crs_models.CRS).filter(crs_models.CRS.id == crs_id).first()
    if not crs:
        raise HTTPException(status_code=404, detail="CRS not found")
    return crs


@router.put("/{crs_id}", response_model=crs_schemas.CRSRead)
def update_crs(
    crs_id: int,
    payload: crs_schemas.CRSUpdate,
    db: Session = Depends(get_db),
):
    crs = db.query(crs_models.CRS).filter(crs_models.CRS.id == crs_id).first()
    if not crs:
        raise HTTPException(status_code=404, detail="CRS not found")

    data = payload.model_dump(exclude_unset=True)

    # Convert enums to their string values for DB
    if "releasing_authority" in data and data["releasing_authority"] is not None:
        data["releasing_authority"] = data["releasing_authority"].value
    if "airframe_limit_unit" in data and data["airframe_limit_unit"] is not None:
        data["airframe_limit_unit"] = data["airframe_limit_unit"].value

    for field, value in data.items():
        setattr(crs, field, value)

    db.add(crs)
    db.commit()
    db.refresh(crs)
    return crs


@router.delete("/{crs_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_crs(crs_id: int, db: Session = Depends(get_db)):
    """
    Archive instead of hard-delete.
    Records stay available (read-only) until an external cleanup job
    purges rows where `expires_at < now()` (36-month retention).
    """
    crs = db.query(crs_models.CRS).filter(crs_models.CRS.id == crs_id).first()
    if not crs:
        raise HTTPException(status_code=404, detail="CRS not found")

    now = datetime.utcnow()
    crs.is_archived = True
    crs.archived_at = now

    # Approximate 36 months as 3 years.
    if crs.expires_at is None:
        crs.expires_at = now + timedelta(days=365 * 3)

    db.add(crs)
    db.commit()
    return


# --------------------------------------------------------------------------
# CRS PDF DOWNLOAD ENDPOINT
# --------------------------------------------------------------------------

@router.get(
    "/{crs_id}/pdf",
    response_class=FileResponse,
    summary="Download filled CRS PDF",
    include_in_schema=True,
)
def download_crs_pdf(crs_id: int):
    """
    Generate a filled, read-only CRS PDF for this record and return it.
    """
    try:
        pdf_path: Path = create_crs_pdf(crs_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="CRS not found")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=pdf_path.name,
    )
