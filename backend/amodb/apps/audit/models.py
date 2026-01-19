from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String

from ...database import Base


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
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    before_json = Column(JSON, nullable=True)
    after_json = Column(JSON, nullable=True)
    correlation_id = Column(String(64), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    def __repr__(self) -> str:
        return f"<AuditEvent id={self.id} entity={self.entity_type}:{self.entity_id} action={self.action}>"
