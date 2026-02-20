from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from amodb.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class DocControlSettings(Base):
    __tablename__ = "doc_control_settings"

    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), primary_key=True)
    default_retention_years = Column(Integer, nullable=False, default=5)
    default_review_interval_months = Column(Integer, nullable=False, default=24)
    regulated_workflow_enabled = Column(Boolean, nullable=False, default=False)
    default_ack_required = Column(Boolean, nullable=False, default=True)


class ControlledDocument(Base):
    __tablename__ = "doc_control_documents"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_id = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    doc_type = Column(String(64), nullable=False)
    owner_department = Column(String(128), nullable=False)
    issue_no = Column(Integer, nullable=False, default=1)
    revision_no = Column(Integer, nullable=False, default=0)
    version = Column(String(32), nullable=False, default="1.0")
    effective_date = Column(Date, nullable=True)
    status = Column(String(32), nullable=False, default="Draft")
    regulated_flag = Column(Boolean, nullable=False, default=False)
    authority_name = Column(String(255), nullable=True)
    authority_approval_status = Column(String(32), nullable=True)
    authority_evidence_asset_id = Column(String(255), nullable=True)
    restricted_flag = Column(Boolean, nullable=False, default=False)
    access_policy_id = Column(String(64), nullable=True)
    current_asset_id = Column(String(255), nullable=True)
    physical_locations = Column(JSONB, nullable=False, default=list)
    next_review_due = Column(Date, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("uq_doc_control_documents_tenant_doc_id", "tenant_id", "doc_id", unique=True),
    )


class Draft(Base):
    __tablename__ = "doc_control_drafts"

    draft_id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_id = Column(String(64), nullable=False)
    metadata_snapshot_json = Column(JSONB, nullable=False, default=dict)
    asset_id = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="Draft")
    authority_evidence_asset_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ChangeProposal(Base):
    __tablename__ = "doc_control_change_proposals"

    proposal_id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_id = Column(String(64), nullable=False)
    proposer_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    description = Column(Text, nullable=False)
    attachment_asset_ids = Column(JSONB, nullable=False, default=list)
    dept_head_decision = Column(String(64), nullable=True)
    quality_decision = Column(String(64), nullable=True)
    accountable_manager_decision = Column(String(64), nullable=True)
    authority_status = Column(String(64), nullable=True)
    authority_evidence_asset_ids = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class RevisionPackage(Base):
    __tablename__ = "doc_control_revision_packages"

    package_id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_id = Column(String(64), nullable=False)
    revision_no = Column(Integer, nullable=False)
    reference_serial_no = Column(String(128), nullable=False)
    change_summary = Column(Text, nullable=False)
    transmittal_notice = Column(Text, nullable=False)
    filing_instructions = Column(Text, nullable=False)
    replacement_pages = Column(JSONB, nullable=False, default=list)
    effective_date = Column(Date, nullable=False)
    internal_approval_status = Column(String(64), nullable=False, default="Pending")
    authority_status = Column(String(64), nullable=True)
    authority_evidence_asset_id = Column(String(255), nullable=True)
    published_at = Column(DateTime, nullable=True)
    published_revision_asset_id = Column(String(255), nullable=True)


class LEP(Base):
    __tablename__ = "doc_control_leps"

    lep_id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_id = Column(String(64), nullable=False)
    revision_no = Column(Integer, nullable=False)
    lep_date = Column(Date, nullable=False)
    rows = Column(JSONB, nullable=False, default=list)
    export_asset_id = Column(String(255), nullable=True)


class TemporaryRevision(Base):
    __tablename__ = "doc_control_temporary_revisions"

    tr_id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_id = Column(String(64), nullable=False)
    tr_no = Column(String(64), nullable=False)
    effective_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=False)
    reason = Column(Text, nullable=False)
    filing_instructions = Column(Text, nullable=False)
    updated_lep_asset_id = Column(String(255), nullable=True)
    tr_pages = Column(JSONB, nullable=False, default=list)
    status = Column(String(32), nullable=False, default="Draft")
    incorporated_revision_package_id = Column(String(36), nullable=True)


class DistributionListEntry(Base):
    __tablename__ = "doc_control_distribution_list_entries"

    entry_id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_id = Column(String(64), nullable=False)
    copy_no = Column(String(64), nullable=False)
    holder_name = Column(String(255), nullable=False)
    location_text = Column(String(255), nullable=False)
    format = Column(String(16), nullable=False)


class DistributionEvent(Base):
    __tablename__ = "doc_control_distribution_events"

    event_id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_id = Column(String(64), nullable=False)
    source_type = Column(String(32), nullable=False)
    source_id = Column(String(36), nullable=False)
    method = Column(String(32), nullable=False)
    sent_at = Column(DateTime, nullable=True)
    acknowledgement_required = Column(Boolean, nullable=False, default=True)
    status = Column(String(16), nullable=False, default="Draft")


class DistributionRecipient(Base):
    __tablename__ = "doc_control_distribution_recipients"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(String(36), ForeignKey("doc_control_distribution_events.event_id", ondelete="CASCADE"), nullable=False)
    recipient_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    copy_no = Column(String(64), nullable=True)


class Acknowledgement(Base):
    __tablename__ = "doc_control_acknowledgements"

    ack_id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(String(36), ForeignKey("doc_control_distribution_events.event_id", ondelete="CASCADE"), nullable=False)
    recipient_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    copy_no = Column(String(64), nullable=True)
    acknowledged_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    method = Column(String(32), nullable=False)
    evidence_asset_id = Column(String(255), nullable=True)


class ArchiveRecord(Base):
    __tablename__ = "doc_control_archive_records"

    archive_id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_id = Column(String(64), nullable=False)
    revision_no = Column(Integer, nullable=False)
    archived_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    archival_marking = Column(String(255), nullable=False)
    retention_until = Column(Date, nullable=False)
    disposal_status = Column(String(32), nullable=False, default="Retained")
    outsourced_vendor = Column(String(255), nullable=True)
    evidence_asset_id = Column(String(255), nullable=True)


class PeriodicReview(Base):
    __tablename__ = "doc_control_reviews"

    review_id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_id = Column(String(64), nullable=False)
    due_date = Column(Date, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    outcome = Column(String(32), nullable=True)
    actions = Column(JSONB, nullable=False, default=list)


class AuditEvent(Base):
    __tablename__ = "doc_control_audit_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    object_type = Column(String(64), nullable=False)
    object_id = Column(String(64), nullable=False)
    action = Column(String(32), nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    diff_json = Column(JSONB, nullable=False, default=dict)
