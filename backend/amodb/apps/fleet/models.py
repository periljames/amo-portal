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
"""

from datetime import datetime, date
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    ForeignKey,
    UniqueConstraint,
    Enum as SQLEnum,
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

    # These correspond to model/type structure but are not strict Spec 2000 TEIs.
    # They are retained for UI clarity and internal reporting.
    template = Column(String(50), nullable=True)   # e.g. 'DHC8-315', 'C208B'
    make = Column(String(50), nullable=True)       # e.g. manufacturer name
    model = Column(String(50), nullable=True)      # e.g. '315', '208B'

    # Home base / station (ICAO/IATA)
    home_base = Column(String(10), nullable=True)

    # Owner / operator descriptive text (operator code + name, leasing info, etc.)
    owner = Column(String(255), nullable=True)

    # Operational status – OPEN / CLOSED / STORED, etc.
    status = Column(String(20), nullable=False, default="OPEN")
    is_active = Column(Boolean, nullable=False, default=True)

    # Utilisation snapshot (high-level cumulative hours / cycles)
    # These reflect total aircraft time and cycles as of `last_log_date`.
    # Spec 2000 alignment:
    #   - total_hours  -> Aircraft Cumulative Total Flight Hours
    #   - total_cycles -> Aircraft Cumulative Total Cycles
    last_log_date = Column(Date, nullable=True)
    total_hours = Column(Float, nullable=True)   # cumulative flight hours
    total_cycles = Column(Float, nullable=True)  # cumulative cycles / landings

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

    # All work orders raised against this aircraft (defined in apps.work)
    work_orders = relationship(
        "WorkOrder",
        back_populates="aircraft",
        cascade="all, delete-orphan",
    )

    # All CRS records that reference this aircraft (defined in apps.crs)
    crs_list = relationship(
        "CRS",
        back_populates="aircraft",
    )

    # Component master records (engines, props, APU, etc.)
    components = relationship(
        "AircraftComponent",
        back_populates="aircraft",
        cascade="all, delete-orphan",
    )

    # Detailed utilisation entries (per techlog / date)
    usage_entries = relationship(
        "AircraftUsage",
        back_populates="aircraft",
        cascade="all, delete-orphan",
    )

    # Maintenance programme status records for this aircraft
    maintenance_statuses = relationship(
        "MaintenanceStatus",
        back_populates="aircraft",
        cascade="all, delete-orphan",
    )


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

    Time accumulation fields (installed/current hours/cycles and overhaul
    references) are designed to map cleanly onto Spec 2000 Total Time Text
    (TTM_x_y) when exporting component reliability data:
      - Time Since New (TSN)
      - Time Since Overhaul (TSO)
      - etc.
    """

    __tablename__ = "aircraft_components"

    id = Column(Integer, primary_key=True, index=True)

    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=False,
    )

    # e.g. 'L ENGINE', 'R ENGINE', 'APU', 'PROP LH', 'PROP RH'
    position = Column(String(50), nullable=False)

    # Optional ATA chapter / system reference (e.g. '72', '79', etc.)
    ata = Column(String(20))

    # Core identification
    part_number = Column(String(50))       # PNR
    serial_number = Column(String(50))     # component serial
    description = Column(String(255))

    # Installation reference
    installed_date = Column(Date)
    installed_hours = Column(Float)
    installed_cycles = Column(Float)

    # Current cumulative utilisation
    current_hours = Column(Float)
    current_cycles = Column(Float)

    notes = Column(Text)

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
    operator_code = Column(String(32), nullable=True)       # OPR / reporting operator

    # Units of measure for hours and cycles – normally 'H' and 'C' in Spec 2000
    unit_of_measure_hours = Column(String(8), nullable=False, default="H")
    unit_of_measure_cycles = Column(String(8), nullable=False, default="C")

    # Relationships
    aircraft = relationship("Aircraft", back_populates="components")


# ---------------------------------------------------------------------------
# Aircraft usage – per-techlog utilisation entries
# ---------------------------------------------------------------------------


class AircraftUsage(Base):
    """
    Represents an individual utilisation entry from a techlog / flight.

    For each aircraft, this captures:
    - date
    - techlog number
    - block hours (time flown)
    - cycles (takeoff/landing)

    plus an optional snapshot of totals after the flight.

    Spec 2000 alignment:

    These records are the raw per-flight utilisation that can be aggregated
    to:
      - Aircraft Monthly Total Flight Hours
      - Aircraft Monthly Total Cycles
      - Aircraft Cumulative Total Flight Hours
      - Aircraft Cumulative Total Cycles

    as required to build Aircraft Hours and Landings Records (Record Type 36)
    for external exchange.
    """

    __tablename__ = "aircraft_usage"
    __table_args__ = (
        UniqueConstraint(
            "aircraft_serial_number",
            "date",
            "techlog_no",
            name="uq_aircraft_usage_aircraft_date_techlog",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    date = Column(Date, nullable=False, index=True)
    techlog_no = Column(String(64), nullable=False)
    station = Column(String(16), nullable=True)  # ICAO/IATA/base code

    block_hours = Column(Float, nullable=False)
    cycles = Column(Float, nullable=False)

    # Snapshot / denormalised totals AFTER this entry
    # These can be used directly when calculating Spec 2000 cumulative
    # hours/cycles for the aircraft at the reporting date.
    ttaf_after = Column(Float, nullable=True)    # Total Time Airframe
    tca_after = Column(Float, nullable=True)     # Total Cycles Airframe
    ttesn_after = Column(Float, nullable=True)   # Total Time Engine Since New
    tcesn_after = Column(Float, nullable=True)   # Total Cycles Engine Since New
    ttsoh_after = Column(Float, nullable=True)   # Time Since Overhaul (relevant comp)

    remarks = Column(Text, nullable=True)

    # Audit
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    aircraft = relationship("Aircraft", back_populates="usage_entries")


# ---------------------------------------------------------------------------
# Maintenance Programme & Status
# ---------------------------------------------------------------------------


class MaintenanceProgramCategoryEnum(str, Enum):
    """
    High-level category for maintenance programme items.

    Not directly defined in Spec 2000, but aligned with common airline
    maintenance planning practice and ATA chapters:

    - AIRFRAME: airframe and systems (ATA 21–57).
    - ENGINE: engine-related tasks.
    - PROP: propeller.
    - AD: Airworthiness Directive.
    - SB: Service Bulletin.
    - HT: Hard Time / life-limited items.
    - OTHER: anything not fitting the above buckets.
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

    Example:
      - aircraft_template: aircraft model / type (e.g. 'C208B')
      - ata_chapter: '05-21'
      - task_code: manufacturer or internal task identifier
      - category: AIRFRAME / ENGINE / PROP / AD / SB / HT / OTHER

    The ATA chapter links naturally to ATA iSpec 2200 / IPC structures
    and to Spec 2000 provisioning data by ATA/system code.
    """

    __tablename__ = "maintenance_program_items"

    id = Column(Integer, primary_key=True, index=True)

    aircraft_template = Column(String(50), nullable=False, index=True)
    ata_chapter = Column(String(20), nullable=False, index=True)
    task_code = Column(String(64), nullable=False, index=True)

    category = Column(
        SQLEnum(MaintenanceProgramCategoryEnum, name="maintenance_program_category"),
        nullable=False,
        default=MaintenanceProgramCategoryEnum.AIRFRAME,
    )

    description = Column(Text, nullable=False)

    # Intervals (can be used singly or in combination)
    interval_hours = Column(Float, nullable=True)
    interval_cycles = Column(Float, nullable=True)
    interval_days = Column(Integer, nullable=True)

    is_mandatory = Column(Boolean, nullable=False, default=True)

    statuses = relationship(
        "MaintenanceStatus",
        back_populates="program_item",
        cascade="all, delete-orphan",
    )


class MaintenanceStatus(Base):
    """
    Aircraft-level status for each maintenance programme item.

    Tracks:
    - last done (date / hours / cycles)
    - next due (date / hours / cycles)
    - remaining (days / hours / cycles)

    These fields can be used to drive both internal planning (check packs,
    work orders) and external reporting if you ever decide to encode
    maintenance status into Spec 2000-compatible exchange messages
    or reliability data.
    """

    __tablename__ = "maintenance_statuses"
    __table_args__ = (
        UniqueConstraint(
            "aircraft_serial_number",
            "program_item_id",
            name="uq_maintenance_status_aircraft_program_item",
        ),
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
    next_due_date = Column(Date, nullable=True)
    next_due_hours = Column(Float, nullable=True)
    next_due_cycles = Column(Float, nullable=True)

    # Denormalised / remaining (computed by planning logic)
    remaining_days = Column(Integer, nullable=True)
    remaining_hours = Column(Float, nullable=True)
    remaining_cycles = Column(Float, nullable=True)

    program_item = relationship("MaintenanceProgramItem", back_populates="statuses")
    aircraft = relationship("Aircraft", back_populates="maintenance_statuses")
