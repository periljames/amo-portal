from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from amodb.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.utcnow()


class DocumentationNode(Base):
    """One governed node in the tenant's documented-information hierarchy.

    A node may be a grouping/root or may bind to the canonical manuals.Manual
    record. Keeping hierarchy separate from the controlled document prevents a
    folder move from mutating an approved publication revision.
    """

    __tablename__ = "documentation_nodes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "normalized_code", name="uq_documentation_node_tenant_code"),
        UniqueConstraint("tenant_id", "manual_id", name="uq_documentation_node_tenant_manual"),
        Index("ix_documentation_nodes_tenant_parent_order", "tenant_id", "parent_id", "order_index"),
        Index("ix_documentation_nodes_tenant_type", "tenant_id", "node_type"),
        Index("ix_documentation_nodes_tenant_path", "tenant_id", "path"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(String(36), ForeignKey("documentation_nodes.id", ondelete="RESTRICT"), nullable=True)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="SET NULL"), nullable=True)
    node_type = Column(String(40), nullable=False)
    code = Column(String(128), nullable=False)
    normalized_code = Column(String(128), nullable=False)
    title = Column(String(255), nullable=False)
    path = Column(String(2048), nullable=False)
    depth = Column(Integer, nullable=False, default=0)
    order_index = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="ACTIVE")
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DocumentationExecutionProfile(Base):
    """Defines how a controlled form/checklist/template can be executed."""

    __tablename__ = "documentation_execution_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "manual_id", name="uq_documentation_execution_tenant_manual"),
        Index("ix_documentation_execution_tenant_type", "tenant_id", "execution_type"),
        Index("ix_documentation_execution_record_series", "record_series_node_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    execution_type = Column(String(40), nullable=False, default="NONE")
    submission_mode = Column(String(40), nullable=False, default="DOWNLOAD_ONLY")
    record_series_node_id = Column(String(36), ForeignKey("documentation_nodes.id", ondelete="SET NULL"), nullable=True)
    retention_years = Column(Integer, nullable=True)
    naming_pattern = Column(String(255), nullable=False, default="{code}-{date}-{sequence}")
    allow_download = Column(Boolean, nullable=False, default=True)
    allow_save_draft = Column(Boolean, nullable=False, default=False)
    requires_signature = Column(Boolean, nullable=False, default=False)
    requires_review = Column(Boolean, nullable=False, default=False)
    schema_json = Column(JSONB, nullable=False, default=dict)
    access_scope_json = Column(JSONB, nullable=False, default=dict)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DocumentationReference(Base):
    """Version-aware link from an exact source occurrence to controlled content."""

    __tablename__ = "documentation_references"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_revision_id",
            "occurrence_key",
            name="uq_documentation_reference_occurrence",
        ),
        Index("ix_documentation_references_source_page", "source_revision_id", "source_page_number"),
        Index("ix_documentation_references_source_section", "source_section_id", "source_block_id"),
        Index("ix_documentation_references_target_manual", "target_manual_id", "status"),
        Index("ix_documentation_references_tenant_status", "tenant_id", "status"),
        Index("ix_documentation_references_normalized_token", "tenant_id", "normalized_token"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    source_manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    source_revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False)
    source_section_id = Column(String(36), ForeignKey("manual_sections.id", ondelete="SET NULL"), nullable=True)
    source_block_id = Column(String(36), ForeignKey("manual_blocks.id", ondelete="SET NULL"), nullable=True)
    source_page_number = Column(Integer, nullable=True)
    source_char_start = Column(Integer, nullable=True)
    source_char_end = Column(Integer, nullable=True)
    source_bbox_json = Column(JSONB, nullable=False, default=dict)
    source_quote = Column(Text, nullable=False)
    source_context = Column(Text, nullable=True)
    source_change_hash = Column(String(128), nullable=True)
    occurrence_key = Column(String(128), nullable=False)
    raw_token = Column(String(255), nullable=False)
    normalized_token = Column(String(128), nullable=False)
    relationship_type = Column(String(40), nullable=False, default="REFERENCES")
    resolution_policy = Column(String(40), nullable=False, default="CURRENT_EFFECTIVE")
    target_manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="SET NULL"), nullable=True)
    target_revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="SET NULL"), nullable=True)
    target_section_id = Column(String(36), ForeignKey("manual_sections.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(32), nullable=False, default="UNRESOLVED")
    confidence_percent = Column(Integer, nullable=False, default=0)
    detection_method = Column(String(40), nullable=False, default="TEXT_ALIAS")
    candidates_json = Column(JSONB, nullable=False, default=list)
    verified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DocumentationIndexJob(Base):
    """Observable, idempotent indexing state for one source revision."""

    __tablename__ = "documentation_index_jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "revision_id", name="uq_documentation_index_tenant_revision"),
        Index("ix_documentation_index_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_documentation_index_jobs_revision_checksum", "revision_id", "source_sha256"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False)
    source_sha256 = Column(String(64), nullable=True)
    index_version = Column(Integer, nullable=False, default=1)
    status = Column(String(32), nullable=False, default="PENDING")
    detected_count = Column(Integer, nullable=False, default=0)
    resolved_count = Column(Integer, nullable=False, default=0)
    unresolved_count = Column(Integer, nullable=False, default=0)
    broken_count = Column(Integer, nullable=False, default=0)
    error_summary = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DocumentationRecord(Base):
    """Immutable output created from an executable controlled template."""

    __tablename__ = "documentation_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "record_number", name="uq_documentation_record_tenant_number"),
        Index("ix_documentation_records_template_revision", "template_revision_id", "submitted_at"),
        Index("ix_documentation_records_series_status", "record_series_node_id", "status"),
        Index("ix_documentation_records_tenant_submitter", "tenant_id", "submitted_by_user_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    record_number = Column(String(128), nullable=False)
    template_manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="RESTRICT"), nullable=False)
    template_revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="RESTRICT"), nullable=False)
    source_reference_id = Column(String(36), ForeignKey("documentation_references.id", ondelete="SET NULL"), nullable=True)
    record_series_node_id = Column(String(36), ForeignKey("documentation_nodes.id", ondelete="SET NULL"), nullable=True)
    source_context_json = Column(JSONB, nullable=False, default=dict)
    payload_json = Column(JSONB, nullable=False, default=dict)
    artifact_storage_path = Column(Text, nullable=False)
    artifact_filename = Column(String(255), nullable=False)
    artifact_mime_type = Column(String(128), nullable=False, default="application/pdf")
    artifact_sha256 = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="SUBMITTED")
    retention_years = Column(Integer, nullable=True)
    retention_disposition = Column(String(64), nullable=False, default="REVIEW_AT_EXPIRY")
    submitted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
