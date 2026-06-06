# backend/amodb/apps/foundations/models.py
"""Shared foundation ORM models.

These tables hold data that must be shared by several modules but should not be
owned by any single operational module such as Quality, Training, Work, or Fleet.

Phase 0 scope:
- Canonical base/station master records.
- Effective-dated user-to-base assignments.

Personnel identity is intentionally *not* duplicated here. All rosterable people
must resolve to ``accounts.users.id``; optional HR-style details remain in
``personnel_profiles``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, Enum as SAEnum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from ...database import Base
from ...user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BaseStationType(str, Enum):
    MAIN_BASE = "MAIN_BASE"
    LINE_STATION = "LINE_STATION"
    OUTSTATION = "OUTSTATION"
    WORKSHOP = "WORKSHOP"
    HANGAR = "HANGAR"
    TRAINING_SITE = "TRAINING_SITE"
    OTHER = "OTHER"


class BaseAssignmentKind(str, Enum):
    HOME_BASE = "HOME_BASE"
    TEMPORARY = "TEMPORARY"
    TRAINING = "TRAINING"
    RELIEF = "RELIEF"
    OTHER = "OTHER"


class BaseStation(Base):
    __tablename__ = "base_stations"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_base_stations_amo_code"),
        Index("ix_base_stations_amo_active", "amo_id", "is_active"),
        Index("ix_base_stations_amo_type", "amo_id", "base_type"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)

    code = Column(String(32), nullable=False, doc="Canonical short code used by all modules, e.g. WIL, NBO, HANGAR.")
    name = Column(String(255), nullable=False)
    icao_code = Column(String(8), nullable=True, index=True)
    iata_code = Column(String(8), nullable=True, index=True)
    base_type = Column(SAEnum(BaseStationType, name="base_station_type_enum", native_enum=False), nullable=False, default=BaseStationType.OTHER, index=True)
    time_zone = Column(String(64), nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    aliases = relationship("BaseStationAlias", back_populates="base_station", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")
    user_assignments = relationship("UserBaseAssignment", back_populates="base_station", lazy="selectin")

    def __repr__(self) -> str:
        return f"<BaseStation {self.code} amo={self.amo_id}>"


class BaseStationAlias(Base):
    __tablename__ = "base_station_aliases"
    __table_args__ = (
        UniqueConstraint("amo_id", "alias", name="uq_base_station_aliases_amo_alias"),
        Index("ix_base_station_aliases_base", "base_station_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    base_station_id = Column(String(36), ForeignKey("base_stations.id", ondelete="CASCADE"), nullable=False, index=True)
    alias = Column(String(64), nullable=False, doc="Legacy or imported spelling/code mapped to the canonical base station.")
    source_module = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    base_station = relationship("BaseStation", back_populates="aliases", lazy="joined")


class UserBaseAssignment(Base):
    __tablename__ = "user_base_assignments"
    __table_args__ = (
        Index("ix_user_base_assignments_amo_user", "amo_id", "user_id"),
        Index("ix_user_base_assignments_amo_base", "amo_id", "base_station_id"),
        Index("ix_user_base_assignments_effective", "effective_from", "effective_to"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_user_base_assignment_dates"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    base_station_id = Column(String(36), ForeignKey("base_stations.id", ondelete="RESTRICT"), nullable=False, index=True)

    assignment_kind = Column(SAEnum(BaseAssignmentKind, name="base_assignment_kind_enum", native_enum=False), nullable=False, default=BaseAssignmentKind.HOME_BASE)
    effective_from = Column(Date, nullable=False, default=date.today)
    effective_to = Column(Date, nullable=True)
    is_primary = Column(Boolean, nullable=False, default=True, index=True)
    note = Column(Text, nullable=True)

    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    base_station = relationship("BaseStation", back_populates="user_assignments", lazy="joined")
    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    created_by = relationship("User", foreign_keys=[created_by_user_id], lazy="joined")

    def __repr__(self) -> str:
        return f"<UserBaseAssignment user={self.user_id} base={self.base_station_id}>"
