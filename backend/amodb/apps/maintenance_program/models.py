# backend/amodb/apps/maintenance_program/models.py
#
# ORM models for the maintenance program module:
# - AmpProgramItem        : template-level AMP tasks (generic, by template_code).
# - AmpAircraftProgramItem: per-aircraft instance of a program item with
#                           utilisation / last-done / next-due tracking.

from __future__ import annotations

from datetime import datetime, date
from enum import Enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Text,
    Date,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship

from ...database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProgramItemStatusEnum(str, Enum):
    """Lifecycle status of a template maintenance-program item."""

    ACTIVE = "ACTIVE"        # in use
    SUSPENDED = "SUSPENDED"  # temporarily not used
    DELETED = "DELETED"      # logically deleted / retired


class AircraftProgramStatusEnum(str, Enum):
    """Status of a per-aircraft program item from a scheduling perspective."""

    PLANNED = "PLANNED"      # configured, not yet near due
    DUE_SOON = "DUE_SOON"    # approaching limits (hours/cycles/days)
    OVERDUE = "OVERDUE"      # beyond one or more limits
    COMPLETED = "COMPLETED"  # closed out and updated
    SUSPENDED = "SUSPENDED"  # disabled because master item inactive / aircraft parked


# ---------------------------------------------------------------------------
# AmpProgramItem – template AMP task definition
# ---------------------------------------------------------------------------


class AmpProgramItem(Base):
    """
    Template-level maintenance program item (AMP / MRB task).

    This is generic per template / fleet type (e.g. "DHC6-300 AMP v1"),
    not tied to a specific aircraft. Per-aircraft instances live in
    AmpAircraftProgramItem.
    """

    __tablename__ = "maintenance_program_items"
    # Guard against duplicate Table() definitions with the same name
    # in this metadata (e.g. legacy Table(...) plus this ORM class).
    __table_args__ = {"extend_existing": True}

    id: int = Column(Integer, primary_key=True, index=True)

    # Logical template / program identifier (e.g. "DHC6-300-AMP-V1")
    template_code: str = Column(String(50), nullable=False, index=True)

    # Technical identification
    ata_chapter: str | None = Column(String(20), nullable=True, index=True)
    task_number: str | None = Column(String(64), nullable=True, index=True)
    task_code: str | None = Column(String(64), nullable=True, index=True)

    title: str = Column(String(255), nullable=False)
    description: str | None = Column(Text, nullable=True)

    # Intervals (simple FH/FC/calendar model for now)
    interval_hours: float | None = Column(Float, nullable=True)
    interval_cycles: float | None = Column(Float, nullable=True)
    interval_days: int | None = Column(Integer, nullable=True)

    # Thresholds (e.g. first compliance at X FH / FC / days)
    threshold_hours: float | None = Column(Float, nullable=True)
    threshold_cycles: float | None = Column(Float, nullable=True)
    threshold_days: int | None = Column(Integer, nullable=True)

    # Default planning / access data
    default_zone: str | None = Column(String(32), nullable=True)
    notes: str | None = Column(Text, nullable=True)

    status: ProgramItemStatusEnum = Column(
        SQLEnum(ProgramItemStatusEnum, name="program_item_status_enum"),
        nullable=False,
        default=ProgramItemStatusEnum.ACTIVE,
    )

    # Audit
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    created_by_user_id: int | None = Column(Integer, nullable=True)
    updated_by_user_id: int | None = Column(Integer, nullable=True)

    # Relationships
    aircraft_items = relationship(
        "AmpAircraftProgramItem",
        back_populates="program_item",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# AmpAircraftProgramItem – per-aircraft instance + scheduling data
# ---------------------------------------------------------------------------


class AmpAircraftProgramItem(Base):
    """
    Per-aircraft maintenance-program item.

    Links an aircraft to an AmpProgramItem and stores last-done,
    next-due and remaining utilisation / time.
    """

    __tablename__ = "aircraft_program_items"

    id: int = Column(Integer, primary_key=True, index=True)

    aircraft_serial_number: str = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    program_item_id: int = Column(
        Integer,
        ForeignKey("maintenance_program_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional link to a specific component / position
    aircraft_component_id: int | None = Column(
        Integer,
        ForeignKey("aircraft_components.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Optional overrides for this particular aircraft / position
    override_title: str | None = Column(String(255), nullable=True)
    override_task_code: str | None = Column(String(64), nullable=True)

    notes: str | None = Column(Text, nullable=True)

    # Last-done data (aircraft total at time of accomplishment)
    last_done_hours: float | None = Column(Float, nullable=True)
    last_done_cycles: float | None = Column(Float, nullable=True)
    last_done_date: date | None = Column(Date, nullable=True)

    # Next-due values (absolute FH/FC/date)
    next_due_hours: float | None = Column(Float, nullable=True)
    next_due_cycles: float | None = Column(Float, nullable=True)
    next_due_date: date | None = Column(Date, nullable=True)

    # Remaining to limits (derived)
    remaining_hours: float | None = Column(Float, nullable=True)
    remaining_cycles: float | None = Column(Float, nullable=True)
    remaining_days: int | None = Column(Integer, nullable=True)

    status: AircraftProgramStatusEnum = Column(
        SQLEnum(
            AircraftProgramStatusEnum,
            name="aircraft_program_status_enum",
        ),
        nullable=False,
        default=AircraftProgramStatusEnum.PLANNED,
    )

    # Audit
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    created_by_user_id: int | None = Column(Integer, nullable=True)
    updated_by_user_id: int | None = Column(Integer, nullable=True)

    # Relationships
    program_item = relationship(
        "AmpProgramItem",
        back_populates="aircraft_items",
    )

    # Simple navigation helpers; "Aircraft" and "AircraftComponent"
    # live in the fleet app models and will be resolved by name.
    aircraft = relationship("Aircraft")
    component = relationship("AircraftComponent")
