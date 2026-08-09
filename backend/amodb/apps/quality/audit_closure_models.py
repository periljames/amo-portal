from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditClosureState(Base):
    __tablename__ = "quality_audit_closure_states"
    __table_args__ = (
        UniqueConstraint("amo_id", "audit_id", name="uq_quality_audit_closure_state"),
        CheckConstraint("execution_status IN ('OPEN','CLOSED')", name="ck_quality_audit_execution_status"),
        CheckConstraint("follow_up_status IN ('OPEN','COMPLETE')", name="ck_quality_audit_follow_up_status"),
        Index("ix_quality_audit_closure_state", "amo_id", "execution_status", "follow_up_status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    execution_status = Column(String(16), nullable=False, default="OPEN", server_default="OPEN")
    execution_closed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    execution_closed_at = Column(DateTime(timezone=True), nullable=True)
    execution_close_reason = Column(Text, nullable=True)
    execution_evidence_snapshot = Column(JSON, nullable=False, default=dict)
    follow_up_status = Column(String(16), nullable=False, default="OPEN", server_default="OPEN")
    follow_up_completed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    follow_up_completed_at = Column(DateTime(timezone=True), nullable=True)
    follow_up_completion_reason = Column(Text, nullable=True)
    follow_up_evidence_snapshot = Column(JSON, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    events = relationship(
        "QualityAuditClosureEvent",
        back_populates="closure_state",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QualityAuditClosureEvent.created_at",
        lazy="selectin",
    )


class QualityAuditClosureEvent(Base):
    __tablename__ = "quality_audit_closure_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('EXECUTION_CLOSED','FOLLOW_UP_COMPLETED','FOLLOW_UP_REOPENED')",
            name="ck_quality_audit_closure_event_type",
        ),
        Index("ix_quality_audit_closure_events", "amo_id", "audit_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    closure_state_id = Column(String(36), ForeignKey("quality_audit_closure_states.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(32), nullable=False)
    reason = Column(Text, nullable=False)
    evidence_snapshot = Column(JSON, nullable=False, default=dict)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    closure_state = relationship("QualityAuditClosureState", back_populates="events", lazy="joined")
