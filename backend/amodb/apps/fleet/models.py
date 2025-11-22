# backend/amodb/apps/fleet/models.py
from datetime import datetime

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
)
from sqlalchemy.orm import relationship

from ...database import Base


class Aircraft(Base):
    """
    Master record for each aircraft in the fleet.

    serial_number is the primary key so it matches your existing
    aircraft identity in WinAir (e.g. 574, 510, 331).
    """

    __tablename__ = "aircraft"

    # Primary key = aircraft serial number (e.g. 574, 510, 331)
    serial_number = Column(String(50), primary_key=True, index=True)

    # Registration and configuration
    registration = Column(String(20), unique=True, nullable=False)
    template = Column(String(50), nullable=True)   # e.g. 'DASH-8', 'C208B'
    make = Column(String(50), nullable=True)       # e.g. 'DASH-8'
    model = Column(String(50), nullable=True)      # e.g. '315', '202', '208B'
    home_base = Column(String(10), nullable=True)  # e.g. 'HKW', 'HKNW'
    owner = Column(String(255), nullable=True)     # e.g. 'SAFA01 - SAFARILINK AVIATION LTD'

    status = Column(String(20), nullable=False, default="OPEN")  # OPEN / CLOSED etc
    is_active = Column(Boolean, nullable=False, default=True)

    # Utilisation snapshot (from WinAir or the PDFs)
    last_log_date = Column(Date, nullable=True)
    total_hours = Column(Float, nullable=True)     # Current Values: Hours
    total_cycles = Column(Float, nullable=True)    # Current Values: Cycles

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

    # All work orders raised against this aircraft
    work_orders = relationship(
        "WorkOrder",
        back_populates="aircraft",
        cascade="all, delete-orphan",
    )

    # All CRS records that reference this aircraft
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


class AircraftComponent(Base):
    """
    Major component positions for each aircraft:
    engines, props, APU, etc.

    This is intentionally generic so we can feed it
    from WinAir setup PDFs/Excels.
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

    ata = Column(String(20))               # optional ATA reference
    part_number = Column(String(50))
    serial_number = Column(String(50))
    description = Column(String(255))

    installed_date = Column(Date)
    installed_hours = Column(Float)
    installed_cycles = Column(Float)

    current_hours = Column(Float)
    current_cycles = Column(Float)

    notes = Column(Text)

    aircraft = relationship("Aircraft", back_populates="components")
