from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditNoticePolicy(Base):
    __tablename__ = "quality_audit_notice_policies"
    __table_args__ = (
        UniqueConstraint("amo_id", "policy_code", name="uq_quality_audit_notice_policy_code"),
        CheckConstraint("minimum_notice_days >= 0", name="ck_quality_audit_notice_policy_days"),
        Index("ix_quality_audit_notice_policy_active", "amo_id", "is_active", "audit_kind"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    policy_code = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    audit_kind = Column(String(32), nullable=True)
    minimum_notice_days = Column(Integer, nullable=False, default=14, server_default="14")
    review_required = Column(Boolean, nullable=False, default=True, server_default="true")
    acknowledgement_required = Column(Boolean, nullable=False, default=True, server_default="true")
    emergency_exception_allowed = Column(Boolean, nullable=False, default=True, server_default="true")
    unannounced_exception_allowed = Column(Boolean, nullable=False, default=True, server_default="true")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class QualityAuditNotice(Base):
    __tablename__ = "quality_audit_notices"
    __table_args__ = (
        UniqueConstraint("amo_id", "audit_id", "revision_no", name="uq_quality_audit_notice_revision"),
        CheckConstraint("revision_no >= 1", name="ck_quality_audit_notice_revision_no"),
        CheckConstraint("required_notice_days >= 0", name="ck_quality_audit_notice_required_days"),
        CheckConstraint(
            "status IN ('DRAFT','UNDER_REVIEW','APPROVED','GENERATED','DELIVERED','ACKNOWLEDGED','SUPERSEDED','CANCELLED')",
            name="ck_quality_audit_notice_status",
        ),
        CheckConstraint(
            "exception_type IS NULL OR exception_type IN ('EMERGENCY','UNANNOUNCED')",
            name="ck_quality_audit_notice_exception_type",
        ),
        Index("ix_quality_audit_notice_audit", "amo_id", "audit_id", "revision_no"),
        Index("ix_quality_audit_notice_status", "amo_id", "status", "notice_date"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    policy_id = Column(String(36), ForeignKey("quality_audit_notice_policies.id", ondelete="SET NULL"), nullable=True)
    revision_no = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    required_notice_days = Column(Integer, nullable=False, default=14, server_default="14")
    notice_date = Column(Date, nullable=False)
    exception_type = Column(String(16), nullable=True)
    exception_reason = Column(Text, nullable=True)
    subject = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    audit_snapshot = Column(JSON, nullable=False, default=dict)
    recipient_snapshot = Column(JSON, nullable=False, default=list)
    delivery_channel = Column(String(32), nullable=True)
    delivery_reference = Column(String(512), nullable=True)
    supersedes_notice_id = Column(String(36), ForeignKey("quality_audit_notices.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    generated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=True)
    delivered_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    events = relationship(
        "QualityAuditNoticeEvent",
        back_populates="notice",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QualityAuditNoticeEvent.created_at",
        lazy="selectin",
    )


class QualityAuditNoticeEvent(Base):
    __tablename__ = "quality_audit_notice_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('CREATED','SUBMITTED','RETURNED','APPROVED','GENERATED','DELIVERED','ACKNOWLEDGED','REVISED','CANCELLED')",
            name="ck_quality_audit_notice_event_type",
        ),
        Index("ix_quality_audit_notice_events", "amo_id", "audit_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    notice_id = Column(String(36), ForeignKey("quality_audit_notices.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(24), nullable=False)
    reason = Column(Text, nullable=False)
    before_snapshot = Column(JSON, nullable=True)
    after_snapshot = Column(JSON, nullable=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    notice = relationship("QualityAuditNotice", back_populates="events", lazy="joined")
