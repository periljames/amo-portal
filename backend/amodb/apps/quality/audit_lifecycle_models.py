from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from amodb.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditChecklistDocument(Base):
    """Immutable version record for an audit checklist source or filled copy."""

    __tablename__ = "quality_audit_checklist_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    audit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_audits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number = Column(Integer, nullable=False)
    parent_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("quality_audit_checklist_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    filename = Column(String(255), nullable=False)
    storage_key = Column(String(1024), nullable=False)
    content_type = Column(String(128), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    source_type = Column(String(32), nullable=False, default="UPLOAD")
    fillable = Column(String(16), nullable=False, default="UNKNOWN")
    field_count = Column(Integer, nullable=True)
    lifecycle_status = Column(String(32), nullable=False, default="SOURCE", index=True)
    uploaded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    committed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    superseded_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("audit_id", "version_number", name="uq_quality_audit_checklist_version"),
        Index("ix_quality_audit_checklist_audit_status", "audit_id", "lifecycle_status"),
        Index("ix_quality_audit_checklist_audit_created", "audit_id", "created_at"),
        CheckConstraint("version_number > 0", name="ck_quality_audit_checklist_version_positive"),
        CheckConstraint("size_bytes > 0", name="ck_quality_audit_checklist_size_positive"),
        CheckConstraint("field_count IS NULL OR field_count >= 0", name="ck_quality_audit_checklist_field_count_nonnegative"),
        CheckConstraint(
            "lifecycle_status IN ('SOURCE','WORKING_DRAFT','COMMITTED','SUPERSEDED','RETAINED')",
            name="ck_quality_audit_checklist_lifecycle",
        ),
        CheckConstraint(
            "fillable IN ('UNKNOWN','YES','NO')",
            name="ck_quality_audit_checklist_fillable",
        ),
    )


class QualityAuditReportDocument(Base):
    """Versioned report record separating uploaded drafts from issued reports."""

    __tablename__ = "quality_audit_report_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    audit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_audits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number = Column(Integer, nullable=False)
    parent_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("quality_audit_report_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    filename = Column(String(255), nullable=False)
    storage_key = Column(String(1024), nullable=False)
    content_type = Column(String(128), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    lifecycle_status = Column(String(32), nullable=False, default="DRAFT", index=True)
    issue_label = Column(String(64), nullable=True)
    uploaded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    issued_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    issued_at = Column(DateTime(timezone=True), nullable=True, index=True)
    superseded_at = Column(DateTime(timezone=True), nullable=True)
    distribution_status = Column(String(32), nullable=False, default="NOT_DISTRIBUTED")

    __table_args__ = (
        UniqueConstraint("audit_id", "version_number", name="uq_quality_audit_report_version"),
        Index("ix_quality_audit_report_audit_status", "audit_id", "lifecycle_status"),
        Index("ix_quality_audit_report_audit_issued", "audit_id", "issued_at"),
        CheckConstraint("version_number > 0", name="ck_quality_audit_report_version_positive"),
        CheckConstraint("size_bytes > 0", name="ck_quality_audit_report_size_positive"),
        CheckConstraint(
            "lifecycle_status IN ('DRAFT','ISSUED','SUPERSEDED','RETAINED')",
            name="ck_quality_audit_report_lifecycle",
        ),
        CheckConstraint(
            "distribution_status IN ('NOT_DISTRIBUTED','PARTIAL','DISTRIBUTED')",
            name="ck_quality_audit_report_distribution",
        ),
    )


class QualityAuditStageRecord(Base):
    """Explicit controlled stage transitions; navigation never writes these rows."""

    __tablename__ = "quality_audit_stage_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    audit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_audits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_id = Column(String(32), nullable=False)
    state = Column(String(32), nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    note = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)

    __table_args__ = (
        Index("ix_quality_audit_stage_audit_stage_time", "audit_id", "stage_id", "occurred_at"),
        CheckConstraint(
            "stage_id IN ('war-room','checklist','findings','cars','evidence','report','closeout')",
            name="ck_quality_audit_stage_id",
        ),
        CheckConstraint(
            "state IN ('NOT_READY','READY','IN_PROGRESS','BLOCKED','COMPLETE','LOCKED')",
            name="ck_quality_audit_stage_state",
        ),
    )


class QualityAuditEvidenceReview(Base):
    """Auditor verification decision for checklist, finding, CAR or report evidence."""

    __tablename__ = "quality_audit_evidence_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    audit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_audits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type = Column(String(32), nullable=False)
    entity_id = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="PENDING", index=True)
    note = Column(Text, nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("audit_id", "entity_type", "entity_id", name="uq_quality_audit_evidence_entity"),
        Index("ix_quality_audit_evidence_audit_status", "audit_id", "status"),
        CheckConstraint(
            "entity_type IN ('CHECKLIST_VERSION','FINDING_ATTACHMENT','CAR_ATTACHMENT','REPORT_VERSION','OTHER')",
            name="ck_quality_audit_evidence_entity_type",
        ),
        CheckConstraint(
            "status IN ('PENDING','ACCEPTED','REJECTED')",
            name="ck_quality_audit_evidence_status",
        ),
    )
