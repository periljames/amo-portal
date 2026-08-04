from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
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


class MigrationBatchStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    STAGED = "STAGED"
    VALIDATED = "VALIDATED"
    RECONCILED = "RECONCILED"
    APPROVED = "APPROVED"
    COMMITTED = "COMMITTED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    CANCELLED = "CANCELLED"


class MigrationMode(str, enum.Enum):
    DRY_RUN = "DRY_RUN"
    COMMIT = "COMMIT"


class MigrationRowStatus(str, enum.Enum):
    STAGED = "STAGED"
    VALID = "VALID"
    INVALID = "INVALID"
    MATCHED = "MATCHED"
    CONFLICT = "CONFLICT"
    READY = "READY"
    APPLIED = "APPLIED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class MigrationReconciliationStatus(str, enum.Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    WAIVED = "WAIVED"


class MigrationCheckpointStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MigrationBatch(Base):
    __tablename__ = "migration_batches"
    __table_args__ = (
        UniqueConstraint("amo_id", "name", name="uq_migration_batch_amo_name"),
        Index("ix_migration_batches_amo_status", "amo_id", "status"),
        Index("ix_migration_batches_aircraft", "amo_id", "target_aircraft_serial_number"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    preset = Column(String(64), nullable=True, index=True)
    target_aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_registration = Column(String(20), nullable=True, index=True)
    source_type = Column(String(24), nullable=False, default="SPREADSHEET")
    source_reference = Column(String(255), nullable=True)
    status = Column(String(24), nullable=False, default=MigrationBatchStatus.DRAFT.value, index=True)
    mode = Column(String(16), nullable=False, default=MigrationMode.DRY_RUN.value)
    scope_json = Column(JSON, nullable=False, default=dict)
    summary_json = Column(JSON, nullable=False, default=dict)
    cutover_checklist_json = Column(JSON, nullable=False, default=dict)
    rollback_manifest_json = Column(JSON, nullable=False, default=list)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    committed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    committed_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    rows = relationship(
        "MigrationRow",
        back_populates="batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    reconciliation_items = relationship(
        "MigrationReconciliationItem",
        back_populates="batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    checkpoints = relationship(
        "MigrationCheckpoint",
        back_populates="batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class MigrationRow(Base):
    __tablename__ = "migration_rows"
    __table_args__ = (
        UniqueConstraint("batch_id", "dataset", "source_key", name="uq_migration_row_batch_source"),
        UniqueConstraint("batch_id", "dataset", "source_row_number", name="uq_migration_row_batch_number"),
        Index("ix_migration_rows_batch_status", "batch_id", "status"),
        Index("ix_migration_rows_batch_dataset", "batch_id", "dataset", "source_row_number"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(String(36), ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset = Column(String(32), nullable=False, index=True)
    source_row_number = Column(Integer, nullable=False)
    source_key = Column(String(160), nullable=False)
    raw_json = Column(JSON, nullable=False, default=dict)
    normalized_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(24), nullable=False, default=MigrationRowStatus.STAGED.value, index=True)
    action = Column(String(24), nullable=False, default="PENDING")
    errors_json = Column(JSON, nullable=False, default=list)
    warnings_json = Column(JSON, nullable=False, default=list)
    local_object_type = Column(String(64), nullable=True)
    local_object_id = Column(String(64), nullable=True)
    before_json = Column(JSON, nullable=True)
    after_json = Column(JSON, nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    batch = relationship("MigrationBatch", back_populates="rows", lazy="joined")
    reconciliation_items = relationship(
        "MigrationReconciliationItem",
        back_populates="row",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class MigrationReconciliationItem(Base):
    __tablename__ = "migration_reconciliation_items"
    __table_args__ = (
        Index("ix_migration_recon_batch_status", "batch_id", "status"),
        Index("ix_migration_recon_amo_severity", "amo_id", "severity", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(String(36), ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    row_id = Column(String(36), ForeignKey("migration_rows.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(48), nullable=False, index=True)
    severity = Column(String(16), nullable=False, default="ERROR", index=True)
    status = Column(String(20), nullable=False, default=MigrationReconciliationStatus.OPEN.value, index=True)
    summary = Column(Text, nullable=False)
    source_json = Column(JSON, nullable=False, default=dict)
    local_json = Column(JSON, nullable=False, default=dict)
    differences_json = Column(JSON, nullable=False, default=dict)
    resolution = Column(String(24), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    resolved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    batch = relationship("MigrationBatch", back_populates="reconciliation_items", lazy="joined")
    row = relationship("MigrationRow", back_populates="reconciliation_items", lazy="joined")


class MigrationCheckpoint(Base):
    __tablename__ = "migration_checkpoints"
    __table_args__ = (
        UniqueConstraint("batch_id", "checkpoint_key", name="uq_migration_checkpoint_key"),
        Index("ix_migration_checkpoints_batch_status", "batch_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(String(36), ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    checkpoint_key = Column(String(64), nullable=False)
    label = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default=MigrationCheckpointStatus.PENDING.value, index=True)
    evidence_json = Column(JSON, nullable=False, default=list)
    notes = Column(Text, nullable=True)
    completed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    batch = relationship("MigrationBatch", back_populates="checkpoints", lazy="joined")
