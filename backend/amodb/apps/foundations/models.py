# backend/amodb/apps/foundations/models.py
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from ...database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class BaseStationType(str, enum.Enum):
    MAIN_BASE = "MAIN_BASE"
    LINE_STATION = "LINE_STATION"
    OUTSTATION = "OUTSTATION"
    WORKSHOP = "WORKSHOP"
    HANGAR = "HANGAR"
    TRAINING_SITE = "TRAINING_SITE"
    OTHER = "OTHER"


class BaseAssignmentKind(str, enum.Enum):
    HOME_BASE = "HOME_BASE"
    TEMPORARY = "TEMPORARY"
    TRAINING = "TRAINING"
    RELIEF = "RELIEF"
    OTHER = "OTHER"


class AvailabilityStatus(str, enum.Enum):
    ON_DUTY = "ON_DUTY"
    AWAY = "AWAY"
    ON_LEAVE = "ON_LEAVE"


class BaseStation(Base):
    __tablename__ = "base_stations"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_base_stations_amo_code"),
        Index("ix_base_stations_amo_active", "amo_id", "is_active"),
        Index("ix_base_stations_amo_location", "amo_id", "latitude", "longitude"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(32), nullable=False)
    name = Column(String(160), nullable=False)
    icao_code = Column(String(8), nullable=True, index=True)
    iata_code = Column(String(8), nullable=True, index=True)
    base_type = Column(Enum(BaseStationType, name="base_station_type"), nullable=False, default=BaseStationType.MAIN_BASE)
    time_zone = Column(String(80), nullable=True)
    description = Column(Text, nullable=True)

    # Approved canonical location. Raw device observations are stored separately
    # and never returned by normal base-station responses.
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    coordinate_accuracy_m = Column(Float, nullable=True)
    location_source = Column(String(32), nullable=True)
    airport_reference_ident = Column(String(16), nullable=True)
    location_verified_at = Column(DateTime(timezone=True), nullable=True)
    location_verified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    geofence_radius_m = Column(Integer, nullable=False, default=250, server_default="250")
    checkin_prompt_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    checkout_reminder_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    suspicious_location_review_enabled = Column(Boolean, nullable=False, default=False, server_default="false")

    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    aliases = relationship("BaseStationAlias", back_populates="base_station", cascade="all, delete-orphan", lazy="selectin")
    user_assignments = relationship("UserBaseAssignment", back_populates="base_station", lazy="selectin")
    location_observations = relationship(
        "BaseLocationObservation",
        back_populates="base_station",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    @property
    def location_configured(self) -> bool:
        """Derived flag exposed without disclosing the approved coordinate."""
        return self.latitude is not None and self.longitude is not None


class BaseStationAlias(Base):
    __tablename__ = "base_station_aliases"
    __table_args__ = (
        UniqueConstraint("amo_id", "alias", name="uq_base_station_aliases_amo_alias"),
        Index("ix_base_station_aliases_station", "base_station_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    base_station_id = Column(String(36), ForeignKey("base_stations.id", ondelete="CASCADE"), nullable=False)
    alias = Column(String(160), nullable=False)
    source_module = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    base_station = relationship("BaseStation", back_populates="aliases")


class BaseLocationObservation(Base):
    """Short-lived, tenant-scoped location evidence used only for consensus."""

    __tablename__ = "base_location_observations"
    __table_args__ = (
        Index("ix_base_location_observations_station_created", "base_station_id", "created_at"),
        Index("ix_base_location_observations_expiry", "expires_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    base_station_id = Column(String(36), ForeignKey("base_stations.id", ondelete="CASCADE"), nullable=False)
    submitted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    accuracy_m = Column(Float, nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    base_station = relationship("BaseStation", back_populates="location_observations")


class UserBaseAssignment(Base):
    __tablename__ = "user_base_assignments"
    __table_args__ = (
        Index("ix_user_base_assignments_user_effective", "user_id", "effective_from", "effective_to"),
        Index("ix_user_base_assignments_base_effective", "base_station_id", "effective_from", "effective_to"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    base_station_id = Column(String(36), ForeignKey("base_stations.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_kind = Column(Enum(BaseAssignmentKind, name="base_assignment_kind"), nullable=False, default=BaseAssignmentKind.HOME_BASE)
    effective_from = Column(Date, nullable=False, server_default=func.current_date())
    effective_to = Column(Date, nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    note = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    base_station = relationship("BaseStation", back_populates="user_assignments", lazy="joined")


class CanonicalAvailability(Base):
    __tablename__ = "canonical_user_availability"
    __table_args__ = (
        Index("ix_canonical_availability_user_effective", "user_id", "effective_from", "effective_to"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(Enum(AvailabilityStatus, name="canonical_availability_status"), nullable=False)
    effective_from = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    effective_to = Column(DateTime(timezone=True), nullable=True)
    note = Column(Text, nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
