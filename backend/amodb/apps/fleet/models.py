"""
Fleet data models (aircraft, components, utilisation, maintenance programme).

Scope of this app:
- Aircraft master data and configuration.
- Major installed components (engines, propellers, APU, etc.).
- Aircraft utilisation entries (per techlog / flight).
- Maintenance programme template items and aircraft-level status.

Reliability analysis and event logging will be handled in the dedicated
`apps.reliability` module, not here.

Key ATA Spec 2000 alignments:

- Aircraft master aligned with the Aircraft Hours and Landings Record
  (Record Type 36): Aircraft Identification Number (AIN), Aircraft
  Registration Number, Aircraft Model Code, Operator Code, Supplier Code,
  Company Name, Operator Internal Identifier, cumulative hours and cycles.

- Components aligned with Spec 2000 equipment data elements (PNR, MFR,
  operator code, total time text TTM_x_y, units of measure).

This file is intentionally conservative: we add the Spec 2000-aligned
fields without breaking existing API field names so that routers and
schemas can be migrated incrementally.

Long-run safeguards added in this revision:
- Indexes for common query paths (fleet dashboards, planning, reporting).
- Uniqueness constraints to prevent silent duplication (component positions,
  programme item identity).
- Removed dangerous delete-orphan cascade on WorkOrders (editing the list
  should never delete work orders).
- Relationship loading defaults to avoid join row-explosion in large datasets.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Enum as SQLEnum,
    JSON,
)
from sqlalchemy.orm import relationship

from ...database import Base


# ---------------------------------------------------------------------------
# AIRCRAFT MASTER (Spec 2000-aligned)
# ---------------------------------------------------------------------------


class Aircraft(Base):
    """
    Master record for each aircraft in the fleet.

    Spec 2000 mapping (primarily Record Type 36 - Aircraft Hours and Landings):

    - serial_number:
        Operator-side Aircraft Identification Number
        (AIN – aircraft identification number).

    - registration:
        Aircraft Registration Number (REG / ACN – registration mark).

    - aircraft_model_code:
        Aircraft Model Code (AMC) – the manufacturer's or type/model code.

    - operator_code:
        Operator Code (OPR) – 3-character airline/operator designator or
        'ZZZZZ' when no standard code is available.

    - supplier_code:
        Supplier Code (SPL) – for data exchanges where the airframer or OEM
        provides hours/landings statistics or other fleet records.

    - company_name:
        Company / Operator Name (WHO / Reporting Organization Name).

    - internal_aircraft_identifier:
        Operator Aircraft Internal Identifier – internal tail/ID used by the
        operator, distinct from regulatory registration if desired.

    - total_hours / total_cycles:
        Aircraft Cumulative Total Flight Hours / Cycles at `last_log_date`
        (aligned with the cumulative totals referenced in Record Type 36).
    """

    __tablename__ = "aircraft"

    __table_args__ = (
        # Typical filters in ops/planning UIs
        Index("ix_aircraft_model_code", "aircraft_model_code"),
        Index("ix_aircraft_operator_code", "operator_code"),
        Index("ix_aircraft_status_active", "status", "is_active"),
        Index("ix_aircraft_last_log_date", "last_log_date"),
        # Prevent negative totals creeping in
        CheckConstraint("total_hours IS NULL OR total_hours >= 0", name="ck_aircraft_total_hours_nonneg"),
        CheckConstraint("total_cycles IS NULL OR total_cycles >= 0", name="ck_aircraft_total_cycles_nonneg"),
    )

    # Primary key = aircraft identification (AIN-style internal ID)
    # Spec 2000: Aircraft Identification Number (AIN)
    serial_number = Column(String(50), primary_key=True, index=True)

    # --- Spec 2000 Identification / Ownership ---

    # Aircraft Registration Number (ACN/REG)
    registration = Column(String(20), unique=True, nullable=False)

    # Aircraft Model Code (AMC) – can mirror type/series (e.g. 'DHC8-315')
    aircraft_model_code = Column(String(32), nullable=True, index=True)

    # Operator Code (OPR) – typically 3 characters, may be 'ZZZZZ'
    operator_code = Column(String(5), nullable=True, index=True)

    # Supplier Code (SPL) – OEM / data supplier code when applicable
    supplier_code = Column(String(5), nullable=True)

    # Company / Operator Name (WHO / Reporting Organization Name)
    company_name = Column(String(255), nullable=True)

    # Operator Aircraft Internal Identifier (separate from AIN/registration)
    internal_aircraft_identifier = Column(String(50), nullable=True)

    # --- Local convenience fields (kept for app usage, mapped to Spec 2000) ---

    template = Column(String(50), nullable=True)   # e.g. 'DHC8-315', 'C208B'
    make = Column(String(50), nullable=True)       # e.g. manufacturer name
    model = Column(String(50), nullable=True)      # e.g. '315', '208B'

    # Home base / station (ICAO/IATA)
    home_base = Column(String(10), nullable=True)

    # Owner / operator descriptive text (operator code + name, leasing info, etc.)
    owner = Column(String(255), nullable=True)

    # Operational status – OPEN / CLOSED / STORED, etc.
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    # Utilisation snapshot (high-level cumulative hours / cycles)
    last_log_date = Column(Date, nullable=True, index=True)
    total_hours = Column(Float, nullable=True)   # cumulative flight hours
    total_cycles = Column(Float, nullable=True)  # cumulative cycles / landings
    verification_status = Column(
        String(32),
        nullable=False,
        default="UNVERIFIED",
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

    # All work orders raised against this aircraft (defined in apps.work)
    #
    # IMPORTANT:
    # Do NOT use delete-orphan here. Removing a WorkOrder from the relationship
    # list should never delete it. That is a long-run "silent data loss" risk.
    work_orders = relationship(
        "WorkOrder",
        back_populates="aircraft",
        lazy="selectin",
        passive_deletes=True,
        cascade="save-update, merge",
    )

    # All CRS records that reference this aircraft (defined in apps.crs)
    crs_list = relationship(
        "CRS",
        back_populates="aircraft",
        lazy="selectin",
        passive_deletes=True,
    )

    # Component master records (engines, props, APU, etc.)
    components = relationship(
        "AircraftComponent",
        back_populates="aircraft",
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Detailed utilisation entries (per techlog / date)
    usage_entries = relationship(
        "AircraftUsage",
        back_populates="aircraft",
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Maintenance programme status records for this aircraft
    maintenance_statuses = relationship(
        "MaintenanceStatus",
        back_populates="aircraft",
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Aircraft serial_number={self.serial_number} registration={self.registration}>"


# ---------------------------------------------------------------------------
# COMPONENT MASTER (engines, props, APU, etc.)
# ---------------------------------------------------------------------------


class AircraftComponent(Base):
    """
    Major component positions for each aircraft:
    engines, propellers, APU, etc.

    Spec 2000 alignment (component/equipment master):

    - part_number:
        Part Number (PNR).

    - serial_number:
        Manufacturer or operator-unique serial number for the component.

    - manufacturer_code:
        Manufacturer Code (MFR) – 5-character manufacturer identifier.

    - operator_code:
        Operator Code (OPR) – who is operating / reporting the component.

    - unit_of_measure_hours / unit_of_measure_cycles:
        Units of measure (UNT) consistent with Spec 2000 usage:
        typically 'H' for hours, 'C' for cycles.
    """

    __tablename__ = "aircraft_components"

    __table_args__ = (
        # One component position per aircraft (prevents duplicate "L ENGINE" entries)
        UniqueConstraint("aircraft_serial_number", "position", name="uq_aircraft_component_aircraft_position"),
        Index("ix_aircraft_components_aircraft_position", "aircraft_serial_number", "position"),
        Index("ix_aircraft_components_pn_sn", "part_number", "serial_number"),
        Index("ix_aircraft_components_ata", "ata"),
        CheckConstraint("installed_hours IS NULL OR installed_hours >= 0", name="ck_aircraft_comp_installed_hours_nonneg"),
        CheckConstraint("installed_cycles IS NULL OR installed_cycles >= 0", name="ck_aircraft_comp_installed_cycles_nonneg"),
        CheckConstraint("current_hours IS NULL OR current_hours >= 0", name="ck_aircraft_comp_current_hours_nonneg"),
        CheckConstraint("current_cycles IS NULL OR current_cycles >= 0", name="ck_aircraft_comp_current_cycles_nonneg"),
    )

    id = Column(Integer, primary_key=True, index=True)

    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # e.g. 'L ENGINE', 'R ENGINE', 'APU', 'PROP LH', 'PROP RH'
    position = Column(String(50), nullable=False, index=True)

    # Optional ATA chapter / system reference (e.g. '72', '79', etc.)
    ata = Column(String(20), nullable=True, index=True)

    # Core identification
    part_number = Column(String(50), nullable=True, index=True)       # PNR
    serial_number = Column(String(50), nullable=True, index=True)     # component serial
    description = Column(String(255), nullable=True)

    # Installation reference
    installed_date = Column(Date, nullable=True)
    installed_hours = Column(Float, nullable=True)
    installed_cycles = Column(Float, nullable=True)

    # Current cumulative utilisation
    current_hours = Column(Float, nullable=True)
    current_cycles = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)
    verification_status = Column(
        String(32),
        nullable=False,
        default="UNVERIFIED",
        index=True,
    )

    # ------------------------------------------------------------------
    # Life limits and reliability standardisation
    # ------------------------------------------------------------------

    # Time Between Overhaul (TBO)
    tbo_hours = Column(Float, nullable=True)
    tbo_cycles = Column(Float, nullable=True)
    tbo_calendar_months = Column(Integer, nullable=True)

    # Hot Section Inspection (HSI) or equivalent interval
    hsi_hours = Column(Float, nullable=True)
    hsi_cycles = Column(Float, nullable=True)
    hsi_calendar_months = Column(Integer, nullable=True)

    # Overhaul reference values at last shop visit
    last_overhaul_date = Column(Date, nullable=True)
    last_overhaul_hours = Column(Float, nullable=True)
    last_overhaul_cycles = Column(Float, nullable=True)

    # Standardisation for reliability coding
    manufacturer_code = Column(String(32), nullable=True)  # MFR
    operator_code = Column(String(32), nullable=True)      # OPR / reporting operator

    # Units of measure for hours and cycles – normally 'H' and 'C' in Spec 2000
    unit_of_measure_hours = Column(String(8), nullable=False, default="H")
    unit_of_measure_cycles = Column(String(8), nullable=False, default="C")

    # Relationships
    aircraft = relationship("Aircraft", back_populates="components", lazy="joined")

    def __repr__(self) -> str:
        return f"<AircraftComponent id={self.id} aircraft={self.aircraft_serial_number} position={self.position}>"


# ---------------------------------------------------------------------------
# Aircraft usage – per-techlog utilisation entries
# ---------------------------------------------------------------------------


class AircraftUsage(Base):
    """
    Represents an individual utilisation entry from a techlog / flight.
    """

    __tablename__ = "aircraft_usage"

    __table_args__ = (
        UniqueConstraint(
            "aircraft_serial_number",
            "date",
            "techlog_no",
            name="uq_aircraft_usage_aircraft_date_techlog",
        ),
        Index("ix_aircraft_usage_aircraft_date", "aircraft_serial_number", "date"),
        Index("ix_aircraft_usage_techlog_no", "techlog_no"),
        CheckConstraint("block_hours >= 0", name="ck_aircraft_usage_block_hours_nonneg"),
        CheckConstraint("cycles >= 0", name="ck_aircraft_usage_cycles_nonneg"),
    )

    id = Column(Integer, primary_key=True, index=True)

    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    date = Column(Date, nullable=False, index=True)
    techlog_no = Column(String(64), nullable=False, index=True)
    station = Column(String(16), nullable=True)  # ICAO/IATA/base code

    block_hours = Column(Float, nullable=False)
    cycles = Column(Float, nullable=False)

    # Snapshot / denormalised totals AFTER this entry
    ttaf_after = Column(Float, nullable=True)    # Total Time Airframe
    tca_after = Column(Float, nullable=True)     # Total Cycles Airframe
    ttesn_after = Column(Float, nullable=True)   # Total Time Engine Since New
    tcesn_after = Column(Float, nullable=True)   # Total Cycles Engine Since New
    ttsoh_after = Column(Float, nullable=True)   # Time Since Overhaul (relevant comp)
    ttshsi_after = Column(Float, nullable=True)  # Time Since HSI
    tcsoh_after = Column(Float, nullable=True)   # Cycles Since Overhaul
    pttsn_after = Column(Float, nullable=True)   # Prop Total Time Since New
    pttso_after = Column(Float, nullable=True)   # Prop Time Since Overhaul
    tscoa_after = Column(Float, nullable=True)   # Time Since Change of Angle (prop)

    hours_to_mx = Column(Float, nullable=True)
    days_to_mx = Column(Integer, nullable=True)

    remarks = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    verification_status = Column(
        String(32),
        nullable=False,
        default="UNVERIFIED",
        index=True,
    )

    # Audit
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    aircraft = relationship("Aircraft", back_populates="usage_entries", lazy="joined")

    def __repr__(self) -> str:
        return f"<AircraftUsage id={self.id} aircraft={self.aircraft_serial_number} date={self.date} techlog={self.techlog_no}>"


# ---------------------------------------------------------------------------
# Maintenance Programme & Status
# ---------------------------------------------------------------------------


class MaintenanceProgramCategoryEnum(str, Enum):
    """
    High-level category for maintenance programme items.

    Not directly defined in Spec 2000, but aligned with common airline
    maintenance planning practice and ATA chapters.
    """

    AIRFRAME = "AIRFRAME"
    ENGINE = "ENGINE"
    PROP = "PROP"
    AD = "AD"
    SB = "SB"
    HT = "HT"
    OTHER = "OTHER"


class MaintenanceProgramItem(Base):
    """
    Template-level definition of a maintenance task for a given aircraft type.
    """

    __tablename__ = "maintenance_program_items"

    __table_args__ = (
        # Prevent accidental duplicates of the same task identity
        UniqueConstraint(
            "aircraft_template",
            "ata_chapter",
            "task_code",
            name="uq_maintenance_program_item_template_ata_task",
        ),
        Index("ix_mpi_template_ata", "aircraft_template", "ata_chapter"),
        Index("ix_mpi_task_code", "task_code"),
        Index("ix_mpi_category", "category"),
        CheckConstraint("interval_hours IS NULL OR interval_hours >= 0", name="ck_mpi_interval_hours_nonneg"),
        CheckConstraint("interval_cycles IS NULL OR interval_cycles >= 0", name="ck_mpi_interval_cycles_nonneg"),
        CheckConstraint("interval_days IS NULL OR interval_days >= 0", name="ck_mpi_interval_days_nonneg"),
    )

    id = Column(Integer, primary_key=True, index=True)

    aircraft_template = Column(String(50), nullable=False, index=True)
    ata_chapter = Column(String(20), nullable=False, index=True)
    task_code = Column(String(64), nullable=False, index=True)

    # NOTE:
    # native_enum=False prevents Postgres enum-type lifecycle issues (Alembic).
    # It stores values as VARCHAR + CHECK constraint instead.
    category = Column(
        SQLEnum(
            MaintenanceProgramCategoryEnum,
            name="maintenance_program_category",
            native_enum=False,
        ),
        nullable=False,
        default=MaintenanceProgramCategoryEnum.AIRFRAME,
    )

    description = Column(Text, nullable=False)

    # Intervals (can be used singly or in combination)
    interval_hours = Column(Float, nullable=True)
    interval_cycles = Column(Float, nullable=True)
    interval_days = Column(Integer, nullable=True)

    is_mandatory = Column(Boolean, nullable=False, default=True, index=True)

    statuses = relationship(
        "MaintenanceStatus",
        back_populates="program_item",
        cascade="all, delete-orphan",
        lazy="selectin",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<MaintenanceProgramItem id={self.id} template={self.aircraft_template} task_code={self.task_code}>"


class MaintenanceStatus(Base):
    """
    Aircraft-level status for each maintenance programme item.
    """

    __tablename__ = "maintenance_statuses"

    __table_args__ = (
        UniqueConstraint(
            "aircraft_serial_number",
            "program_item_id",
            name="uq_maintenance_status_aircraft_program_item",
        ),
        Index("ix_maintenance_status_aircraft_due_date", "aircraft_serial_number", "next_due_date"),
        Index("ix_maintenance_status_program_item", "program_item_id"),
        CheckConstraint("remaining_days IS NULL OR remaining_days >= 0", name="ck_mstatus_remaining_days_nonneg"),
        CheckConstraint("remaining_hours IS NULL OR remaining_hours >= 0", name="ck_mstatus_remaining_hours_nonneg"),
        CheckConstraint("remaining_cycles IS NULL OR remaining_cycles >= 0", name="ck_mstatus_remaining_cycles_nonneg"),
    )

    id = Column(Integer, primary_key=True, index=True)

    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    program_item_id = Column(
        Integer,
        ForeignKey("maintenance_program_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Last done
    last_done_date = Column(Date, nullable=True)
    last_done_hours = Column(Float, nullable=True)
    last_done_cycles = Column(Float, nullable=True)

    # Next due
    next_due_date = Column(Date, nullable=True, index=True)
    next_due_hours = Column(Float, nullable=True)
    next_due_cycles = Column(Float, nullable=True)

    # Denormalised / remaining (computed by planning logic)
    remaining_days = Column(Integer, nullable=True)
    remaining_hours = Column(Float, nullable=True)
    remaining_cycles = Column(Float, nullable=True)

    program_item = relationship("MaintenanceProgramItem", back_populates="statuses", lazy="joined")
    aircraft = relationship("Aircraft", back_populates="maintenance_statuses", lazy="joined")

    def __repr__(self) -> str:
        return f"<MaintenanceStatus id={self.id} aircraft={self.aircraft_serial_number} program_item_id={self.program_item_id}>"


# ---------------------------------------------------------------------------
# Aircraft Import Templates
# ---------------------------------------------------------------------------


class AircraftImportTemplate(Base):
    """
    Saved templates for aircraft import column mappings and defaults.
    """

    __tablename__ = "aircraft_import_templates"
    __table_args__ = (
        UniqueConstraint(
            "template_type",
            "name",
            name="uq_aircraft_import_template_type_name",
        ),
        Index("ix_aircraft_import_template_aircraft_template", "aircraft_template"),
        Index("ix_aircraft_import_template_model_code", "model_code"),
        Index("ix_aircraft_import_template_operator_code", "operator_code"),
        Index("ix_aircraft_import_template_type", "template_type"),
    )

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(120), nullable=False, index=True)
    template_type = Column(String(32), nullable=False, index=True, default="aircraft")
    aircraft_template = Column(String(50), nullable=True)
    model_code = Column(String(32), nullable=True)
    operator_code = Column(String(5), nullable=True)

    column_mapping = Column(JSON, nullable=True)
    default_values = Column(JSON, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<AircraftImportTemplate id={self.id} name={self.name}>"


# ---------------------------------------------------------------------------
# Aircraft Import Preview Staging
# ---------------------------------------------------------------------------


class AircraftImportPreviewSession(Base):
    """
    Preview session metadata for bulk import staging.
    """

    __tablename__ = "aircraft_import_preview_sessions"
    __table_args__ = (
        Index("ix_aircraft_import_preview_session_created", "created_at"),
        Index("ix_aircraft_import_preview_session_type", "import_type"),
    )

    preview_id = Column(String(36), primary_key=True, index=True)
    import_type = Column(String(32), nullable=False, index=True, default="aircraft")
    total_rows = Column(Integer, nullable=False, default=0)
    column_mapping = Column(JSON, nullable=True)
    summary = Column(JSON, nullable=True)
    ocr_info = Column(JSON, nullable=True)
    formula_discrepancies = Column(JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class AircraftImportPreviewRow(Base):
    """
    Staged rows for bulk import preview.
    """

    __tablename__ = "aircraft_import_preview_rows"
    __table_args__ = (
        Index("ix_aircraft_import_preview_row_preview", "preview_id", "row_number"),
        Index("ix_aircraft_import_preview_row_preview_action", "preview_id", "action"),
    )

    id = Column(Integer, primary_key=True, index=True)
    preview_id = Column(
        String(36),
        ForeignKey("aircraft_import_preview_sessions.preview_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    row_number = Column(Integer, nullable=False, index=True)
    data = Column(JSON, nullable=False)
    errors = Column(JSON, nullable=False, default=list)
    warnings = Column(JSON, nullable=False, default=list)
    action = Column(String(16), nullable=False)
    suggested_template = Column(JSON, nullable=True)
    formula_proposals = Column(JSON, nullable=True)


# ---------------------------------------------------------------------------
# Aircraft Import Reconciliation
# ---------------------------------------------------------------------------


class ImportSnapshot(Base):
    """
    Captures the full diff map for an import batch, enabling undo/redo.
    """

    __tablename__ = "aircraft_import_snapshots"
    __table_args__ = (
        Index("ix_import_snapshot_batch", "batch_id", "created_at"),
        Index("ix_import_snapshot_type", "import_type", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String(36), nullable=False, index=True)
    import_type = Column(String(32), nullable=False, index=True, default="aircraft")
    diff_map = Column(JSON, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<ImportSnapshot id={self.id} batch_id={self.batch_id}>"


class ImportReconciliationLog(Base):
    """
    Audit trail of per-cell reconciliation for import confirms.
    """

    __tablename__ = "aircraft_import_reconciliation_logs"
    __table_args__ = (
        Index("ix_import_recon_batch", "batch_id", "created_at"),
        Index("ix_import_recon_snapshot", "snapshot_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    snapshot_id = Column(
        Integer,
        ForeignKey("aircraft_import_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    batch_id = Column(String(36), nullable=False, index=True)
    import_type = Column(String(32), nullable=False, index=True, default="aircraft")
    row_number = Column(Integer, nullable=True)
    field_name = Column(String(64), nullable=False, index=True)
    aircraft_serial_number = Column(String(50), nullable=True, index=True)
    original_value = Column(JSON, nullable=True)
    proposed_value = Column(JSON, nullable=True)
    final_value = Column(JSON, nullable=True)
    decision = Column(String(32), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ImportReconciliationLog id={self.id} batch_id={self.batch_id} "
            f"field={self.field_name}>"
        )
