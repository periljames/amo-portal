from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text

from ...database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AircraftUsageCorrection(Base):
    """Append-only request and decision record for an aircraft-usage correction."""

    __tablename__ = "aircraft_usage_corrections"
    __table_args__ = (
        Index("ix_usage_corrections_amo_status", "amo_id", "status"),
        Index("ix_usage_corrections_usage", "usage_id", "requested_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    usage_id = Column(Integer, ForeignKey("aircraft_usage.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason = Column(Text, nullable=False)
    proposed_values_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(16), nullable=False, default="PENDING", index=True)
    expected_usage_updated_at = Column(DateTime(timezone=True), nullable=False)
    requested_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_notes = Column(Text, nullable=True)
    requested_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)
