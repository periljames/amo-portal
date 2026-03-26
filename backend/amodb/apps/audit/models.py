from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, Index, JSON, String

from ...database import Base
from ...utils.identifiers import generate_uuid7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditEvent(Base):
    """
    Append-only audit trail for maintenance, configuration, and work actions.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_amo_entity", "amo_id", "entity_type", "entity_id"),
        Index("ix_audit_events_amo_action", "amo_id", "action"),
        Index("ix_audit_events_amo_time", "amo_id", "occurred_at"),
        Index("ix_audit_events_amo_actor", "amo_id", "actor_user_id"),
        Index(
            "ix_audit_events_correlation_id",
            "correlation_id",
            postgresql_where=sa.text("correlation_id IS NOT NULL"),
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(64), nullable=False)
    action = Column(String(64), nullable=False, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    before = Column(JSON, nullable=True)
    after = Column(JSON, nullable=True)
    correlation_id = Column(String(64), nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    def __repr__(self) -> str:
        return f"<AuditEvent id={self.id} entity={self.entity_type}:{self.entity_id} action={self.action}>"
