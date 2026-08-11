from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)

from ...database import Base
from ...user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RosterAircraftAllocationType(str, Enum):
    FLIGHT_ENGINEERING = "FLIGHT_ENGINEERING"
    LINE_SUPPORT = "LINE_SUPPORT"
    OTHER = "OTHER"


class RosterAircraftAllocation(Base):
    """Direct operational aircraft allocation for a roster assignment.

    This is intentionally independent of maintenance task/work-order links.
    A Flight Engineer may follow an aircraft operationally without being
    allocated to a maintenance work order.
    """

    __tablename__ = "roster_aircraft_allocations"
    __table_args__ = (
        UniqueConstraint(
            "roster_assignment_id",
            "aircraft_serial_number",
            "starts_at",
            "ends_at",
            name="uq_roster_aircraft_allocation_window",
        ),
        Index("ix_roster_aircraft_alloc_amo_assignment", "amo_id", "roster_assignment_id"),
        Index("ix_roster_aircraft_alloc_aircraft_time", "aircraft_serial_number", "starts_at", "ends_at"),
        CheckConstraint("ends_at > starts_at", name="ck_roster_aircraft_alloc_time_order"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    roster_assignment_id = Column(
        String(36),
        ForeignKey("roster_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    allocation_type = Column(
        SAEnum(
            RosterAircraftAllocationType,
            name="roster_aircraft_allocation_type_enum",
            native_enum=False,
        ),
        nullable=False,
        default=RosterAircraftAllocationType.FLIGHT_ENGINEERING,
    )
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
