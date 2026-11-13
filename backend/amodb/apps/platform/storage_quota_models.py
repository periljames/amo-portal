"""Authoritative byte-exact tenant object-storage quotas.

Five decimal terabytes = 5_000_000_000_000 bytes. No automatic allocation:
the platform operator must activate a quota after provisioning and payment.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from amodb.database import Base
from amodb.user_id import generate_user_id

DEFAULT_PAID_QUOTA_BYTES = 5_000_000_000_000


def utcnow():
    return datetime.now(timezone.utc)


class TenantStorageQuota(Base):
    __tablename__ = "tenant_storage_quotas"
    __table_args__ = (
        CheckConstraint("quota_bytes >= 0 AND used_bytes >= 0 AND reserved_bytes >= 0", name="ck_tenant_storage_nonnegative"),
        CheckConstraint("used_bytes + reserved_bytes <= quota_bytes", name="ck_tenant_storage_not_oversubscribed"),
    )
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), primary_key=True)
    quota_bytes = Column(BigInteger, nullable=False, default=0)
    used_bytes = Column(BigInteger, nullable=False, default=0)
    reserved_bytes = Column(BigInteger, nullable=False, default=0)
    generation = Column(BigInteger, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    last_reconciled_at = Column(DateTime(timezone=True), nullable=True)
    integrity_state = Column(String(24), nullable=False, default="OK")


class TenantStorageReservation(Base):
    __tablename__ = "tenant_storage_reservations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_tenant_storage_reservation_key"),
        Index("ix_storage_reservation_expire", "state", "expires_at"),
        CheckConstraint("size_bytes > 0", name="ck_storage_reserved_positive"),
    )
    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    idempotency_key = Column(String(160), nullable=False)
    object_key = Column(Text, nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    state = Column(String(24), nullable=False, default="RESERVED")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    finalized_at = Column(DateTime(timezone=True), nullable=True)


class TenantStorageObject(Base):
    __tablename__ = "tenant_storage_objects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "object_key", name="uq_tenant_storage_object_key"),
        CheckConstraint("size_bytes >= 0", name="ck_tenant_storage_object_nonnegative"),
    )
    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    object_key = Column(Text, nullable=False)
    storage_uri = Column(Text, nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    checksum_sha256 = Column(String(64), nullable=False)
    state = Column(String(24), nullable=False, default="ACTIVE")
    retained_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    reservation_id = Column(String(36), ForeignKey("tenant_storage_reservations.id", ondelete="SET NULL"), nullable=True)


class TenantStorageLedgerEvent(Base):
    __tablename__ = "tenant_storage_ledger_events"
    __table_args__ = (Index("ix_storage_event_tenant_time", "tenant_id", "created_at"),)
    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(32), nullable=False)
    object_key = Column(Text, nullable=True)
    delta_used_bytes = Column(BigInteger, nullable=False, default=0)
    delta_reserved_bytes = Column(BigInteger, nullable=False, default=0)
    quota_after_bytes = Column(BigInteger, nullable=False)
    used_after_bytes = Column(BigInteger, nullable=False)
    reserved_after_bytes = Column(BigInteger, nullable=False)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
