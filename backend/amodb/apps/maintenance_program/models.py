# backend/amodb/apps/maintenance_program/models.py
#
# ORM models for the maintenance program module:
# - AmpProgramItem         : template-level AMP tasks (generic, by template_code).
# - AmpAircraftProgramItem : per-aircraft instance of a program item with
#                            utilisation / last-done / next-due tracking.
#
# This revision hardens the schema for long-run safety:
# - Avoids table-name collisions with other modules by using distinct table names.
# - Adds uniqueness constraints to prevent silent duplication.
# - Adds indexes for common planning queries (by aircraft, due date, status).
# - Uses timezone-aware UTC timestamps.
# - Uses users.id GUID (String(36)) for audit FKs (consistent with accounts app).
# - Uses non-native enums to avoid Postgres enum lifecycle headaches in Alembic.
# - Adds non-negative check constraints for hours/cycles/days fields.

from __future__ import annotations

from datetime import date, datetime, timezone
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
    RETIRED = "RETIRED"      # logically retired (kept for traceability)


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

    NOTE ON TABLE NAMING:
    This model uses a dedicated table name (`amp_program_items`) to avoid
    collisions with similarly named tables/models in other modules.
    """

    __tablename__ = "amp_program_items"

    __table_args__ = (
        # Prevent duplicates for the same template/task identity.
        # (NULL handling: Postgres allows multiple NULLs; that is acceptable.)
        UniqueConstraint("template_code", "task_code", name="uq_amp_program_items_template_task_code"),
        UniqueConstraint("template_code", "task_number", name="uq_amp_program_items_template_task_number"),
        Index("ix_amp_program_items_template_ata", "template_code", "ata_chapter"),
        Index("ix_amp_program_items_template_status", "template_code", "status"),
        Index("ix_amp_program_items_task_code", "task_code"),
        Index("ix_amp_program_items_task_number", "task_number"),
        # Safety checks (avoid negative values)
        CheckConstraint("interval_hours IS NULL OR interval_hours >= 0", name="ck_amp_pi_interval_hours_nonneg"),
        CheckConstraint("interval_cycles IS NULL OR interval_cycles >= 0", name="ck_amp_pi_interval_cycles_nonneg"),
        CheckConstraint("interval_days IS NULL OR interval_days >= 0", name="ck_amp_pi_interval_days_nonneg"),
        CheckConstraint("threshold_hours IS NULL OR threshold_hours >= 0", name="ck_amp_pi_threshold_hours_nonneg"),
        CheckConstraint("threshold_cycles IS NULL OR threshold_cycles >= 0", name="ck_amp_pi_threshold_cycles_nonneg"),
        CheckConstraint("threshold_days IS NULL OR threshold_days >= 0", name="ck_amp_pi_threshold_days_nonneg"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Logical template / program identifier (e.g. "DHC6-300-AMP-V1")
    template_code = Column(String(50), nullable=False, index=True)

    # Technical identification
    ata_chapter = Column(String(20), nullable=True, index=True)
    task_number = Column(String(64), nullable=True, index=True)
    task_code = Column(String(64), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Planning classification (optional)
    default_zone = Column(String(32), nullable=True)
    is_mandatory = Column(Boolean, nullable=False, default=True)

    # Intervals (simple FH/FC/calendar model)
    interval_hours = Column(Float, nullable=True)
    interval_cycles = Column(Float, nullable=True)
    interval_days = Column(Integer, nullable=True)

    # Thresholds (e.g. first compliance at X FH / FC / days)
    threshold_hours = Column(Float, nullable=True)
    threshold_cycles = Column(Float, nullable=True)
    threshold_days = Column(Integer, nullable=True)

    notes = Column(Text, nullable=True)

    # Use non-native enums to avoid Postgres enum-type lifecycle issues (Alembic).
    status = Column(
        SQLEnum(
            ProgramItemStatusEnum,
            name="program_item_status_enum",
            native_enum=False,
        ),
        nullable=False,
        default=ProgramItemStatusEnum.ACTIVE,
        index=True,
    )

    # Audit (accounts.users.id is a GUID string)
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

    # Relationships
    aircraft_items = relationship(
        "AmpAircraftProgramItem",
        back_populates="program_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<AmpProgramItem id={self.id} template_code={self.template_code} task_code={self.task_code}>"


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

    __table_args__ = (
        # Prevent duplicates for the same aircraft + program item + component position link.
        UniqueConstraint(
            "aircraft_serial_number",
            "program_item_id",
            "aircraft_component_id",
            name="uq_aircraft_program_items_aircraft_program_component",
        ),
        Index("ix_aircraft_program_items_aircraft_status", "aircraft_serial_number", "status"),
        Index("ix_aircraft_program_items_due_date", "aircraft_serial_number", "next_due_date"),
        Index("ix_aircraft_program_items_program_item", "program_item_id"),
        CheckConstraint("last_done_hours IS NULL OR last_done_hours >= 0", name="ck_api_last_done_hours_nonneg"),
        CheckConstraint("last_done_cycles IS NULL OR last_done_cycles >= 0", name="ck_api_last_done_cycles_nonneg"),
        CheckConstraint("next_due_hours IS NULL OR next_due_hours >= 0", name="ck_api_next_due_hours_nonneg"),
        CheckConstraint("next_due_cycles IS NULL OR next_due_cycles >= 0", name="ck_api_next_due_cycles_nonneg"),
        CheckConstraint("remaining_hours IS NULL OR remaining_hours >= 0", name="ck_api_remaining_hours_nonneg"),
        CheckConstraint("remaining_cycles IS NULL OR remaining_cycles >= 0", name="ck_api_remaining_cycles_nonneg"),
        CheckConstraint("remaining_days IS NULL OR remaining_days >= 0", name="ck_api_remaining_days_nonneg"),
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
        ForeignKey("amp_program_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional link to a specific component / position
    aircraft_component_id = Column(
        Integer,
        ForeignKey("aircraft_components.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Optional overrides for this particular aircraft / position
    override_title = Column(String(255), nullable=True)
    override_task_code = Column(String(64), nullable=True)

    notes = Column(Text, nullable=True)

    # Last-done data (aircraft total at time of accomplishment)
    last_done_hours = Column(Float, nullable=True)
    last_done_cycles = Column(Float, nullable=True)
    last_done_date = Column(Date, nullable=True)

    # Next-due values (absolute FH/FC/date)
    next_due_hours = Column(Float, nullable=True)
    next_due_cycles = Column(Float, nullable=True)
    next_due_date = Column(Date, nullable=True, index=True)

    # Remaining to limits (derived)
    remaining_hours = Column(Float, nullable=True)
    remaining_cycles = Column(Float, nullable=True)
    remaining_days = Column(Integer, nullable=True)

    status = Column(
        SQLEnum(
            AircraftProgramStatusEnum,
            name="aircraft_program_status_enum",
            native_enum=False,
        ),
        nullable=False,
        default=AircraftProgramStatusEnum.PLANNED,
        index=True,
    )

    # Audit (accounts.users.id is a GUID string)
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

    # Relationships
    program_item = relationship(
        "AmpProgramItem",
        back_populates="aircraft_items",
        lazy="joined",
    )

    # Simple navigation helpers; "Aircraft" and "AircraftComponent"
    # live in the fleet app models and will be resolved by name.
    aircraft = relationship("Aircraft", lazy="joined")
    component = relationship("AircraftComponent", lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<AmpAircraftProgramItem id={self.id} aircraft={self.aircraft_serial_number} "
            f"program_item_id={self.program_item_id} status={self.status}>"
        )
