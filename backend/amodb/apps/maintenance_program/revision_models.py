from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from ...database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AmpProgramRevision(Base):
    __tablename__ = "amp_program_revisions"
    __table_args__ = (
        UniqueConstraint("amo_id", "template_code", "revision_code", name="uq_amp_revision_identity"),
        Index("ix_amp_revisions_amo_status", "amo_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    template_code = Column(String(50), nullable=False, index=True)
    revision_code = Column(String(32), nullable=False)
    title = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    effective_date = Column(Date, nullable=True)
    source_reference = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class AmpAircraftBaseline(Base):
    __tablename__ = "amp_aircraft_baselines"
    __table_args__ = (
        Index("ix_amp_baselines_amo_aircraft", "amo_id", "aircraft_serial_number", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_id = Column(
        Integer,
        ForeignKey("amp_program_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    template_code = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    applied_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    notes = Column(Text, nullable=True)
