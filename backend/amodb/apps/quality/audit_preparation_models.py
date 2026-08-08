from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditPreparationRevision(Base):
    __tablename__ = "quality_audit_preparation_revisions"
    __table_args__ = (
        UniqueConstraint("amo_id", "audit_id", "revision_no", name="uq_quality_audit_preparation_revision"),
        CheckConstraint("revision_no >= 1", name="ck_quality_audit_preparation_revision_no"),
        CheckConstraint("status IN ('DRAFT','ISSUED')", name="ck_quality_audit_preparation_status"),
        Index("ix_quality_audit_preparation_audit", "amo_id", "audit_id", "revision_no"),
        Index("ix_quality_audit_preparation_status", "amo_id", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    revision_no = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False, default="DRAFT", server_default="DRAFT")
    preparation_scope = Column(Text, nullable=True)
    audit_snapshot = Column(JSON, nullable=False, default=dict)
    checklist_snapshot = Column(JSON, nullable=False, default=list)
    document_request_snapshot = Column(JSON, nullable=False, default=list)
    source_references = Column(JSON, nullable=False, default=list)
    source_fingerprint = Column(String(64), nullable=False)
    change_reason = Column(Text, nullable=False)
    supersedes_revision_id = Column(String(36), ForeignKey("quality_audit_preparation_revisions.id", ondelete="SET NULL"), nullable=True)
    issued_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    events = relationship(
        "QualityAuditPreparationEvent",
        back_populates="revision",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QualityAuditPreparationEvent.created_at",
        lazy="selectin",
    )


class QualityAuditPreparationEvent(Base):
    __tablename__ = "quality_audit_preparation_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('CREATED','ISSUED')", name="ck_quality_audit_preparation_event_type"),
        Index("ix_quality_audit_preparation_events", "amo_id", "audit_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("quality_audit_preparation_revisions.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(16), nullable=False)
    reason = Column(Text, nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    revision = relationship("QualityAuditPreparationRevision", back_populates="events", lazy="joined")
