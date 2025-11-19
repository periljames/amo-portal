# backend/amodb/apps/crs/router.py
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ...database import get_db
from . import models as crs_models
from . import schemas as crs_schemas
from .utils import generate_crs_serial
from .pdf_renderer import create_crs_pdf

router = APIRouter(prefix="/crs", tags=["crs"])


@router.post("/", response_model=crs_schemas.CRSRead, status_code=status.HTTP_201_CREATED)
def create_crs(
    payload: crs_schemas.CRSCreate,
    db: Session = Depends(get_db),
):
    # Create CRS row first (without serial so we can use the DB id)
    crs = crs_models.CRS(
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
        work_order_no=payload.work_order_no,
        airframe_limit_unit=payload.airframe_limit_unit.value,
        expiry_date=payload.expiry_date,
        hrs_to_expiry=payload.hrs_to_expiry,
        sum_airframe_tat_expiry=payload.sum_airframe_tat_expiry,
        next_maintenance_due=payload.next_maintenance_due,
        issuer_full_name=payload.issuer_full_name,
        issuer_auth_ref=payload.issuer_auth_ref,
        issuer_license=payload.issuer_license,
        crs_issue_date=payload.crs_issue_date,
        crs_issuing_stamp=payload.crs_issuing_stamp,
    )

    db.add(crs)
    db.flush()  # get crs.id in the same transaction

    # Non-repeating CRS identity – based on DB id
    crs.crs_serial = generate_crs_serial(crs.id)
    crs.barcode_value = crs.crs_serial

    # Child sign-off rows
    for s in payload.signoffs:
        signoff = crs_models.CRSSignoff(
            crs=crs,
            category=s.category,
            sign_date=s.sign_date,
            full_name_and_signature=s.full_name_and_signature,
            internal_auth_ref=s.internal_auth_ref,
            stamp=s.stamp,
        )
        db.add(signoff)

    db.commit()
    db.refresh(crs)
    return crs


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
    return query.order_by(crs_models.CRS.id.desc()).offset(skip).limit(limit).all()


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
