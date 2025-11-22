# backend/amodb/apps/crs/schemas.py
from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


# --- Enums for radio buttons / check type ---


class ReleasingAuthority(str, Enum):
    KCAA = "KCAA"
    ECAA = "ECAA"
    GCAA = "GCAA"


class AirframeLimitUnit(str, Enum):
    HOURS = "HOURS"
    CYCLES = "CYCLES"


class CRSCheckType(str, Enum):
    """
    Only check types that are allowed to have a CRS.

    L-checks, 100-hour checks, etc. are intentionally NOT here
    because they must never generate a CRS.
    """
    H200 = "200HR"
    A = "A"
    C = "C"


# --- Sign-off table ---


class CRSSignoffBase(BaseModel):
    category: str  # 'AEROPLANES', 'C-ENGINES', etc
    sign_date: Optional[date] = None
    full_name_and_signature: Optional[str] = None
    internal_auth_ref: Optional[str] = None
    stamp: Optional[str] = None


class CRSSignoffCreate(CRSSignoffBase):
    pass


class CRSSignoffRead(CRSSignoffBase):
    id: int

    class Config:
        from_attributes = True


# --- CRS main record (request/response) ---


class CRSBase(BaseModel):
    # Link back to aircraft (WinAir serial) and WO number
    aircraft_serial_number: str
    wo_no: str

    # Header
    releasing_authority: ReleasingAuthority
    operator_contractor: str
    job_no: Optional[str] = None
    location: str

    # Aircraft & engines
    aircraft_type: str
    aircraft_reg: str
    msn: Optional[str] = None

    lh_engine_type: Optional[str] = None
    rh_engine_type: Optional[str] = None
    lh_engine_sno: Optional[str] = None
    rh_engine_sno: Optional[str] = None

    aircraft_tat: Optional[float] = None
    aircraft_tac: Optional[float] = None
    lh_hrs: Optional[float] = None
    lh_cyc: Optional[float] = None
    rh_hrs: Optional[float] = None
    rh_cyc: Optional[float] = None

    # Work / deferred maintenance
    maintenance_carried_out: str
    deferred_maintenance: Optional[str] = None
    date_of_completion: date

    # Maintenance data – check boxes & refs
    amp_used: bool = False
    amm_used: bool = False
    mtx_data_used: bool = False

    amp_reference: Optional[str] = None
    amp_revision: Optional[str] = None
    amp_issue_date: Optional[date] = None

    amm_reference: Optional[str] = None
    amm_revision: Optional[str] = None
    amm_issue_date: Optional[date] = None

    add_mtx_data: Optional[str] = None
    work_order_no: Optional[str] = None

    # Expiry / next check
    airframe_limit_unit: AirframeLimitUnit
    expiry_date: Optional[date] = None
    hrs_to_expiry: Optional[float] = None
    sum_airframe_tat_expiry: Optional[float] = None
    next_maintenance_due: Optional[str] = None

    # Certificate issued by
    issuer_full_name: str
    issuer_auth_ref: str
    issuer_license: str
    crs_issue_date: date
    crs_issuing_stamp: Optional[str] = None


class CRSCreate(CRSBase):
    # All form fields + optional nested sign-off rows
    signoffs: List[CRSSignoffCreate] = []


class CRSUpdate(BaseModel):
    """
    Full update; all fields optional. Only those provided will be changed.
    Note: check_type is NOT exposed here – it is derived from the Work Order.
    """

    aircraft_serial_number: Optional[str] = None
    wo_no: Optional[str] = None

    releasing_authority: Optional[ReleasingAuthority] = None
    operator_contractor: Optional[str] = None
    job_no: Optional[str] = None
    location: Optional[str] = None

    aircraft_type: Optional[str] = None
    aircraft_reg: Optional[str] = None
    msn: Optional[str] = None

    lh_engine_type: Optional[str] = None
    rh_engine_type: Optional[str] = None
    lh_engine_sno: Optional[str] = None
    rh_engine_sno: Optional[str] = None

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

    amp_reference: Optional[str] = None
    amp_revision: Optional[str] = None
    amp_issue_date: Optional[date] = None

    amm_reference: Optional[str] = None
    amm_revision: Optional[str] = None
    amm_issue_date: Optional[date] = None

    add_mtx_data: Optional[str] = None
    work_order_no: Optional[str] = None

    airframe_limit_unit: Optional[AirframeLimitUnit] = None
    expiry_date: Optional[date] = None
    hrs_to_expiry: Optional[float] = None
    sum_airframe_tat_expiry: Optional[float] = None
    next_maintenance_due: Optional[str] = None

    issuer_full_name: Optional[str] = None
    issuer_auth_ref: Optional[str] = None
    issuer_license: Optional[str] = None
    crs_issue_date: Optional[date] = None
    crs_issuing_stamp: Optional[str] = None


class CRSRead(CRSBase):
    id: int
    crs_serial: str
    barcode_value: str

    # Derived from WorkOrder.check_type; read-only on the API
    check_type: Optional[CRSCheckType] = None

    created_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    is_archived: bool
    archived_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    signoffs: List[CRSSignoffRead] = []

    class Config:
        from_attributes = True


# ---------------- PREFILL RESPONSE ----------------

class CRSPrefill(BaseModel):
    """
    Lightweight object used to pre-populate a new CRS form from
    Aircraft + AircraftComponent + WorkOrder.

    Most fields are optional; the UI can decide what to lock and what
    to allow the user to edit.
    """
    aircraft_serial_number: str
    wo_no: str

    releasing_authority: ReleasingAuthority
    operator_contractor: str
    job_no: Optional[str] = None
    location: str

    aircraft_type: Optional[str] = None
    aircraft_reg: Optional[str] = None
    msn: Optional[str] = None

    lh_engine_type: Optional[str] = None
    rh_engine_type: Optional[str] = None
    lh_engine_sno: Optional[str] = None
    rh_engine_sno: Optional[str] = None

    aircraft_tat: Optional[float] = None
    aircraft_tac: Optional[float] = None
    lh_hrs: Optional[float] = None
    lh_cyc: Optional[float] = None
    rh_hrs: Optional[float] = None
    rh_cyc: Optional[float] = None

    airframe_limit_unit: Optional[AirframeLimitUnit] = None
    next_maintenance_due: Optional[str] = None

    date_of_completion: Optional[date] = None
    crs_issue_date: Optional[date] = None
