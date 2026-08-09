from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityEffectivenessResponseAction(Base):
    __tablename__ = "quality_effectiveness_response_actions"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ('ADDITIONAL_ACTION','FOLLOW_UP_AUDIT','REOPEN_CAR','MANAGEMENT_ESCALATION','RISK_REASSESSMENT')",
            name="ck_quality_effectiveness_response_type",
        ),
        CheckConstraint("status IN ('OPEN','COMPLETED','CANCELLED')", name="ck_quality_effectiveness_response_status"),
        Index("ix_quality_effectiveness_response_case", "amo_id", "case_id", "status", "created_at"),
        Index("ix_quality_effectiveness_response_plan", "amo_id", "effectiveness_plan_id", "status"),
        Index("ix_quality_effectiveness_response_due", "amo_id", "status", "due_date"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String(36), ForeignKey("quality_assurance_cases.id", ondelete="CASCADE"), nullable=False)
    effectiveness_plan_id = Column(String(36), ForeignKey("quality_effectiveness_plans.id", ondelete="CASCADE"), nullable=False)
    action_type = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False, default="OPEN", server_default="OPEN")
    rationale = Column(Text, nullable=False)
    target_source_type = Column(String(64), nullable=True)
    target_source_id = Column(String(160), nullable=True)
    target_route = Column(String(500), nullable=True)
    schedule_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audit_schedules.id", ondelete="SET NULL"), nullable=True)
    due_date = Column(Date, nullable=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source_snapshot = Column(JSON, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    completed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completion_reason = Column(Text, nullable=True)

    events = relationship(
        "QualityEffectivenessResponseEvent",
        back_populates="response_action",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QualityEffectivenessResponseEvent.created_at",
        lazy="selectin",
    )


class QualityEffectivenessResponseEvent(Base):
    __tablename__ = "quality_effectiveness_response_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('OPENED','COMPLETED','CANCELLED')", name="ck_quality_effectiveness_response_event_type"),
        Index("ix_quality_effectiveness_response_events", "amo_id", "case_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String(36), ForeignKey("quality_assurance_cases.id", ondelete="CASCADE"), nullable=False)
    response_action_id = Column(String(36), ForeignKey("quality_effectiveness_response_actions.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(16), nullable=False)
    reason = Column(Text, nullable=False)
    snapshot = Column(JSON, nullable=False, default=dict)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    response_action = relationship("QualityEffectivenessResponseAction", back_populates="events", lazy="joined")
