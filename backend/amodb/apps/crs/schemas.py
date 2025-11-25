# backend/amodb/apps/crs/schemas.py

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# ENUMS
# ---------------------------------------------------------------------------


class ReleasingAuthority(str, enum.Enum):
    KCAA = "KCAA"
    FAA = "FAA"
    EASA = "EASA"
    OTHER = "OTHER"


class AirframeLimitUnit(str, enum.Enum):
    HOURS = "HOURS"
    CYCLES = "CYCLES"
    DAYS = "DAYS"
    DATE_ONLY = "DATE_ONLY"


# ---------------------------------------------------------------------------
# SIGNOFFS
# ---------------------------------------------------------------------------


class CRSSignoffInput(BaseModel):
    """Single signoff entry supplied by the client when creating/updating a CRS."""

    category: str = Field(..., description="Category of signoff, e.g. ISSUER / VERIFIER")
    sign_date: date
    full_name_and_signature: Optional[str] = None
    internal_auth_ref: Optional[str] = None
    stamp: Optional[str] = None


class CRSSignoffRead(BaseModel):
    """Signoff as returned from the API."""

    id: int
    category: str
    sign_date: date
    full_name_and_signature: Optional[str] = None
    internal_auth_ref: Optional[str] = None
    stamp: Optional[str] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# CRS BASE MODEL
# ---------------------------------------------------------------------------


class CRSBase(BaseModel):
    """
    Common CRS payload fields.

    This is the logical shape the frontend works with; the SQLAlchemy model
    adds server-managed fields like id, crs_serial, barcode_value, timestamps,
    etc.
    """

    # Linkage
    aircraft_serial_number: str = Field(..., max_length=50)
    work_order_id: Optional[int] = Field(
        None,
        description="Optional explicit work order id; usually inferred from WO number.",
    )

    # High-level classification
    check_type: Optional[str] = Field(None, max_length=20)
    releasing_authority: ReleasingAuthority
    operator_contractor: str = Field(..., max_length=255)

    # Work-order / job references
    job_no: Optional[str] = Field(None, max_length=100)
    wo_no: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=255)

    # Aircraft identity
    aircraft_type: str = Field(..., max_length=100)
    aircraft_reg: str = Field(..., max_length=50)
    msn: Optional[str] = Field(None, max_length=50)

    lh_engine_type: Optional[str] = Field(None, max_length=100)
    rh_engine_type: Optional[str] = Field(None, max_length=100)
    lh_engine_sno: Optional[str] = Field(None, max_length=100)
    rh_engine_sno: Optional[str] = Field(None, max_length=100)

    # Flight hours / cycles at CRS
    aircraft_tat: Optional[float] = None
    aircraft_tac: Optional[float] = None
    lh_hrs: Optional[float] = None
    lh_cyc: Optional[float] = None
    rh_hrs: Optional[float] = None
    rh_cyc: Optional[float] = None

    # Work performed
    maintenance_carried_out: str
    deferred_maintenance: Optional[str] = None

    # Dates
    date_of_completion: date

    # Document usage flags
    amp_used: bool
    amm_used: bool
    mtx_data_used: bool

    amp_reference: Optional[str] = Field(None, max_length=255)
    amp_revision: Optional[str] = Field(None, max_length=50)
    amp_issue_date: Optional[date] = None

    amm_reference: Optional[str] = Field(None, max_length=255)
    amm_revision: Optional[str] = Field(None, max_length=50)
    amm_issue_date: Optional[date] = None

    add_mtx_data: Optional[str] = Field(None, max_length=255)

    # Airframe limit / follow-up
    work_order_no: Optional[str] = Field(None, max_length=100)
    airframe_limit_unit: AirframeLimitUnit
    expiry_date: Optional[date] = None
    hrs_to_expiry: Optional[float] = None
    sum_airframe_tat_expiry: Optional[float] = None
    next_maintenance_due: Optional[str] = Field(None, max_length=255)

    # Issuer details
    issuer_full_name: str = Field(..., max_length=255)
    issuer_auth_ref: str = Field(..., max_length=255)
    issuer_license: str = Field(..., max_length=100)
    crs_issue_date: date
    crs_issuing_stamp: Optional[str] = Field(None, max_length=255)

    # Nested signoffs (issuer / verifier etc.)
    signoffs: List[CRSSignoffInput] = Field(
        default_factory=list,
        description="List of signoff entries (issuer / verifier etc.).",
    )


# ---------------------------------------------------------------------------
# CREATE / UPDATE / READ
# ---------------------------------------------------------------------------


class CRSCreate(CRSBase):
    """
    Payload for creating a new CRS.

    The backend calculates crs_serial, barcode_value, created_by_id,
    created_at, updated_at, and is_archived.
    """

    pass


class CRSUpdate(BaseModel):
    """
    Partial update payload for an existing CRS.

    All fields are optional and only supplied values will be updated.
    """

    # Same fields as CRSBase but all optional
    aircraft_serial_number: Optional[str] = Field(None, max_length=50)
    work_order_id: Optional[int] = None

    check_type: Optional[str] = Field(None, max_length=20)
    releasing_authority: Optional[ReleasingAuthority] = None
    operator_contractor: Optional[str] = Field(None, max_length=255)

    job_no: Optional[str] = Field(None, max_length=100)
    wo_no: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=255)

    aircraft_type: Optional[str] = Field(None, max_length=100)
    aircraft_reg: Optional[str] = Field(None, max_length=50)
    msn: Optional[str] = Field(None, max_length=50)

    lh_engine_type: Optional[str] = Field(None, max_length=100)
    rh_engine_type: Optional[str] = Field(None, max_length=100)
    lh_engine_sno: Optional[str] = Field(None, max_length=100)
    rh_engine_sno: Optional[str] = Field(None, max_length=100)

    aircraft_tat: Optional[float] = None
    aircraft_tac: Optional[float] = None
    lh_hrs: Optional[float] = None
    lh_cyc: Optional[float] = None
    rh_hrs: Optional[float] = None
    rh_cyc: Optional[float] = None

    maintenance_carried_out: Optional[str] = None
    deferred_maintenance: Optional[str] = None

    date_of_completion: Optional[date] = None

    amp_used: Optional[bool] = None
    amm_used: Optional[bool] = None
    mtx_data_used: Optional[bool] = None

    amp_reference: Optional[str] = Field(None, max_length=255)
    amp_revision: Optional[str] = Field(None, max_length=50)
    amp_issue_date: Optional[date] = None

    amm_reference: Optional[str] = Field(None, max_length=255)
    amm_revision: Optional[str] = Field(None, max_length=50)
    amm_issue_date: Optional[date] = None

    add_mtx_data: Optional[str] = Field(None, max_length=255)

    work_order_no: Optional[str] = Field(None, max_length=100)
    airframe_limit_unit: Optional[AirframeLimitUnit] = None
    expiry_date: Optional[date] = None
    hrs_to_expiry: Optional[float] = None
    sum_airframe_tat_expiry: Optional[float] = None
    next_maintenance_due: Optional[str] = Field(None, max_length=255)

    issuer_full_name: Optional[str] = Field(None, max_length=255)
    issuer_auth_ref: Optional[str] = Field(None, max_length=255)
    issuer_license: Optional[str] = Field(None, max_length=100)
    crs_issue_date: Optional[date] = None
    crs_issuing_stamp: Optional[str] = Field(None, max_length=255)

    # Allow updating signoffs as a whole list (replace semantics)
    signoffs: Optional[List[CRSSignoffInput]] = None


class CRSRead(CRSBase):
    """
    Full CRS record as returned to the client.

    Extends CRSBase with database-managed fields.
    """

    id: int
    crs_serial: str
    barcode_value: str

    # The canonical work_order_id the CRS is attached to
    work_order_id: int

    # Who created this CRS (GUID-style id from accounts User)
    created_by_id: Optional[str] = None

    created_at: datetime
    updated_at: datetime
    is_archived: bool
    archived_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    # For reads, signoffs are fully hydrated
    signoffs: List[CRSSignoffRead] = Field(default_factory=list)

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# PREFILL PAYLOAD
# ---------------------------------------------------------------------------


class CRSPrefill(BaseModel):
    """
    Lightweight payload returned by the /prefill endpoint.

    Used to pre-populate the CRS form from aircraft + work-order data.
    """

    aircraft_serial_number: str
    wo_no: str

    releasing_authority: ReleasingAuthority
    operator_contractor: str
    job_no: str
    location: str

    aircraft_type: str
    aircraft_reg: str
    msn: str

    lh_engine_type: str
    rh_engine_type: str
    lh_engine_sno: str
    rh_engine_sno: str

    aircraft_tat: float
    aircraft_tac: float
    lh_hrs: float
    lh_cyc: float
    rh_hrs: float
    rh_cyc: float

    airframe_limit_unit: AirframeLimitUnit
    next_maintenance_due: str

    date_of_completion: date
    crs_issue_date: date
