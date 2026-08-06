from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RolloutGroup(Base):
    __tablename__ = "rollout_groups"
    __table_args__ = (
        UniqueConstraint("amo_id", "name", name="uq_rollout_group_amo_name"),
        Index("ix_rollout_groups_amo_status", "amo_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    selection_json = Column(JSON, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    waves = relationship(
        "RolloutWave",
        back_populates="group",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class RolloutWave(Base):
    __tablename__ = "rollout_waves"
    __table_args__ = (
        UniqueConstraint("group_id", "sequence_no", name="uq_rollout_wave_sequence"),
        UniqueConstraint("group_id", "name", name="uq_rollout_wave_name"),
        Index("ix_rollout_waves_amo_status", "amo_id", "status"),
        Index("ix_rollout_waves_group", "group_id", "sequence_no"),
        CheckConstraint("sequence_no >= 1", name="ck_rollout_wave_sequence"),
        CheckConstraint(
            "planned_start IS NULL OR planned_end IS NULL OR planned_end >= planned_start",
            name="ck_rollout_wave_dates",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id = Column(String(36), ForeignKey("rollout_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    sequence_no = Column(Integer, nullable=False)
    planned_start = Column(Date, nullable=True)
    planned_end = Column(Date, nullable=True)
    status = Column(String(24), nullable=False, default="PLANNED", index=True)
    readiness_json = Column(JSON, nullable=False, default=dict)
    decision_notes = Column(Text, nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    group = relationship("RolloutGroup", back_populates="waves", lazy="joined")
    aircraft = relationship(
        "RolloutWaveAircraft",
        back_populates="wave",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    checklist_items = relationship(
        "RolloutChecklistItem",
        back_populates="wave",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class RolloutWaveAircraft(Base):
    __tablename__ = "rollout_wave_aircraft"
    __table_args__ = (
        UniqueConstraint("wave_id", "aircraft_serial_number", name="uq_rollout_wave_aircraft"),
        Index("ix_rollout_wave_aircraft_status", "wave_id", "status"),
        Index("ix_rollout_aircraft_amo_registration", "amo_id", "registration"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    wave_id = Column(String(36), ForeignKey("rollout_waves.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    registration = Column(String(20), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="PLANNED", index=True)
    migration_batch_id = Column(
        String(36),
        ForeignKey("migration_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dual_run_started_at = Column(DateTime(timezone=True), nullable=True)
    cutover_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    hold_reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    wave = relationship("RolloutWave", back_populates="aircraft", lazy="joined")


class RolloutChecklistItem(Base):
    __tablename__ = "rollout_checklist_items"
    __table_args__ = (
        UniqueConstraint(
            "wave_id",
            "aircraft_serial_number",
            "check_key",
            name="uq_rollout_checklist_scope_key",
        ),
        Index("ix_rollout_checklist_wave_status", "wave_id", "status"),
        Index("ix_rollout_checklist_aircraft", "aircraft_serial_number", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    wave_id = Column(String(36), ForeignKey("rollout_waves.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    check_key = Column(String(64), nullable=False)
    category = Column(String(24), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    evidence_json = Column(JSON, nullable=False, default=list)
    notes = Column(Text, nullable=True)
    completed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    wave = relationship("RolloutWave", back_populates="checklist_items", lazy="joined")


class SpreadsheetRegister(Base):
    __tablename__ = "spreadsheet_register"
    __table_args__ = (
        UniqueConstraint("amo_id", "name", name="uq_spreadsheet_register_amo_name"),
        Index("ix_spreadsheet_register_amo_status", "amo_id", "status"),
        Index("ix_spreadsheet_register_domain", "amo_id", "data_domain"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    owner = Column(String(255), nullable=True)
    location = Column(String(512), nullable=True)
    purpose = Column(Text, nullable=False)
    data_domain = Column(String(48), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="LIVE", index=True)
    replacement_route = Column(String(255), nullable=True)
    retirement_criteria_json = Column(JSON, nullable=False, default=list)
    retirement_evidence_json = Column(JSON, nullable=False, default=list)
    retired_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    events = relationship(
        "SpreadsheetRetirementEvent",
        back_populates="spreadsheet",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class SpreadsheetRetirementEvent(Base):
    __tablename__ = "spreadsheet_retirement_events"
    __table_args__ = (
        Index("ix_spreadsheet_events_sheet_time", "spreadsheet_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    spreadsheet_id = Column(
        String(36),
        ForeignKey("spreadsheet_register.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(32), nullable=False)
    from_status = Column(String(24), nullable=True)
    to_status = Column(String(24), nullable=False)
    notes = Column(Text, nullable=True)
    evidence_json = Column(JSON, nullable=False, default=list)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    spreadsheet = relationship("SpreadsheetRegister", back_populates="events", lazy="joined")
