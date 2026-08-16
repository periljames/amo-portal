from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditRetentionPolicyRevision(Base):
    __tablename__ = "quality_audit_retention_policy_revisions"
    __table_args__ = (
        UniqueConstraint("amo_id", "revision_no", name="uq_quality_audit_retention_policy_revision"),
        CheckConstraint("revision_no >= 1", name="ck_quality_audit_retention_policy_revision_no"),
        CheckConstraint("record_type = 'AUDIT_PACKAGE'", name="ck_quality_audit_retention_record_type"),
        CheckConstraint(
            "retention_start_event IN ('EXECUTION_CLOSED','FOLLOW_UP_COMPLETE')",
            name="ck_quality_audit_retention_start_event",
        ),
        CheckConstraint(
            "disposition_mode IN ('PRESERVE_METADATA_DELETE_PACKAGE','TRANSFER_PACKAGE','NO_DISPOSITION')",
            name="ck_quality_audit_retention_disposition_mode",
        ),
        CheckConstraint(
            "(indefinite IS TRUE AND duration_days IS NULL) OR (indefinite IS FALSE AND duration_days IS NOT NULL AND duration_days > 0)",
            name="ck_quality_audit_retention_duration_rule",
        ),
        Index("ix_quality_audit_retention_policy_latest", "amo_id", "revision_no"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    revision_no = Column(Integer, nullable=False)
    retention_class = Column(String(96), nullable=False)
    record_type = Column(String(32), nullable=False, default="AUDIT_PACKAGE", server_default="AUDIT_PACKAGE")
    retention_start_event = Column(String(32), nullable=False)
    duration_days = Column(Integer, nullable=True)
    indefinite = Column(Boolean, nullable=False, default=False, server_default="false")
    governing_basis = Column(Text, nullable=False)
    review_before_disposition = Column(Boolean, nullable=False, default=True, server_default="true")
    legal_hold_supported = Column(Boolean, nullable=False, default=True, server_default="true")
    disposition_mode = Column(String(48), nullable=False)
    approving_capability = Column(String(128), nullable=False)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class QualityAuditArchiveManifest(Base):
    __tablename__ = "quality_audit_archive_manifests"
    __table_args__ = (
        UniqueConstraint("amo_id", "audit_id", "manifest_version", name="uq_quality_audit_archive_manifest_version"),
        CheckConstraint("manifest_version >= 1", name="ck_quality_audit_archive_manifest_version"),
        CheckConstraint("item_count >= 0", name="ck_quality_audit_archive_manifest_item_count"),
        Index("ix_quality_audit_archive_manifest_latest", "amo_id", "audit_id", "manifest_version"),
        Index("ix_quality_audit_archive_manifest_due", "amo_id", "retention_due_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    manifest_version = Column(Integer, nullable=False)
    retention_policy_revision_id = Column(String(36), ForeignKey("quality_audit_retention_policy_revisions.id", ondelete="RESTRICT"), nullable=False)
    retention_class = Column(String(96), nullable=False)
    retention_start_at = Column(DateTime(timezone=True), nullable=False)
    retention_due_at = Column(DateTime(timezone=True), nullable=True)
    manifest_json = Column(JSON, nullable=False)
    manifest_sha256 = Column(String(64), nullable=False)
    item_count = Column(Integer, nullable=False)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    items = relationship(
        "QualityAuditArchiveManifestItem",
        back_populates="manifest",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QualityAuditArchiveManifestItem.created_at",
        lazy="selectin",
    )


class QualityAuditArchiveManifestItem(Base):
    __tablename__ = "quality_audit_archive_manifest_items"
    __table_args__ = (
        Index("ix_quality_audit_archive_item_manifest", "amo_id", "audit_id", "manifest_id", "item_type"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    manifest_id = Column(String(36), ForeignKey("quality_audit_archive_manifests.id", ondelete="CASCADE"), nullable=False)
    item_type = Column(String(64), nullable=False)
    authoritative_record_id = Column(String(255), nullable=False)
    revision_ref = Column(String(255), nullable=True)
    source_system = Column(String(96), nullable=False)
    content_hash = Column(String(64), nullable=True)
    retention_role = Column(String(96), nullable=False)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    manifest = relationship("QualityAuditArchiveManifest", back_populates="items", lazy="joined")


class QualityAuditLegalHoldEvent(Base):
    __tablename__ = "quality_audit_legal_hold_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('PLACED','RELEASED')", name="ck_quality_audit_legal_hold_event_type"),
        Index("ix_quality_audit_legal_hold_latest", "amo_id", "audit_id", "hold_key", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    manifest_id = Column(String(36), ForeignKey("quality_audit_archive_manifests.id", ondelete="SET NULL"), nullable=True)
    hold_key = Column(String(128), nullable=False)
    event_type = Column(String(16), nullable=False)
    reason = Column(Text, nullable=False)
    governing_basis = Column(Text, nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class QualityAuditDispositionEvent(Base):
    __tablename__ = "quality_audit_disposition_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('APPROVED','REJECTED','EXECUTED')", name="ck_quality_audit_disposition_event_type"),
        Index("ix_quality_audit_disposition_events", "amo_id", "audit_id", "manifest_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    manifest_id = Column(String(36), ForeignKey("quality_audit_archive_manifests.id", ondelete="RESTRICT"), nullable=False)
    event_type = Column(String(16), nullable=False)
    disposition_mode = Column(String(48), nullable=False)
    inventory_sha256 = Column(String(64), nullable=False)
    reason = Column(Text, nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
