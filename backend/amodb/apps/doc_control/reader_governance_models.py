"""Version-bound reader governance, evidence and migration records."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from amodb.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.utcnow()


class DocumentAnnotationMigration(Base):
    """Human-governed migration of one annotation between immutable revisions."""

    __tablename__ = "document_annotation_migrations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_annotation_id",
            "target_revision_id",
            name="uq_doc_annotation_migration_target",
        ),
        Index("ix_doc_annotation_migration_review", "tenant_id", "status", "target_revision_id"),
        Index("ix_doc_annotation_migration_source", "source_annotation_id", "source_revision_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    source_annotation_id = Column(String(36), ForeignKey("document_annotations.id", ondelete="CASCADE"), nullable=False)
    source_revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False)
    target_revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False)
    proposed_location_json = Column(JSONB, nullable=False, default=dict)
    migration_strategy = Column(String(32), nullable=False)
    confidence_percent = Column(Integer, nullable=False, default=0)
    status = Column(String(24), nullable=False, default="PENDING")
    reason = Column(Text, nullable=True)
    target_annotation_id = Column(String(36), ForeignKey("document_annotations.id", ondelete="SET NULL"), nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DocumentEvidenceSnapshot(Base):
    """Immutable evidence package proving the controlled revision state at a point in time."""

    __tablename__ = "document_evidence_snapshots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "snapshot_sha256", name="uq_doc_evidence_snapshot_sha"),
        Index("ix_doc_evidence_revision_created", "tenant_id", "revision_id", "created_at"),
        Index("ix_doc_evidence_manual_created", "tenant_id", "manual_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False)
    source_sha256 = Column(String(64), nullable=True)
    snapshot_sha256 = Column(String(64), nullable=False)
    schema_version = Column(Integer, nullable=False, default=1)
    payload_json = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
