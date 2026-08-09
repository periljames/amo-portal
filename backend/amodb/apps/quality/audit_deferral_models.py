from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditDeferral(Base):
    __tablename__ = "quality_audit_deferrals"
    __table_args__ = (
        CheckConstraint("status IN ('REQUESTED','APPROVED','REJECTED','APPLIED','WITHDRAWN')", name="ck_quality_audit_deferral_status"),
        CheckConstraint("risk_rating IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="ck_quality_audit_deferral_risk"),
        CheckConstraint("repeated_deferral_count >= 0", name="ck_quality_audit_deferral_repeat_count"),
        CheckConstraint("revised_target_end IS NULL OR revised_target_end >= revised_target_start", name="ck_quality_audit_deferral_revised_dates"),
        Index("ix_quality_audit_deferral_item", "amo_id", "programme_item_id", "status", "requested_at"),
        Index("ix_quality_audit_deferral_risk", "amo_id", "risk_rating", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    programme_id = Column(String(36), ForeignKey("quality_audit_programmes.id", ondelete="CASCADE"), nullable=False)
    programme_item_id = Column(String(36), ForeignKey("quality_audit_programme_items.id", ondelete="CASCADE"), nullable=False)
    original_target_start = Column(Date, nullable=True)
    original_target_end = Column(Date, nullable=True)
    revised_target_start = Column(Date, nullable=False)
    revised_target_end = Column(Date, nullable=True)
    reason = Column(Text, nullable=False)
    risk_rating = Column(String(16), nullable=False)
    risk_assessment = Column(Text, nullable=False)
    mitigations = Column(JSON, nullable=False, default=list)
    approval_required = Column(Boolean, nullable=False, default=False, server_default="false")
    repeated_deferral_count = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String(16), nullable=False, default="REQUESTED", server_default="REQUESTED")
    requested_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    requested_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    decided_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decision_reason = Column(Text, nullable=True)
    applied_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)

    events = relationship(
        "QualityAuditDeferralEvent",
        back_populates="deferral",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QualityAuditDeferralEvent.created_at",
        lazy="selectin",
    )


class QualityAuditDeferralEvent(Base):
    __tablename__ = "quality_audit_deferral_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('REQUESTED','APPROVED','REJECTED','APPLIED','WITHDRAWN')", name="ck_quality_audit_deferral_event_type"),
        Index("ix_quality_audit_deferral_events", "amo_id", "programme_item_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    programme_item_id = Column(String(36), ForeignKey("quality_audit_programme_items.id", ondelete="CASCADE"), nullable=False)
    deferral_id = Column(String(36), ForeignKey("quality_audit_deferrals.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(16), nullable=False)
    reason = Column(Text, nullable=False)
    snapshot = Column(JSON, nullable=False, default=dict)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    deferral = relationship("QualityAuditDeferral", back_populates="events", lazy="joined")
