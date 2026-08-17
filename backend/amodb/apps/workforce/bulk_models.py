"""Durable Workforce bulk-operation records.

The request row is the idempotency and progress boundary.  Item rows preserve
per-person outcomes so failed records can be retried without repeating success.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
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

from ...database import Base
from ...user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkforceBulkOperation(Base):
    __tablename__ = "workforce_bulk_operations"
    __table_args__ = (
        UniqueConstraint(
            "amo_id",
            "actor_user_id",
            "operation_type",
            "idempotency_key",
            name="uq_workforce_bulk_operation_idempotency",
        ),
        Index("ix_workforce_bulk_operation_tenant_status", "amo_id", "status", "created_at"),
        Index("ix_workforce_bulk_operation_actor", "amo_id", "actor_user_id", "created_at"),
        Index("ix_workforce_bulk_operation_retry", "retry_of_operation_id"),
        CheckConstraint("total_count >= 0", name="ck_workforce_bulk_operation_total"),
        CheckConstraint("processed_count >= 0", name="ck_workforce_bulk_operation_processed"),
        CheckConstraint("succeeded_count >= 0", name="ck_workforce_bulk_operation_succeeded"),
        CheckConstraint("skipped_count >= 0", name="ck_workforce_bulk_operation_skipped"),
        CheckConstraint("failed_count >= 0", name="ck_workforce_bulk_operation_failed"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    operation_type = Column(String(64), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="QUEUED", index=True)
    idempotency_key = Column(String(128), nullable=False)
    request_hash = Column(String(64), nullable=False)
    selection_token = Column(String(64), nullable=False)
    selection_snapshot = Column(JSON, nullable=False)
    payload_json = Column(JSON, nullable=False)
    retry_of_operation_id = Column(
        String(36),
        ForeignKey("workforce_bulk_operations.id", ondelete="SET NULL"),
        nullable=True,
    )
    total_count = Column(Integer, nullable=False, default=0)
    processed_count = Column(Integer, nullable=False, default=0)
    succeeded_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    items = relationship(
        "WorkforceBulkOperationItem",
        back_populates="operation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="WorkforceBulkOperationItem.sequence",
    )


class WorkforceBulkOperationItem(Base):
    __tablename__ = "workforce_bulk_operation_items"
    __table_args__ = (
        UniqueConstraint("operation_id", "user_id", name="uq_workforce_bulk_operation_item_user"),
        Index("ix_workforce_bulk_item_status", "operation_id", "status", "sequence"),
        Index("ix_workforce_bulk_item_claim", "status", "claim_expires_at", "sequence"),
        Index("ix_workforce_bulk_item_tenant_user", "amo_id", "user_id", "created_at"),
        CheckConstraint("sequence >= 0", name="ck_workforce_bulk_item_sequence"),
        CheckConstraint("attempt_count >= 0", name="ck_workforce_bulk_item_attempts"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    operation_id = Column(
        String(36),
        ForeignKey("workforce_bulk_operations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False, default="PENDING", index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    outcome_code = Column(String(96), nullable=True)
    outcome_message = Column(Text, nullable=True)
    input_json = Column(JSON, nullable=True)
    result_json = Column(JSON, nullable=True)
    claim_token = Column(String(64), nullable=True)
    claimed_by = Column(String(128), nullable=True)
    claim_expires_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    operation = relationship("WorkforceBulkOperation", back_populates="items", lazy="joined")
