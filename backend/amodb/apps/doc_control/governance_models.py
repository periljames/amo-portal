from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from amodb.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.utcnow()


class DocumentResponsibilityAssignment(Base):
    """Effective-dated, attributable responsibility for one governed document.

    This intentionally does not collapse controller, owner, reviewer and approver
    into the legacy profile owner string. Inferred rows remain suggestions until a
    controller confirms them.
    """

    __tablename__ = "document_responsibility_assignments"
    __table_args__ = (
        CheckConstraint("confidence_percent >= 0 AND confidence_percent <= 100", name="ck_doc_resp_confidence"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_doc_resp_effective_period"),
        CheckConstraint(
            "(CASE WHEN assignee_user_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN assignee_department_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN assignee_org_unit_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN assignee_role IS NULL THEN 0 ELSE 1 END) = 1",
            name="ck_doc_resp_one_assignee",
        ),
        Index("ix_doc_resp_tenant_manual_type", "tenant_id", "manual_id", "responsibility_type"),
        Index("ix_doc_resp_tenant_status", "tenant_id", "confirmation_status", "responsibility_type"),
        Index("ix_doc_resp_user_effective", "assignee_user_id", "effective_from", "effective_to"),
        Index("ix_doc_resp_department_effective", "assignee_department_id", "effective_from", "effective_to"),
        Index("ix_doc_resp_org_effective", "assignee_org_unit_id", "effective_from", "effective_to"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=True)
    responsibility_type = Column(String(48), nullable=False)
    assignee_type = Column(String(24), nullable=False)
    assignee_user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    assignee_department_id = Column(String(36), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=True)
    assignee_org_unit_id = Column(String(36), ForeignKey("workforce_org_units.id", ondelete="RESTRICT"), nullable=True)
    assignee_role = Column(String(96), nullable=True)
    is_primary = Column(Boolean, nullable=False, default=True)
    delegated_from_id = Column(
        String(36),
        ForeignKey("document_responsibility_assignments.id", ondelete="SET NULL"),
        nullable=True,
    )
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    assignment_source = Column(String(24), nullable=False, default="MANUAL")
    confidence_percent = Column(Integer, nullable=False, default=100)
    confirmation_status = Column(String(24), nullable=False, default="CONFIRMED")
    provenance_json = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    superseded_by_id = Column(
        String(36),
        ForeignKey("document_responsibility_assignments.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DocumentLocation(Base):
    """Format-neutral immutable source location used by links and annotations."""

    __tablename__ = "document_locations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "revision_id", "location_key", name="uq_document_location_revision_key"),
        Index("ix_document_location_revision_page", "revision_id", "page_number"),
        Index("ix_document_location_checksum", "source_sha256", "location_type"),
        Index("ix_document_location_section", "section_id", "block_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False)
    source_sha256 = Column(String(64), nullable=False)
    location_key = Column(String(128), nullable=False)
    location_type = Column(String(32), nullable=False)
    page_number = Column(Integer, nullable=True)
    normalized_rects_json = Column(JSONB, nullable=False, default=list)
    exact_quote = Column(Text, nullable=True)
    prefix_context = Column(Text, nullable=True)
    suffix_context = Column(Text, nullable=True)
    section_id = Column(String(36), ForeignKey("manual_sections.id", ondelete="SET NULL"), nullable=True)
    block_id = Column(String(36), ForeignKey("manual_blocks.id", ondelete="SET NULL"), nullable=True)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    sheet_name = Column(String(255), nullable=True)
    cell_range = Column(String(128), nullable=True)
    slide_number = Column(Integer, nullable=True)
    object_id = Column(String(255), nullable=True)
    image_region_json = Column(JSONB, nullable=False, default=dict)
    adapter_name = Column(String(64), nullable=False)
    adapter_version = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class DocumentGovernedRelationship(Base):
    """Typed, provenance-preserving relation from a document occurrence to an entity."""

    __tablename__ = "document_governed_relationships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "occurrence_key", name="uq_doc_relationship_occurrence"),
        CheckConstraint("confidence_percent >= 0 AND confidence_percent <= 100", name="ck_doc_rel_confidence"),
        Index("ix_doc_rel_source", "tenant_id", "source_manual_id", "relationship_type"),
        Index("ix_doc_rel_target_manual", "tenant_id", "target_manual_id", "relationship_type"),
        Index("ix_doc_rel_target_entity", "tenant_id", "target_entity_type", "target_entity_id"),
        Index("ix_doc_rel_resolution", "tenant_id", "resolution_status", "relationship_type"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    source_manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    source_revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=True)
    source_location_id = Column(String(36), ForeignKey("document_locations.id", ondelete="SET NULL"), nullable=True)
    target_entity_type = Column(String(48), nullable=False)
    target_entity_id = Column(String(128), nullable=True)
    target_manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="SET NULL"), nullable=True)
    target_revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="SET NULL"), nullable=True)
    relationship_type = Column(String(48), nullable=False)
    relationship_source = Column(String(24), nullable=False, default="MANUAL")
    occurrence_key = Column(String(128), nullable=False)
    exact_token = Column(String(255), nullable=True)
    exact_quote = Column(Text, nullable=True)
    page_number = Column(Integer, nullable=True)
    section_label = Column(String(255), nullable=True)
    confidence_percent = Column(Integer, nullable=False, default=100)
    resolution_status = Column(String(24), nullable=False, default="CONFIRMED")
    provenance_json = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    superseded_by_id = Column(
        String(36),
        ForeignKey("document_governed_relationships.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DocumentAnnotation(Base):
    __tablename__ = "document_annotations"
    __table_args__ = (
        Index("ix_doc_annotation_revision_visibility", "tenant_id", "revision_id", "visibility"),
        Index("ix_doc_annotation_creator", "tenant_id", "created_by_user_id", "created_at"),
        Index("ix_doc_annotation_link", "tenant_id", "linked_entity_type", "linked_entity_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False)
    location_id = Column(String(36), ForeignKey("document_locations.id", ondelete="RESTRICT"), nullable=False)
    source_sha256 = Column(String(64), nullable=False)
    annotation_type = Column(String(32), nullable=False)
    color = Column(String(16), nullable=False, default="YELLOW")
    visibility = Column(String(24), nullable=False, default="PRIVATE")
    note_text = Column(Text, nullable=True)
    tags_json = Column(JSONB, nullable=False, default=list)
    linked_entity_type = Column(String(48), nullable=True)
    linked_entity_id = Column(String(128), nullable=True)
    status = Column(String(24), nullable=False, default="ACTIVE")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DocumentGovernanceBackfillRun(Base):
    __tablename__ = "document_governance_backfill_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_doc_backfill_tenant_key"),
        Index("ix_doc_backfill_status", "tenant_id", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    scope_json = Column(JSONB, nullable=False, default=dict)
    status = Column(String(24), nullable=False, default="QUEUED")
    dry_run = Column(Boolean, nullable=False, default=True)
    total_count = Column(Integer, nullable=False, default=0)
    processed_count = Column(Integer, nullable=False, default=0)
    succeeded_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    reconciliation_json = Column(JSONB, nullable=False, default=dict)
    last_error = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DocumentGovernanceBackfillItem(Base):
    __tablename__ = "document_governance_backfill_items"
    __table_args__ = (
        UniqueConstraint("run_id", "manual_id", name="uq_doc_backfill_item_manual"),
        Index("ix_doc_backfill_item_status", "run_id", "status", "sequence"),
        Index("ix_doc_backfill_item_tenant_manual", "tenant_id", "manual_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(String(36), ForeignKey("document_governance_backfill_runs.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="SET NULL"), nullable=True)
    sequence = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False, default="PENDING")
    attempt_count = Column(Integer, nullable=False, default=0)
    action_json = Column(JSONB, nullable=False, default=dict)
    result_json = Column(JSONB, nullable=False, default=dict)
    error_summary = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
