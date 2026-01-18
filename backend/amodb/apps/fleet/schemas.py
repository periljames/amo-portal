"""
Pydantic schemas for the fleet app.

Scope:
- Aircraft master data.
- Aircraft components (engines, props, APU, etc.) with life limits.
- Aircraft utilisation entries (per techlog / flight).
- Maintenance programme items and aircraft-level status.
"""

from __future__ import annotations

from datetime import date as DateType, datetime as DateTimeType
import re
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field, field_validator

from amodb.apps.accounts.models import RegulatoryAuthority
from .models import (
    MaintenanceProgramCategoryEnum,
    AircraftDocumentStatus,
    AircraftDocumentType,
)

MIN_VALID_DATE = DateType(1950, 1, 1)
MAX_HOURS = 1_000_000.0
MAX_CYCLES = 1_000_000.0
MAX_CALENDAR_MONTHS = 1_200

AIRCRAFT_SERIAL_PATTERN = re.compile(r"^[A-Z0-9-]{1,50}$")
REGISTRATION_PATTERN = re.compile(r"^[A-Z0-9-]{1,20}$")
PART_NUMBER_PATTERN = re.compile(r"^[A-Z0-9./-]{1,50}$")
COMPONENT_SERIAL_PATTERN = re.compile(r"^[A-Z0-9./-]{1,50}$")


# ---------------- AIRCRAFT ----------------


class AircraftBase(BaseModel):
    """
    Aircraft master record.

    `serial_number` is your AIN-style identifier.
    `registration` is the aircraft REG.
    Additional optional fields align with ATA Spec 2000-style codes
    (model code, operator code, supplier code, etc.).
    """

    # Core identifiers
    serial_number: str
    registration: str

    # Configuration / description
    template: Optional[str] = None          # e.g. 'DHC8-315', 'C208B'
    make: Optional[str] = None              # manufacturer
    model: Optional[str] = None             # subtype / series
    home_base: Optional[str] = None         # ICAO/IATA/base code
    owner: Optional[str] = None             # free text owner/operator

    # ATA Spec 2000-style coding (all optional, for standardisation)
    aircraft_model_code: Optional[str] = None          # model code used in manuals/IPC
    operator_code: Optional[str] = None                # OPR
    supplier_code: Optional[str] = None                # SPL / lessor
    company_name: Optional[str] = None                 # WHO
    internal_aircraft_identifier: Optional[str] = None # internal fleet ID / hangar ID

    status: Optional[str] = "OPEN"
    is_active: bool = True

    # Utilisation snapshot (as of last_log_date)
    last_log_date: Optional[DateType] = None
    total_hours: Optional[float] = Field(default=None, ge=0, le=MAX_HOURS)
    total_cycles: Optional[float] = Field(default=None, ge=0, le=MAX_CYCLES)

    @field_validator("serial_number", mode="before")
    @classmethod
    def validate_serial_number(cls, value: str) -> str:
        if value is None:
            raise ValueError("serial_number is required")
        trimmed = str(value).strip().upper()
        if not AIRCRAFT_SERIAL_PATTERN.match(trimmed):
            raise ValueError("serial_number must be A-Z/0-9 with optional hyphens.")
        return trimmed

    @field_validator("registration", mode="before")
    @classmethod
    def validate_registration(cls, value: str) -> str:
        if value is None:
            raise ValueError("registration is required")
        trimmed = str(value).strip().upper()
        if not REGISTRATION_PATTERN.match(trimmed):
            raise ValueError("registration must be A-Z/0-9 with optional hyphens.")
        return trimmed

    @field_validator("last_log_date")
    @classmethod
    def validate_last_log_date(cls, value: Optional[DateType]) -> Optional[DateType]:
        if value is None:
            return value
        if value < MIN_VALID_DATE:
            raise ValueError("last_log_date is earlier than allowed.")
        if value > DateType.today():
            raise ValueError("last_log_date cannot be in the future.")
        return value


class AircraftCreate(AircraftBase):
    """
    Used when initially loading / creating aircraft.
    All fields from AircraftBase are allowed.
    """
    safety_confirmed: Optional[bool] = Field(default=None, exclude=True)


class AircraftUpdate(BaseModel):
    """
    Partial update – all fields optional.
    serial_number is taken from the path, not from the body.
    """

    registration: Optional[str] = None

    template: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    home_base: Optional[str] = None
    owner: Optional[str] = None

    # ATA Spec 2000-style coding
    aircraft_model_code: Optional[str] = None
    operator_code: Optional[str] = None
    supplier_code: Optional[str] = None
    company_name: Optional[str] = None
    internal_aircraft_identifier: Optional[str] = None

    status: Optional[str] = None
    is_active: Optional[bool] = None

    last_log_date: Optional[DateType] = None
    total_hours: Optional[float] = None
    total_cycles: Optional[float] = None
    safety_confirmed: Optional[bool] = Field(default=None, exclude=True)


class AircraftRead(AircraftBase):
    created_at: DateTimeType
    updated_at: DateTimeType
    verification_status: str

    class Config:
        from_attributes = True


# ---------------- AIRCRAFT DOCUMENTS ----------------


class AircraftDocumentBase(BaseModel):
    document_type: AircraftDocumentType
    authority: RegulatoryAuthority = RegulatoryAuthority.KCAA
    title: Optional[str] = None
    reference_number: Optional[str] = None
    compliance_basis: Optional[str] = None
    issued_on: Optional[DateType] = None
    expires_on: Optional[DateType] = None
    alert_window_days: int = Field(default=30, ge=0, le=365)

    @field_validator("issued_on", "expires_on")
    @classmethod
    def validate_dates(cls, value: Optional[DateType]) -> Optional[DateType]:
        if value is None:
            return value
        if value < MIN_VALID_DATE:
            raise ValueError("Date is earlier than allowed.")
        return value

    @field_validator("expires_on")
    @classmethod
    def validate_expiry_after_issue(
        cls, value: Optional[DateType], values: Dict[str, Any]
    ) -> Optional[DateType]:
        issued_on = values.get("issued_on")
        if value and issued_on and value < issued_on:
            raise ValueError("expires_on cannot be earlier than issued_on.")
        return value


class AircraftDocumentCreate(AircraftDocumentBase):
    pass


class AircraftDocumentUpdate(BaseModel):
    title: Optional[str] = None
    reference_number: Optional[str] = None
    compliance_basis: Optional[str] = None
    issued_on: Optional[DateType] = None
    expires_on: Optional[DateType] = None
    alert_window_days: Optional[int] = Field(default=None, ge=0, le=365)
    status: Optional[AircraftDocumentStatus] = None

    @field_validator("expires_on")
    @classmethod
    def validate_expiry_after_issue(
        cls, value: Optional[DateType], values: Dict[str, Any]
    ) -> Optional[DateType]:
        issued_on = values.get("issued_on")
        if value and issued_on and value < issued_on:
            raise ValueError("expires_on cannot be earlier than issued_on.")
        return value


class AircraftDocumentRead(AircraftDocumentBase):
    id: int
    aircraft_serial_number: str
    status: AircraftDocumentStatus
    is_blocking: bool
    days_to_expiry: Optional[int] = None
    missing_evidence: bool = False
    file_original_name: Optional[str] = None
    file_storage_path: Optional[str] = None
    file_content_type: Optional[str] = None
    last_uploaded_at: Optional[DateTimeType] = None
    last_uploaded_by_user_id: Optional[str] = None
    override_reason: Optional[str] = None
    override_expires_on: Optional[DateType] = None
    override_by_user_id: Optional[str] = None
    override_recorded_at: Optional[DateTimeType] = None
    created_at: DateTimeType
    updated_at: DateTimeType

    class Config:
        from_attributes = True


class AircraftDocumentOverride(BaseModel):
    reason: str
    override_expires_on: Optional[DateType] = None


class AircraftDocumentDownloadRequest(BaseModel):
    document_ids: List[int] = Field(..., min_length=1)


class AircraftComplianceSummary(BaseModel):
    aircraft_serial_number: str
    documents_total: int
    is_blocking: bool
    blocking_documents: List[AircraftDocumentRead]
    due_soon_documents: List[AircraftDocumentRead]
    overdue_documents: List[AircraftDocumentRead]
    overrides: List[AircraftDocumentRead]
    documents: List[AircraftDocumentRead]


class AircraftImportRow(BaseModel):
    row_number: Optional[int] = None
    serial_number: str
    registration: str

    template: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    home_base: Optional[str] = None
    owner: Optional[str] = None

    aircraft_model_code: Optional[str] = None
    operator_code: Optional[str] = None
    supplier_code: Optional[str] = None
    company_name: Optional[str] = None
    internal_aircraft_identifier: Optional[str] = None

    status: Optional[str] = "OPEN"
    is_active: Optional[bool] = True

    last_log_date: Optional[DateType] = None
    total_hours: Optional[float] = None
    total_cycles: Optional[float] = None


class AircraftImportConfirmedCell(BaseModel):
    original: Any = None
    proposed: Any = None
    final: Any = None
    decision: Optional[str] = None


class AircraftImportConfirmedRow(BaseModel):
    row_number: int
    cells: Dict[str, AircraftImportConfirmedCell]


class AircraftImportRequest(BaseModel):
    rows: List[AircraftImportRow] = []
    confirmed_rows: Optional[List[AircraftImportConfirmedRow]] = None
    batch_id: Optional[str] = None
    preview_id: Optional[str] = None
    approved_row_numbers: Optional[List[int]] = None
    rejected_row_numbers: Optional[List[int]] = None


class AircraftImportPreviewRow(BaseModel):
    row_number: int
    data: Dict[str, Any]
    errors: List[str]
    warnings: List[str]
    action: str
    suggested_template: Optional[Dict[str, Any]] = None
    formula_proposals: Optional[List[Dict[str, Any]]] = None


class AircraftImportPreviewResponse(BaseModel):
    preview_id: str
    total_rows: int
    rows: List[AircraftImportPreviewRow]
    column_mapping: Dict[str, Optional[str]]
    summary: Dict[str, int]
    ocr: Optional[Dict[str, Any]] = None
    formula_discrepancies: Optional[List[Dict[str, Any]]] = None
    ispec: Optional["ISpecComplianceReport"] = None


class AircraftImportTemplateBase(BaseModel):
    name: str
    template_type: str = "aircraft"
    aircraft_template: Optional[str] = None
    model_code: Optional[str] = None
    operator_code: Optional[str] = None
    column_mapping: Optional[Dict[str, Optional[str]]] = None
    default_values: Optional[Dict[str, Any]] = None


class AircraftImportTemplateCreate(AircraftImportTemplateBase):
    pass


class AircraftImportTemplateUpdate(BaseModel):
    name: Optional[str] = None
    template_type: Optional[str] = None
    aircraft_template: Optional[str] = None
    model_code: Optional[str] = None
    operator_code: Optional[str] = None
    column_mapping: Optional[Dict[str, Optional[str]]] = None
    default_values: Optional[Dict[str, Any]] = None


class AircraftImportTemplateRead(AircraftImportTemplateBase):
    id: int
    created_at: DateTimeType
    updated_at: DateTimeType

    class Config:
        from_attributes = True


class ImportSnapshotRead(BaseModel):
    id: int
    batch_id: str
    import_type: str
    diff_map: Dict[str, Any]
    created_at: DateTimeType
    created_by_user_id: Optional[str] = None

    class Config:
        from_attributes = True


class ISpecComplianceRow(BaseModel):
    row_number: int
    missing_fields: List[str]


class ISpecComplianceIssue(BaseModel):
    row_number: int
    field: str
    code: str
    message: str


class ISpecComplianceReport(BaseModel):
    compliant: bool
    required_fields: List[str]
    missing_columns: List[str]
    rows_missing_required_fields: List[ISpecComplianceRow]
    issues: List[ISpecComplianceIssue]
    truncated: bool = False


class ISpecExchangeComponent(BaseModel):
    position: str
    ata: Optional[str] = None
    part_number: Optional[str] = None
    serial_number: Optional[str] = None
    manufacturer_code: Optional[str] = None
    operator_code: Optional[str] = None
    installed_date: Optional[DateType] = None
    installed_hours: Optional[float] = None
    installed_cycles: Optional[float] = None
    current_hours: Optional[float] = None
    current_cycles: Optional[float] = None
    notes: Optional[str] = None


class ISpecExchangeAircraft(BaseModel):
    serial_number: str
    registration: str
    aircraft_model_code: Optional[str] = None
    operator_code: Optional[str] = None
    supplier_code: Optional[str] = None
    company_name: Optional[str] = None
    internal_aircraft_identifier: Optional[str] = None
    last_log_date: Optional[DateType] = None
    total_hours: Optional[float] = None
    total_cycles: Optional[float] = None
    components: Optional[List[ISpecExchangeComponent]] = None


class ISpecExchangeEnvelope(BaseModel):
    spec: str
    version: str
    generated_at: DateTimeType
    total: int
    offset: int
    limit: int
    aircraft: List[ISpecExchangeAircraft]


class ISpecExchangeValidationItem(BaseModel):
    identifier: str
    compliant: bool
    missing_fields: List[str]
    issues: List[ISpecComplianceIssue]


class ISpecExchangeValidationReport(BaseModel):
    compliant: bool
    aircraft: List[ISpecExchangeValidationItem]
    components: List[ISpecExchangeValidationItem]


# ---------------- COMPONENTS ----------------


class AircraftComponentBase(BaseModel):
    aircraft_serial_number: str
    position: str

    ata: Optional[str] = None
    part_number: Optional[str] = None
    serial_number: Optional[str] = None
    description: Optional[str] = None

    installed_date: Optional[DateType] = None
    installed_hours: Optional[float] = Field(default=None, ge=0, le=MAX_HOURS)
    installed_cycles: Optional[float] = Field(default=None, ge=0, le=MAX_CYCLES)

    current_hours: Optional[float] = Field(default=None, ge=0, le=MAX_HOURS)
    current_cycles: Optional[float] = Field(default=None, ge=0, le=MAX_CYCLES)

    notes: Optional[str] = None

    # Life limit configuration
    tbo_hours: Optional[float] = Field(default=None, ge=0, le=MAX_HOURS)
    tbo_cycles: Optional[float] = Field(default=None, ge=0, le=MAX_CYCLES)
    tbo_calendar_months: Optional[int] = Field(
        default=None, ge=0, le=MAX_CALENDAR_MONTHS
    )

    hsi_hours: Optional[float] = Field(default=None, ge=0, le=MAX_HOURS)
    hsi_cycles: Optional[float] = Field(default=None, ge=0, le=MAX_CYCLES)
    hsi_calendar_months: Optional[int] = Field(
        default=None, ge=0, le=MAX_CALENDAR_MONTHS
    )

    # Overhaul reference
    last_overhaul_date: Optional[DateType] = None
    last_overhaul_hours: Optional[float] = Field(default=None, ge=0, le=MAX_HOURS)
    last_overhaul_cycles: Optional[float] = Field(default=None, ge=0, le=MAX_CYCLES)

    # Standardisation for reliability
    manufacturer_code: Optional[str] = None
    operator_code: Optional[str] = None
    unit_of_measure_hours: Optional[str] = "H"
    unit_of_measure_cycles: Optional[str] = "C"

    @field_validator("part_number", "serial_number", mode="before")
    @classmethod
    def validate_part_serial_format(cls, value: Optional[str], info) -> Optional[str]:
        if value is None:
            return value
        trimmed = str(value).strip().upper()
        pattern = (
            PART_NUMBER_PATTERN
            if info.field_name == "part_number"
            else COMPONENT_SERIAL_PATTERN
        )
        if not pattern.match(trimmed):
            raise ValueError(f"{info.field_name} contains invalid characters.")
        return trimmed

    @field_validator("installed_date", "last_overhaul_date")
    @classmethod
    def validate_component_dates(
        cls, value: Optional[DateType]
    ) -> Optional[DateType]:
        if value is None:
            return value
        if value < MIN_VALID_DATE:
            raise ValueError("date is earlier than allowed.")
        if value > DateType.today():
            raise ValueError("date cannot be in the future.")
        return value


class AircraftComponentCreate(AircraftComponentBase):
    safety_confirmed: Optional[bool] = Field(default=None, exclude=True)


class AircraftComponentUpdate(BaseModel):
    aircraft_serial_number: Optional[str] = None
    position: Optional[str] = None

    ata: Optional[str] = None
    part_number: Optional[str] = None
    serial_number: Optional[str] = None
    description: Optional[str] = None

    installed_date: Optional[DateType] = None
    installed_hours: Optional[float] = None
    installed_cycles: Optional[float] = None

    current_hours: Optional[float] = None
    current_cycles: Optional[float] = None

    notes: Optional[str] = None

    tbo_hours: Optional[float] = None
    tbo_cycles: Optional[float] = None
    tbo_calendar_months: Optional[int] = None

    hsi_hours: Optional[float] = None
    hsi_cycles: Optional[float] = None
    hsi_calendar_months: Optional[int] = None

    last_overhaul_date: Optional[DateType] = None
    last_overhaul_hours: Optional[float] = None
    last_overhaul_cycles: Optional[float] = None

    manufacturer_code: Optional[str] = None
    operator_code: Optional[str] = None
    unit_of_measure_hours: Optional[str] = None
    unit_of_measure_cycles: Optional[str] = None
    safety_confirmed: Optional[bool] = Field(default=None, exclude=True)


class AircraftComponentRead(AircraftComponentBase):
    id: int
    verification_status: str

    class Config:
        from_attributes = True


class AircraftComponentImportRow(BaseModel):
    row_number: Optional[int] = None
    position: str

    ata: Optional[str] = None
    part_number: Optional[str] = None
    serial_number: Optional[str] = None
    description: Optional[str] = None

    installed_date: Optional[DateType] = None
    installed_hours: Optional[float] = None
    installed_cycles: Optional[float] = None

    current_hours: Optional[float] = None
    current_cycles: Optional[float] = None

    notes: Optional[str] = None
    manufacturer_code: Optional[str] = None
    operator_code: Optional[str] = None


class AircraftComponentImportRequest(BaseModel):
    rows: List[AircraftComponentImportRow]


# For responses that show one aircraft with its components:
class AircraftWithComponents(AircraftRead):
    components: List["AircraftComponentRead"] = []


# ---------------- AIRCRAFT USAGE ----------------


class AircraftUsageBase(BaseModel):
    """
    Core utilisation fields, excluding aircraft_serial_number which
    comes from the path when creating entries.
    """

    date: DateType
    techlog_no: str = Field(..., min_length=1)
    station: Optional[str] = None

    block_hours: float = Field(..., ge=0, le=MAX_HOURS)
    cycles: float = Field(..., ge=0, le=MAX_CYCLES)

    ttaf_after: Optional[float] = None
    tca_after: Optional[float] = None
    ttesn_after: Optional[float] = None
    tcesn_after: Optional[float] = None
    ttsoh_after: Optional[float] = None
    ttshsi_after: Optional[float] = None
    tcsoh_after: Optional[float] = None
    pttsn_after: Optional[float] = None
    pttso_after: Optional[float] = None
    tscoa_after: Optional[float] = None

    hours_to_mx: Optional[float] = Field(default=None, ge=0, le=MAX_HOURS)
    days_to_mx: Optional[int] = Field(default=None, ge=0, le=MAX_CALENDAR_MONTHS * 31)

    remarks: Optional[str] = None
    note: Optional[str] = None

    @field_validator("date")
    @classmethod
    def validate_usage_date(cls, value: DateType) -> DateType:
        if value < MIN_VALID_DATE:
            raise ValueError("date is earlier than allowed.")
        if value > DateType.today():
            raise ValueError("date cannot be in the future.")
        return value


class AircraftUsageCreate(AircraftUsageBase):
    """
    Create payload – aircraft_serial_number is taken from the path,
    not from the body.
    """
    safety_confirmed: Optional[bool] = Field(default=None, exclude=True)


class AircraftUsageUpdate(BaseModel):
    """
    Partial update for an AircraftUsage entry.

    `last_seen_updated_at` is required for optimistic concurrency:
    the client must send the last `updated_at` value it saw. If it
    does not match the current DB value, the update will be rejected.
    """

    date: Optional[DateType] = None
    techlog_no: Optional[str] = None
    station: Optional[str] = None

    block_hours: Optional[float] = Field(default=None, ge=0, le=MAX_HOURS)
    cycles: Optional[float] = Field(default=None, ge=0, le=MAX_CYCLES)

    ttaf_after: Optional[float] = None
    tca_after: Optional[float] = None
    ttesn_after: Optional[float] = None
    tcesn_after: Optional[float] = None
    ttsoh_after: Optional[float] = None
    ttshsi_after: Optional[float] = None
    tcsoh_after: Optional[float] = None
    pttsn_after: Optional[float] = None
    pttso_after: Optional[float] = None
    tscoa_after: Optional[float] = None

    hours_to_mx: Optional[float] = Field(default=None, ge=0, le=MAX_HOURS)
    days_to_mx: Optional[int] = Field(default=None, ge=0, le=MAX_CALENDAR_MONTHS * 31)

    remarks: Optional[str] = None
    note: Optional[str] = None

    last_seen_updated_at: DateTimeType
    safety_confirmed: Optional[bool] = Field(default=None, exclude=True)

    @field_validator("date")
    @classmethod
    def validate_usage_update_date(
        cls, value: Optional[DateType]
    ) -> Optional[DateType]:
        if value is None:
            return value
        if value < MIN_VALID_DATE:
            raise ValueError("date is earlier than allowed.")
        if value > DateType.today():
            raise ValueError("date cannot be in the future.")
        return value


class AircraftUsageRead(AircraftUsageBase):
    id: int
    aircraft_serial_number: str

    created_at: DateTimeType
    updated_at: DateTimeType
    created_by_user_id: Optional[int] = None
    updated_by_user_id: Optional[int] = None
    verification_status: str

    class Config:
        from_attributes = True


class AircraftUsageSummary(BaseModel):
    aircraft_serial_number: str
    total_hours: Optional[float] = None
    total_cycles: Optional[float] = None
    seven_day_daily_average_hours: Optional[float] = None

    next_due_program_item_id: Optional[int] = None
    next_due_task_code: Optional[str] = None
    next_due_date: Optional[DateType] = None
    next_due_hours: Optional[float] = None
    next_due_cycles: Optional[float] = None
    

# ---------------- MAINTENANCE PROGRAMME ----------------


class MaintenanceProgramItemBase(BaseModel):
    aircraft_template: str
    ata_chapter: str
    task_code: str
    category: MaintenanceProgramCategoryEnum = MaintenanceProgramCategoryEnum.AIRFRAME
    description: str

    interval_hours: Optional[float] = None
    interval_cycles: Optional[float] = None
    interval_days: Optional[int] = None

    is_mandatory: bool = True


class MaintenanceProgramItemCreate(MaintenanceProgramItemBase):
    pass


class MaintenanceProgramItemUpdate(BaseModel):
    aircraft_template: Optional[str] = None
    ata_chapter: Optional[str] = None
    task_code: Optional[str] = None
    category: Optional[MaintenanceProgramCategoryEnum] = None
    description: Optional[str] = None

    interval_hours: Optional[float] = None
    interval_cycles: Optional[float] = None
    interval_days: Optional[int] = None

    is_mandatory: Optional[bool] = None


class MaintenanceProgramItemRead(MaintenanceProgramItemBase):
    id: int

    class Config:
        from_attributes = True


class MaintenanceStatusRead(BaseModel):
    """
    Read-only view of maintenance status for a given aircraft/program item.
    """

    id: int
    aircraft_serial_number: str
    program_item_id: int

    last_done_date: Optional[DateType] = None
    last_done_hours: Optional[float] = None
    last_done_cycles: Optional[float] = None

    next_due_date: Optional[DateType] = None
    next_due_hours: Optional[float] = None
    next_due_cycles: Optional[float] = None

    remaining_days: Optional[int] = None
    remaining_hours: Optional[float] = None
    remaining_cycles: Optional[float] = None

    # Optional embedded programme item if you want richer responses
    program_item: Optional[MaintenanceProgramItemRead] = None

    class Config:
        from_attributes = True
