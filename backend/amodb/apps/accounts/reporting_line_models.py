"""Reporting-line extensions that keep display titles separate from authority.

A preferred or working title is presentation metadata only. It must never be
used as a portal role, capability, licence, competence finding or maintenance
authorisation. Canonical corporate positions and their effective assignments
remain the authoritative organization records.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text

from amodb.database import Base
from amodb.user_id import generate_user_id


class PersonnelTitlePreference(Base):
    __tablename__ = "personnel_title_preferences"
    __table_args__ = (
        Index(
            "ix_personnel_title_preferences_amo_user_status",
            "amo_id",
            "user_id",
            "status",
        ),
        Index(
            "ix_personnel_title_preferences_assignment_status",
            "assignment_id",
            "status",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assignment_id = Column(
        String(36),
        ForeignKey("position_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_title = Column(String(128), nullable=False)
    reason = Column(Text, nullable=True)
    source = Column(String(32), nullable=False, default="SELF_SERVICE")
    status = Column(String(32), nullable=False, default="PENDING", index=True)
    requested_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
