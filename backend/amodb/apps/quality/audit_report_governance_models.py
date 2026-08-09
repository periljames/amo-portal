from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditReportRevision(Base):
    __tablename__ = "quality_audit_report_revisions"
    __table_args__ = (
        UniqueConstraint("amo_id", "audit_id", "revision_no", name="uq_quality_audit_report_revision"),
        CheckConstraint("revision_no >= 1", name="ck_quality_audit_report_revision_no"),
        CheckConstraint(
            "status IN ('DRAFT','INTERNAL_REVIEW','APPROVED','ISSUED','SUPERSEDED','CANCELLED')",
            name="ck_quality_audit_report_revision_status",
        ),
        Index("ix_quality_audit_report_revision_audit", "amo_id", "audit_id", "revision_no"),
        Index("ix_quality_audit_report_revision_status", "amo_id", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    revision_no = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    file_ref = Column(String(1024), nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(128), nullable=True)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    report_snapshot = Column(JSON, nullable=False, default=dict)
    change_reason = Column(Text, nullable=False)
    supersedes_revision_id = Column(String(36), ForeignKey("quality_audit_report_revisions.id", ondelete="SET NULL"), nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    issued_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    events = relationship(
        "QualityAuditReportEvent",
        back_populates="revision",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QualityAuditReportEvent.created_at",
        lazy="selectin",
    )


class QualityAuditReportEvent(Base):
    __tablename__ = "quality_audit_report_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('ADOPTED','SUBMITTED','RETURNED','APPROVED','ISSUED','SUPERSEDED','CANCELLED')",
            name="ck_quality_audit_report_event_type",
        ),
        Index("ix_quality_audit_report_events", "amo_id", "audit_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("quality_audit_report_revisions.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(24), nullable=False)
    reason = Column(Text, nullable=False)
    before_snapshot = Column(JSON, nullable=True)
    after_snapshot = Column(JSON, nullable=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    revision = relationship("QualityAuditReportRevision", back_populates="events", lazy="joined")
