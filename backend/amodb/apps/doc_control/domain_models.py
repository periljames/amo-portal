from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from amodb.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.utcnow()


class DocumentControlProfile(Base):
    """Governance metadata attached to the canonical manuals.Manual record."""

    __tablename__ = "document_control_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "manual_id", name="uq_document_control_profile_tenant_manual"),
        Index("ix_document_control_profiles_tenant_class", "tenant_id", "document_class"),
        Index("ix_document_control_profiles_tenant_review", "tenant_id", "next_review_due"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    document_class = Column(String(32), nullable=False, default="INTERNAL")
    owner_department = Column(String(128), nullable=False, default="DOCUMENT_CONTROL")
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    language = Column(String(32), nullable=False, default="English")
    criticality = Column(String(32), nullable=False, default="STANDARD")
    regulated_flag = Column(Boolean, nullable=False, default=False)
    restricted_flag = Column(Boolean, nullable=False, default=False)
    requires_authority_approval = Column(Boolean, nullable=False, default=False)
    acknowledgement_required = Column(Boolean, nullable=False, default=True)
    review_interval_months = Column(Integer, nullable=False, default=24)
    next_review_due = Column(Date, nullable=True)
    access_scope_json = Column(JSONB, nullable=False, default=dict)
    tags_json = Column(JSONB, nullable=False, default=list)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DocumentChangeRequest(Base):
    __tablename__ = "document_change_requests"
    __table_args__ = (
        Index("ix_document_change_requests_tenant_status", "tenant_id", "status"),
        Index("ix_document_change_requests_manual_status", "manual_id", "status"),
        Index("ix_document_change_requests_source", "source_module", "source_entity_type", "source_entity_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="SET NULL"), nullable=True)
    source_module = Column(String(64), nullable=False, default="DOCUMENT_CONTROL")
    source_entity_type = Column(String(64), nullable=True)
    source_entity_id = Column(String(128), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(String(16), nullable=False, default="NORMAL")
    status = Column(String(32), nullable=False, default="OPEN")
    proposer_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    impact_json = Column(JSONB, nullable=False, default=dict)
    training_impact_required = Column(Boolean, nullable=False, default=False)
    qms_blocking = Column(Boolean, nullable=False, default=False)
    resolution = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    closed_at = Column(DateTime(timezone=True), nullable=True)


class DocumentWorkflowInstance(Base):
    __tablename__ = "document_workflow_instances"
    __table_args__ = (
        UniqueConstraint("tenant_id", "revision_id", name="uq_document_workflow_tenant_revision"),
        Index("ix_document_workflows_tenant_state", "tenant_id", "state"),
        Index("ix_document_workflows_manual_state", "manual_id", "state"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False)
    state = Column(String(48), nullable=False, default="DRAFT")
    requires_authority = Column(Boolean, nullable=False, default=False)
    training_impact_required = Column(Boolean, nullable=False, default=False)
    training_readiness_status = Column(String(32), nullable=False, default="NOT_REQUIRED")
    qms_readiness_status = Column(String(32), nullable=False, default="NOT_REQUIRED")
    distribution_readiness_status = Column(String(32), nullable=False, default="NOT_REQUIRED")
    effective_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DocumentWorkflowDecision(Base):
    __tablename__ = "document_workflow_decisions"
    __table_args__ = (
        Index("ix_document_workflow_decisions_workflow", "workflow_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    workflow_id = Column(String(36), ForeignKey("document_workflow_instances.id", ondelete="CASCADE"), nullable=False)
    step_code = Column(String(64), nullable=False)
    decision = Column(String(32), nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    from_state = Column(String(48), nullable=False)
    to_state = Column(String(48), nullable=False)
    comments = Column(Text, nullable=True)
    evidence_json = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class DocumentAuthoritySubmission(Base):
    __tablename__ = "document_authority_submissions"
    __table_args__ = (
        Index("ix_document_authority_tenant_status", "tenant_id", "status"),
        Index("ix_document_authority_revision", "revision_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False)
    workflow_id = Column(String(36), ForeignKey("document_workflow_instances.id", ondelete="SET NULL"), nullable=True)
    authority_name = Column(String(255), nullable=False)
    submission_reference = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="DRAFT")
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    submitted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    response_due_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    response_summary = Column(Text, nullable=True)
    evidence_json = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DocumentTemporaryRevision(Base):
    __tablename__ = "document_temporary_revisions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "manual_id", "tr_number", name="uq_document_tr_tenant_manual_number"),
        Index("ix_document_tr_tenant_status_expiry", "tenant_id", "status", "expiry_date"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    base_revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="SET NULL"), nullable=True)
    tr_number = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    reason = Column(Text, nullable=False)
    affected_sections_json = Column(JSONB, nullable=False, default=list)
    filing_instructions = Column(Text, nullable=True)
    effective_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=False)
    status = Column(String(32), nullable=False, default="DRAFT")
    approval_status = Column(String(32), nullable=False, default="PENDING")
    distribution_campaign_id = Column(String(36), nullable=True)
    incorporated_revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="SET NULL"), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DocumentDistributionCampaign(Base):
    __tablename__ = "document_distribution_campaigns"
    __table_args__ = (
        Index("ix_document_distribution_tenant_status", "tenant_id", "status"),
        Index("ix_document_distribution_revision", "revision_id", "issued_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False)
    temporary_revision_id = Column(String(36), ForeignKey("document_temporary_revisions.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    audience_json = Column(JSONB, nullable=False, default=dict)
    acknowledgement_required = Column(Boolean, nullable=False, default=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), nullable=False, default="DRAFT")
    issued_at = Column(DateTime(timezone=True), nullable=True)
    issued_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DocumentDistributionRecipient(Base):
    __tablename__ = "document_distribution_campaign_recipients"
    __table_args__ = (
        Index("ix_document_distribution_recipient_campaign_status", "campaign_id", "status"),
        Index("ix_document_distribution_recipient_user_status", "recipient_user_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    campaign_id = Column(String(36), ForeignKey("document_distribution_campaigns.id", ondelete="CASCADE"), nullable=False)
    recipient_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    copy_number = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="PENDING")
    due_at = Column(DateTime(timezone=True), nullable=True)
    notified_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    reminder_count = Column(Integer, nullable=False, default=0)
    last_reminded_at = Column(DateTime(timezone=True), nullable=True)
    exemption_reason = Column(Text, nullable=True)
    evidence_json = Column(JSONB, nullable=False, default=list)


class DocumentReviewPlan(Base):
    __tablename__ = "document_review_plans"
    __table_args__ = (
        Index("ix_document_review_plans_tenant_status_due", "tenant_id", "status", "due_at"),
        Index("ix_document_review_plans_manual", "manual_id", "due_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="SET NULL"), nullable=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(32), nullable=False, default="SCHEDULED")
    outcome = Column(String(32), nullable=True)
    findings_json = Column(JSONB, nullable=False, default=list)
    actions_json = Column(JSONB, nullable=False, default=list)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DocumentControlledCopy(Base):
    __tablename__ = "document_controlled_copies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "manual_id", "copy_number", name="uq_document_copy_tenant_manual_number"),
        Index("ix_document_copies_tenant_status", "tenant_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False)
    copy_number = Column(String(64), nullable=False)
    format = Column(String(16), nullable=False, default="HARDCOPY")
    holder_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    holder_name = Column(String(255), nullable=True)
    location_text = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="ISSUED")
    issued_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    issued_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_back_at = Column(DateTime(timezone=True), nullable=True)
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)


class DocumentControlledCopyEvent(Base):
    __tablename__ = "document_controlled_copy_events"
    __table_args__ = (
        Index("ix_document_copy_events_copy", "controlled_copy_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    controlled_copy_id = Column(String(36), ForeignKey("document_controlled_copies.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(32), nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    from_holder_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    to_holder_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    from_location = Column(String(255), nullable=True)
    to_location = Column(String(255), nullable=True)
    reason = Column(Text, nullable=True)
    evidence_json = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ExternalDocumentSource(Base):
    __tablename__ = "external_document_sources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "manual_id", name="uq_external_document_source_tenant_manual"),
        Index("ix_external_document_sources_tenant_status", "tenant_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(255), nullable=False)
    authority = Column(String(255), nullable=True)
    subscription_reference = Column(String(255), nullable=True)
    access_url = Column(Text, nullable=True)
    update_method = Column(String(32), nullable=False, default="MANUAL_CHECK")
    status = Column(String(32), nullable=False, default="ACTIVE")
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    next_check_due_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class ExternalRevisionReceipt(Base):
    __tablename__ = "external_revision_receipts"
    __table_args__ = (
        Index("ix_external_revision_receipts_source_received", "source_id", "received_at"),
        Index("ix_external_revision_receipts_tenant_currency", "tenant_id", "currency_status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(String(36), ForeignKey("external_document_sources.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_label = Column(String(128), nullable=False)
    publication_date = Column(Date, nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    received_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    checksum_sha256 = Column(String(64), nullable=True)
    currency_status = Column(String(32), nullable=False, default="UNVERIFIED")
    applicability_status = Column(String(32), nullable=False, default="PENDING")
    evidence_json = Column(JSONB, nullable=False, default=list)
    notes = Column(Text, nullable=True)


class DocumentApplicabilityRule(Base):
    __tablename__ = "document_applicability_rules"
    __table_args__ = (
        Index("ix_document_applicability_manual_status", "manual_id", "status"),
        Index("ix_document_applicability_target", "target_type", "target_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="SET NULL"), nullable=True)
    rule_type = Column(String(32), nullable=False, default="INCLUDE")
    target_type = Column(String(64), nullable=False)
    target_id = Column(String(128), nullable=True)
    target_value = Column(String(255), nullable=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    status = Column(String(32), nullable=False, default="ACTIVE")
    source = Column(String(64), nullable=False, default="MANUAL")
    criteria_json = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DocumentIntegrationLink(Base):
    __tablename__ = "document_integration_links"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "manual_id",
            "source_module",
            "entity_type",
            "entity_id",
            "relation_type",
            name="uq_document_integration_link_identity",
        ),
        Index("ix_document_integration_links_manual", "manual_id", "source_module"),
        Index("ix_document_integration_links_source", "source_module", "entity_type", "entity_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="SET NULL"), nullable=True)
    change_request_id = Column(String(36), ForeignKey("document_change_requests.id", ondelete="SET NULL"), nullable=True)
    workflow_id = Column(String(36), ForeignKey("document_workflow_instances.id", ondelete="SET NULL"), nullable=True)
    source_module = Column(String(64), nullable=False)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(128), nullable=False)
    relation_type = Column(String(64), nullable=False)
    blocking = Column(Boolean, nullable=False, default=False)
    status_snapshot = Column(String(64), nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
