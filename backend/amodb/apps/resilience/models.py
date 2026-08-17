from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint

from ...database import Base
from ...user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReplayCommand(Base):
    """Durable, tenant-scoped receipt for every mutation that may be replayed.

    The row and the domain change are committed in one database transaction. A
    client can therefore safely ask whether a timed-out command completed before
    attempting it again.
    """

    __tablename__ = "portal_replay_commands"
    __table_args__ = (
        UniqueConstraint(
            "amo_id", "actor_user_id", "method", "route_key", "idempotency_key",
            name="uq_portal_replay_command_scope",
        ),
        Index("ix_portal_replay_command_status", "status", "lease_expires_at"),
        Index("ix_portal_replay_command_tenant_created", "amo_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    method = Column(String(12), nullable=False)
    route_key = Column(String(200), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    request_hash = Column(String(64), nullable=False)
    expected_revision = Column(String(128), nullable=True)
    status = Column(String(24), nullable=False, default="PROCESSING")
    response_status = Column(Integer, nullable=True)
    response_json = Column(JSON, nullable=True)
    error_code = Column(String(96), nullable=True)
    error_detail = Column(Text, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=1)
    lease_owner = Column(String(128), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
