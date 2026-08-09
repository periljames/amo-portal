from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, Uuid

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditSourceLink(Base):
    __tablename__ = "quality_audit_source_links"
    __table_args__ = (
        CheckConstraint("source_type IN ('MISSION','SIGNAL','ASSURANCE_CASE','PROGRAMME','OTHER')", name="ck_quality_audit_source_link_type"),
        UniqueConstraint("amo_id", "schedule_id", "source_type", "source_id", name="uq_quality_audit_source_link"),
        Index("ix_quality_audit_source_link_schedule", "amo_id", "schedule_id", "source_type"),
        Index("ix_quality_audit_source_link_source", "amo_id", "source_type", "source_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    schedule_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audit_schedules.id", ondelete="CASCADE"), nullable=False)
    source_type = Column(String(24), nullable=False)
    source_id = Column(String(160), nullable=False)
    source_route = Column(String(500), nullable=True)
    rationale = Column(Text, nullable=False)
    source_snapshot = Column(JSON, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
