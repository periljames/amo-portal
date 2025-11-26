# backend/amodb/apps/fleet/models.py

"""
Fleet data models (aircraft, components, utilisation, maintenance programme).

Scope of this app:
- Aircraft master data and configuration.
- Major installed components (engines, propellers, APU, etc.).
- Aircraft utilisation entries (per techlog / flight).
- Maintenance programme template items and aircraft-level status.

Reliability analysis and event logging will be handled in the dedicated
`apps.reliability` module, not here.
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


class Aircraft(Base):
    """
    Master record for each aircraft in the fleet.

    Naming is aligned with ATA Spec 2000 concepts:
    - `serial_number` represents the aircraft identification (AIN).
    - `registration` holds the aircraft registration (REG).
    - `template` / `make` / `model` describe the aircraft model / variant.
    """

    __tablename__ = "aircraft"

    # Primary key = aircraft identification (AIN-style internal ID)
    serial_number = Column(String(50), primary_key=True, index=True)

    # Registration and configuration
    registration = Column(String(20), unique=True, nullable=False)
    template = Column(String(50), nullable=True)   # e.g. 'DHC8-315', 'C208B'
    make = Column(String(50), nullable=True)       # e.g. manufacturer name
    model = Column(String(50), nullable=True)      # e.g. '315', '208B'
    home_base = Column(String(10), nullable=True)  # e.g. ICAO/IATA station
    owner = Column(String(255), nullable=True)     # operator / owner code + name

    status = Column(String(20), nullable=False, default="OPEN")  # OPEN / CLOSED etc
    is_active = Column(Boolean, nullable=False, default=True)

    # Utilisation snapshot (high-level cumulative hours / cycles)
    # These reflect total aircraft time and cycles as of `last_log_date`.
    last_log_date = Column(Date, nullable=True)
    total_hours = Column(Float, nullable=True)     # cumulative flight hours
    total_cycles = Column(Float, nullable=True)    # cumulative cycles / landings

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


class AircraftComponent(Base):
    """
    Major component positions for each aircraft:
    engines, propellers, APU, etc.

    Conceptually aligned with ATA Spec 2000 / LRU-style data:
    - `part_number`, `serial_number` for identification.
    - `manufacturer_code`, `operator_code` for standardised coding.
    - hours / cycles use standard units of measure.
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

    ata = Column(String(20))               # optional ATA chapter / system reference
    part_number = Column(String(50))
    serial_number = Column(String(50))
    description = Column(String(255))

    installed_date = Column(Date)
    installed_hours = Column(Float)
    installed_cycles = Column(Float)

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
    manufacturer_code = Column(String(32), nullable=True)
    operator_code = Column(String(32), nullable=True)
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
    plus optional snapshot of totals after the flight.
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
