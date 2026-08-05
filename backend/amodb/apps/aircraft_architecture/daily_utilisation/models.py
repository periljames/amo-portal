from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)

from amodb.database import Base
from amodb.utils.identifiers import generate_uuid7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DailyUtilisationEntry(Base):
    """Immutable source posting for one aircraft operating day."""

    __tablename__ = "aircraft_daily_utilisation_entries"
    __table_args__ = (
        UniqueConstraint("amo_id", "idempotency_key", name="uq_daily_util_idempotency"),
        UniqueConstraint(
            "amo_id",
            "aircraft_serial_number",
            "operation_date",
            "revision_no",
            name="uq_daily_util_aircraft_date_revision",
        ),
        CheckConstraint("flight_hours >= 0", name="ck_daily_util_hours_nonneg"),
        CheckConstraint("cycles >= 0", name="ck_daily_util_cycles_nonneg"),
        CheckConstraint(
            "status IN ('DRAFT','POSTED','SUPERSEDED','REJECTED')",
            name="ck_daily_util_status",
        ),
        CheckConstraint(
            "source_type IN ('MANUAL','CSV','EFB','INTEGRATION')",
            name="ck_daily_util_source_type",
        ),
        Index(
            "ix_daily_util_aircraft_date",
            "amo_id",
            "aircraft_serial_number",
            "operation_date",
        ),
        Index("ix_daily_util_status", "amo_id", "status", "operation_date"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation_date = Column(Date, nullable=False, index=True)
    techlog_no = Column(String(64), nullable=False)
    station = Column(String(16), nullable=True)
    flight_hours = Column(Numeric(12, 2), nullable=False)
    cycles = Column(Integer, nullable=False)
    nil_operation = Column(Boolean, nullable=False, default=False)
    source_type = Column(String(16), nullable=False, default="MANUAL")
    source_reference = Column(String(255), nullable=True)
    status = Column(String(16), nullable=False, default="DRAFT", index=True)
    revision_no = Column(Integer, nullable=False, default=1)
    supersedes_entry_id = Column(
        String(36),
        ForeignKey("aircraft_daily_utilisation_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )
    idempotency_key = Column(String(96), nullable=False)
    content_hash = Column(String(64), nullable=False)
    remarks = Column(Text, nullable=True)

    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    posted_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    posted_at = Column(DateTime(timezone=True), nullable=True)


class DailyUtilisationExposure(Base):
    """Per-airframe/component exposure derived from a daily source posting."""

    __tablename__ = "aircraft_daily_utilisation_exposures"
    __table_args__ = (
        UniqueConstraint(
            "entry_id",
            "target_type",
            "component_id",
            name="uq_daily_util_exposure_target",
        ),
        CheckConstraint(
            "target_type IN ('AIRFRAME','ENGINE','PROPELLER','APU','COMPONENT')",
            name="ck_daily_util_exposure_target",
        ),
        CheckConstraint("hours_delta >= 0", name="ck_daily_util_exposure_hours"),
        CheckConstraint("cycles_delta >= 0", name="ck_daily_util_exposure_cycles"),
        Index("ix_daily_util_exposure_entry", "entry_id", "target_type"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    entry_id = Column(
        String(36),
        ForeignKey("aircraft_daily_utilisation_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_type = Column(String(16), nullable=False)
    component_id = Column(
        Integer,
        ForeignKey("aircraft_components.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    component_position = Column(String(50), nullable=False)
    component_description = Column(String(255), nullable=True)
    derivation = Column(String(24), nullable=False)
    hours_delta = Column(Numeric(12, 2), nullable=False)
    cycles_delta = Column(Integer, nullable=False)
    before_hours = Column(Numeric(14, 2), nullable=True)
    before_cycles = Column(Integer, nullable=True)
    after_hours = Column(Numeric(14, 2), nullable=True)
    after_cycles = Column(Integer, nullable=True)
    baseline_missing = Column(Boolean, nullable=False, default=False)
    override_reason = Column(Text, nullable=True)
