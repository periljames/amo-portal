from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, Uuid

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditProgrammeOccurrenceLink(Base):
    __tablename__ = "quality_audit_programme_occurrence_links"
    __table_args__ = (
        CheckConstraint("occurrence_type IN ('CUSTOM','RISK_TRIGGERED')", name="ck_quality_audit_programme_occurrence_type"),
        UniqueConstraint("amo_id", "schedule_id", name="uq_quality_audit_programme_occurrence_schedule"),
        UniqueConstraint("amo_id", "programme_item_id", "occurrence_key", name="uq_quality_audit_programme_occurrence_key"),
        Index("ix_quality_audit_programme_occurrence_item", "amo_id", "programme_item_id", "created_at"),
        Index("ix_quality_audit_programme_occurrence_source", "amo_id", "source_signal_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    programme_id = Column(String(36), ForeignKey("quality_audit_programmes.id", ondelete="CASCADE"), nullable=False)
    programme_item_id = Column(String(36), ForeignKey("quality_audit_programme_items.id", ondelete="CASCADE"), nullable=False)
    schedule_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audit_schedules.id", ondelete="CASCADE"), nullable=False)
    occurrence_type = Column(String(24), nullable=False)
    occurrence_key = Column(String(160), nullable=False)
    source_signal_id = Column(String(36), ForeignKey("quality_signal_observations.id", ondelete="SET NULL"), nullable=True)
    rationale = Column(Text, nullable=False)
    source_snapshot = Column(JSON, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
