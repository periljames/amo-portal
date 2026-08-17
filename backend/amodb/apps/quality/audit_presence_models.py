from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditPresence(Base):
    __tablename__ = "quality_audit_presence"
    __table_args__ = (
        UniqueConstraint("amo_id", "audit_id", "actor_key", name="uq_quality_audit_presence_actor"),
        CheckConstraint("actor_type IN ('INTERNAL_USER','EXTERNAL_AUDITOR','AUDITEE_GUEST')", name="ck_quality_audit_presence_actor_type"),
        CheckConstraint(
            "(actor_type = 'INTERNAL_USER' AND user_id IS NOT NULL AND participant_id IS NULL) OR "
            "(actor_type <> 'INTERNAL_USER' AND user_id IS NULL AND participant_id IS NOT NULL)",
            name="ck_quality_audit_presence_actor_identity",
        ),
        Index("ix_quality_audit_presence_live", "amo_id", "audit_id", "last_seen_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    actor_type = Column(String(24), nullable=False)
    actor_key = Column(String(96), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    participant_id = Column(String(36), ForeignKey("quality_audit_participants.id", ondelete="CASCADE"), nullable=True)
    display_name = Column(String(255), nullable=False)
    role = Column(String(128), nullable=True)
    route = Column(String(128), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
