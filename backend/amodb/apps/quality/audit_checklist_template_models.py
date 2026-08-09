from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditChecklistTemplate(Base):
    __tablename__ = "quality_audit_checklist_templates"
    __table_args__ = (
        UniqueConstraint("amo_id", "template_code", name="uq_quality_audit_checklist_template_code"),
        CheckConstraint("status IN ('ACTIVE','RETIRED')", name="ck_quality_audit_checklist_template_status"),
        Index("ix_quality_audit_checklist_template_active", "amo_id", "status", "audit_kind"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    template_code = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(64), nullable=True)
    audit_kind = Column(String(32), nullable=True)
    status = Column(String(16), nullable=False, default="ACTIVE", server_default="ACTIVE")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    revisions = relationship("QualityAuditChecklistTemplateRevision", back_populates="template", lazy="selectin")


class QualityAuditChecklistTemplateRevision(Base):
    __tablename__ = "quality_audit_checklist_template_revisions"
    __table_args__ = (
        UniqueConstraint("amo_id", "template_id", "revision_no", name="uq_quality_audit_checklist_template_revision"),
        CheckConstraint("revision_no >= 1", name="ck_quality_audit_checklist_template_revision_no"),
        CheckConstraint("status IN ('DRAFT','ISSUED')", name="ck_quality_audit_checklist_template_revision_status"),
        Index("ix_quality_audit_checklist_template_revision", "amo_id", "template_id", "revision_no"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    template_id = Column(String(36), ForeignKey("quality_audit_checklist_templates.id", ondelete="CASCADE"), nullable=False)
    revision_no = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False, default="DRAFT", server_default="DRAFT")
    items = Column(JSON, nullable=False, default=list)
    source_references = Column(JSON, nullable=False, default=list)
    content_sha256 = Column(String(64), nullable=False)
    change_reason = Column(Text, nullable=False)
    supersedes_revision_id = Column(String(36), ForeignKey("quality_audit_checklist_template_revisions.id", ondelete="SET NULL"), nullable=True)
    issued_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    template = relationship("QualityAuditChecklistTemplate", back_populates="revisions", lazy="joined")


class QualityAuditChecklistBinding(Base):
    __tablename__ = "quality_audit_checklist_bindings"
    __table_args__ = (
        UniqueConstraint("amo_id", "audit_id", "template_revision_id", name="uq_quality_audit_checklist_binding"),
        Index("ix_quality_audit_checklist_binding_audit", "amo_id", "audit_id", "applied_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    template_id = Column(String(36), ForeignKey("quality_audit_checklist_templates.id", ondelete="RESTRICT"), nullable=False)
    template_revision_id = Column(String(36), ForeignKey("quality_audit_checklist_template_revisions.id", ondelete="RESTRICT"), nullable=False)
    template_code = Column(String(64), nullable=False)
    revision_no = Column(Integer, nullable=False)
    content_sha256 = Column(String(64), nullable=False)
    item_snapshot = Column(JSON, nullable=False, default=list)
    source_references = Column(JSON, nullable=False, default=list)
    instantiated_item_ids = Column(JSON, nullable=False, default=list)
    application_reason = Column(Text, nullable=False)
    applied_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
