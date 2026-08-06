from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WinAirProfileStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class WinAirSyncMode(str, enum.Enum):
    SHADOW = "SHADOW"
    ACTIVE = "ACTIVE"


class WinAirTransport(str, enum.Enum):
    API = "API"
    FILE = "FILE"
    WEBHOOK = "WEBHOOK"


class WinAirDirection(str, enum.Enum):
    BIDIRECTIONAL = "BIDIRECTIONAL"
    INBOUND_ONLY = "INBOUND_ONLY"
    OUTBOUND_ONLY = "OUTBOUND_ONLY"


class WinAirRunType(str, enum.Enum):
    PULL = "PULL"
    PUSH = "PUSH"
    RECONCILE = "RECONCILE"
    DRY_RUN = "DRY_RUN"


class WinAirRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WinAirRecordStatus(str, enum.Enum):
    STAGED = "STAGED"
    APPLIED = "APPLIED"
    SKIPPED = "SKIPPED"
    CONFLICT = "CONFLICT"
    FAILED = "FAILED"


class WinAirConflictStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACCEPT_EXTERNAL = "ACCEPT_EXTERNAL"
    KEEP_LOCAL = "KEEP_LOCAL"
    MERGED = "MERGED"
    IGNORED = "IGNORED"


class WinAirSyncProfile(Base):
    __tablename__ = "winair_sync_profiles"
    __table_args__ = (
        UniqueConstraint("amo_id", "name", name="uq_winair_profile_amo_name"),
        UniqueConstraint("amo_id", "integration_config_id", name="uq_winair_profile_amo_config"),
        Index("ix_winair_profiles_amo_status", "amo_id", "status"),
        CheckConstraint("hours_tolerance >= 0", name="ck_winair_profile_hours_tolerance"),
        CheckConstraint("cycles_tolerance >= 0", name="ck_winair_profile_cycles_tolerance"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_config_id = Column(
        String(36),
        ForeignKey("integration_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(128), nullable=False)
    status = Column(String(16), nullable=False, default=WinAirProfileStatus.ACTIVE.value, index=True)
    mode = Column(String(16), nullable=False, default=WinAirSyncMode.SHADOW.value)
    transport = Column(String(16), nullable=False, default=WinAirTransport.API.value)
    direction = Column(String(24), nullable=False, default=WinAirDirection.BIDIRECTIONAL.value)
    authority_json = Column(JSON, nullable=False, default=dict)
    mapping_json = Column(JSON, nullable=False, default=dict)
    dataset_config_json = Column(JSON, nullable=False, default=dict)
    last_cursor_json = Column(JSON, nullable=False, default=dict)
    hours_tolerance = Column(Numeric(14, 2), nullable=False, default=0.05)
    cycles_tolerance = Column(Integer, nullable=False, default=0)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    runs = relationship(
        "WinAirSyncRun",
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class WinAirSyncRun(Base):
    __tablename__ = "winair_sync_runs"
    __table_args__ = (
        Index("ix_winair_runs_amo_profile_started", "amo_id", "profile_id", "started_at"),
        Index("ix_winair_runs_amo_status", "amo_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id = Column(String(36), ForeignKey("winair_sync_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    run_type = Column(String(20), nullable=False, index=True)
    status = Column(String(20), nullable=False, default=WinAirRunStatus.PENDING.value, index=True)
    dry_run = Column(Boolean, nullable=False, default=False)
    requested_datasets_json = Column(JSON, nullable=False, default=list)
    cursor_before_json = Column(JSON, nullable=False, default=dict)
    cursor_after_json = Column(JSON, nullable=False, default=dict)
    counts_json = Column(JSON, nullable=False, default=dict)
    started_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error_summary = Column(Text, nullable=True)
    triggered_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    profile = relationship("WinAirSyncProfile", back_populates="runs", lazy="joined")
    records = relationship(
        "WinAirSyncRecord",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class WinAirSyncRecord(Base):
    __tablename__ = "winair_sync_records"
    __table_args__ = (
        UniqueConstraint("run_id", "dataset", "direction", "external_key", name="uq_winair_run_record"),
        Index("ix_winair_records_run_status", "run_id", "status"),
        Index("ix_winair_records_profile_dataset", "profile_id", "dataset", "external_key"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id = Column(String(36), ForeignKey("winair_sync_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(String(36), ForeignKey("winair_sync_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset = Column(String(32), nullable=False, index=True)
    direction = Column(String(12), nullable=False)
    external_key = Column(String(160), nullable=False)
    local_object_type = Column(String(64), nullable=True)
    local_object_id = Column(String(64), nullable=True)
    action = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default=WinAirRecordStatus.STAGED.value, index=True)
    source_payload_json = Column(JSON, nullable=False, default=dict)
    normalized_payload_json = Column(JSON, nullable=False, default=dict)
    source_hash = Column(String(64), nullable=False)
    local_hash = Column(String(64), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    applied_at = Column(DateTime(timezone=True), nullable=True)

    run = relationship("WinAirSyncRun", back_populates="records", lazy="joined")


class WinAirObjectMap(Base):
    __tablename__ = "winair_object_maps"
    __table_args__ = (
        UniqueConstraint("profile_id", "dataset", "external_key", name="uq_winair_object_map_external"),
        Index("ix_winair_maps_local", "amo_id", "local_object_type", "local_object_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id = Column(String(36), ForeignKey("winair_sync_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset = Column(String(32), nullable=False, index=True)
    external_key = Column(String(160), nullable=False)
    canonical_key = Column(String(160), nullable=True)
    local_object_type = Column(String(64), nullable=False)
    local_object_id = Column(String(64), nullable=False)
    last_source_hash = Column(String(64), nullable=True)
    last_local_hash = Column(String(64), nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class WinAirSyncConflict(Base):
    __tablename__ = "winair_sync_conflicts"
    __table_args__ = (
        Index("ix_winair_conflicts_amo_status", "amo_id", "status"),
        Index("ix_winair_conflicts_profile_dataset", "profile_id", "dataset", "external_key"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id = Column(String(36), ForeignKey("winair_sync_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(String(36), ForeignKey("winair_sync_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    record_id = Column(String(36), ForeignKey("winair_sync_records.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset = Column(String(32), nullable=False, index=True)
    external_key = Column(String(160), nullable=False)
    conflict_type = Column(String(48), nullable=False, index=True)
    source_payload_json = Column(JSON, nullable=False, default=dict)
    local_payload_json = Column(JSON, nullable=False, default=dict)
    field_differences_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(24), nullable=False, default=WinAirConflictStatus.OPEN.value, index=True)
    resolution_notes = Column(Text, nullable=True)
    resolved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
