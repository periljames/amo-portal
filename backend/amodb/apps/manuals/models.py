from __future__ import annotations

import enum
from datetime import datetime, date

from sqlalchemy import Boolean, Column, Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import JSON
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


class ManualRevisionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    DEPARTMENT_REVIEW = "DEPARTMENT_REVIEW"
    QUALITY_APPROVAL = "QUALITY_APPROVAL"
    REGULATOR_SIGNOFF = "REGULATOR_SIGNOFF"
    PUBLISHED = "PUBLISHED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class ManualSourceType(str, enum.Enum):
    DOCX = "DOCX"
    PDF = "PDF"


class ExportType(str, enum.Enum):
    PDF = "PDF"


class Tenant(Base):
    __tablename__ = "manual_tenants"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    slug = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    settings_json = Column(JSON, nullable=False, default=dict)


class Manual(Base):
    __tablename__ = "manuals"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_manual_code_tenant"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), ForeignKey("manual_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    manual_type = Column(String(64), nullable=False)
    owner_role = Column(String(64), nullable=False)
    current_published_rev_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(32), nullable=False, default="ACTIVE")


class ManualRevision(Base):
    __tablename__ = "manual_revisions"
    __table_args__ = (UniqueConstraint("manual_id", "rev_number", name="uq_manual_rev_number"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False, index=True)
    rev_number = Column(String(32), nullable=False)
    issue_number = Column(String(32), nullable=True)
    effective_date = Column(Date, nullable=True)
    status_enum = Column(Enum(ManualRevisionStatus, name="manual_revision_status_enum"), nullable=False, default=ManualRevisionStatus.DRAFT)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    published_at = Column(DateTime(timezone=True), nullable=True)
    superseded_by_rev_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="SET NULL"), nullable=True)
    requires_authority_approval_bool = Column(Boolean, nullable=False, default=False)
    authority_approval_ref = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    immutable_locked = Column(Boolean, nullable=False, default=False)


class ManualSection(Base):
    __tablename__ = "manual_sections"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_section_id = Column(String(36), ForeignKey("manual_sections.id", ondelete="SET NULL"), nullable=True)
    order_index = Column(Integer, nullable=False, default=0)
    heading = Column(String(255), nullable=False)
    anchor_slug = Column(String(255), nullable=False)
    level = Column(Integer, nullable=False, default=1)
    metadata_json = Column(JSON, nullable=False, default=dict)


class ManualBlock(Base):
    __tablename__ = "manual_blocks"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    section_id = Column(String(36), ForeignKey("manual_sections.id", ondelete="CASCADE"), nullable=False, index=True)
    order_index = Column(Integer, nullable=False, default=0)
    block_type = Column(String(64), nullable=False)
    html_sanitized = Column(Text, nullable=False)
    text_plain = Column(Text, nullable=False)
    change_hash = Column(String(128), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class RevisionDiffIndex(Base):
    __tablename__ = "revision_diff_index"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    baseline_revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="SET NULL"), nullable=True)
    computed_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    summary_json = Column(JSON, nullable=False, default=dict)


class Acknowledgement(Base):
    __tablename__ = "acknowledgements"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    holder_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    due_at = Column(DateTime(timezone=True), nullable=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledgement_text = Column(Text, nullable=True)
    evidence_uri = Column(Text, nullable=True)
    status_enum = Column(String(32), nullable=False, default="PENDING")


class PrintExport(Base):
    __tablename__ = "print_exports"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    export_type_enum = Column(Enum(ExportType, name="manual_export_type_enum"), nullable=False, default=ExportType.PDF)
    controlled_bool = Column(Boolean, nullable=False, default=False)
    watermark_uncontrolled_bool = Column(Boolean, nullable=False, default=True)
    generated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    storage_uri = Column(Text, nullable=False)
    sha256 = Column(String(64), nullable=False)
    render_profile_json = Column(JSON, nullable=False, default=dict)
    version_label = Column(String(64), nullable=True)


class PrintLog(Base):
    __tablename__ = "print_logs"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    export_id = Column(String(36), ForeignKey("print_exports.id", ondelete="CASCADE"), nullable=False, index=True)
    printed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    printed_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    printer_hint = Column(String(255), nullable=True)
    controlled_copy_no = Column(String(64), nullable=True)
    recipient = Column(String(255), nullable=True)
    purpose = Column(Text, nullable=True)
    status_enum = Column(String(32), nullable=False, default="ISSUED")
    notes = Column(Text, nullable=True)


class ManualAuditLog(Base):
    __tablename__ = "manual_audit_log"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), ForeignKey("manual_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(128), nullable=False)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(36), nullable=False)
    at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    ip_device = Column(String(255), nullable=True)
    diff_json = Column(JSON, nullable=False, default=dict)


class RegulationCatalog(Base):
    __tablename__ = "regulation_catalog"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), ForeignKey("manual_tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    authority = Column(String(64), nullable=False)
    instrument_name = Column(String(255), nullable=False)
    instrument_version = Column(String(64), nullable=False)
    citation_text = Column(Text, nullable=False)
    url_reference = Column(Text, nullable=True)


class RegulationRequirement(Base):
    __tablename__ = "regulation_requirements"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    catalog_id = Column(String(36), ForeignKey("regulation_catalog.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    requirement_text = Column(Text, nullable=False)
    applicability_tags = Column(JSON, nullable=False, default=list)


class ManualRequirementLink(Base):
    __tablename__ = "manual_requirement_links"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    section_id = Column(String(36), ForeignKey("manual_sections.id", ondelete="SET NULL"), nullable=True)
    block_id = Column(String(36), ForeignKey("manual_blocks.id", ondelete="SET NULL"), nullable=True)
    requirement_id = Column(String(36), ForeignKey("regulation_requirements.id", ondelete="CASCADE"), nullable=False)
    compliance_note = Column(Text, nullable=True)


class ManualAIHookEvent(Base):
    __tablename__ = "manual_ai_hook_events"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), ForeignKey("manual_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=True)
    event_name = Column(String(128), nullable=False)
    payload_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
