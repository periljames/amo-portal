from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditChecklistExecutionGovernance(Base):
    """Governance metadata for the authoritative legacy checklist execution row."""

    __tablename__ = "quality_audit_checklist_execution_governance"
    __table_args__ = (
        UniqueConstraint("amo_id", "checklist_item_id", name="uq_quality_checklist_execution_item"),
        CheckConstraint(
            "canonical_response_status IN ('COMPLIANT','NONCOMPLIANT','OBSERVATION','NOT_APPLICABLE','NOT_VERIFIED')",
            name="ck_quality_checklist_execution_canonical_status",
        ),
        CheckConstraint(
            "assessment_applicability IN ('APPLICABLE','NOT_APPLICABLE','UNVERIFIED')",
            name="ck_quality_checklist_execution_assessment_applicability",
        ),
        CheckConstraint(
            "documentary_status IN ('DOCUMENTED','NOT_DOCUMENTED','PARTIALLY_DOCUMENTED','CONFLICT','NOT_EVIDENCED','UNVERIFIED')",
            name="ck_quality_checklist_execution_documentary_status",
        ),
        CheckConstraint(
            "implementation_status IN ('OBJECTIVE_EVIDENCE_AVAILABLE','VERIFIED','NOT_VERIFIED','NOT_EVIDENCED','UNVERIFIED')",
            name="ck_quality_checklist_execution_implementation_status",
        ),
        CheckConstraint(
            "field_verification_status IN ('FIELD_VERIFICATION_REQUIRED','VERIFIED','NOT_VERIFIED','NOT_APPLICABLE','UNVERIFIED')",
            name="ck_quality_checklist_execution_field_status",
        ),
        Index("ix_quality_checklist_execution_audit", "amo_id", "audit_id", "canonical_response_status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    checklist_item_id = Column(Uuid(as_uuid=True), ForeignKey("quality_audit_checklist_items.id", ondelete="CASCADE"), nullable=False)
    canonical_response_status = Column(String(24), nullable=False, default="NOT_VERIFIED", server_default="NOT_VERIFIED")
    response_value = Column(String(64), nullable=True)
    auditor_notes = Column(Text, nullable=True)
    auditee_comments = Column(Text, nullable=True)
    sampled_item_information = Column(Text, nullable=True)
    applicability = Column(String(128), nullable=False, default="APPLICABLE", server_default="APPLICABLE")
    evidence_references = Column(JSON, nullable=False, default=list)
    assessment_applicability = Column(String(24), nullable=False, default="UNVERIFIED", server_default="UNVERIFIED")
    documentary_status = Column(String(32), nullable=False, default="UNVERIFIED", server_default="UNVERIFIED")
    implementation_status = Column(String(32), nullable=False, default="UNVERIFIED", server_default="UNVERIFIED")
    field_verification_status = Column(String(32), nullable=False, default="UNVERIFIED", server_default="UNVERIFIED")
    applicability_reason = Column(Text, nullable=True)
    applicability_basis = Column(JSON, nullable=False, default=list)
    evidence_ids = Column(JSON, nullable=False, default=list)
    document_revision_ids = Column(JSON, nullable=False, default=list)
    regulation_refs = Column(JSON, nullable=False, default=list)
    procedure_refs = Column(JSON, nullable=False, default=list)
    conflicts = Column(JSON, nullable=False, default=list)
    missing_evidence = Column(JSON, nullable=False, default=list)
    fieldwork_requirements = Column(JSON, nullable=False, default=list)
    ai_analysis = Column(JSON, nullable=True)
    human_decision = Column(String(24), nullable=True)
    human_override_reason = Column(Text, nullable=True)
    entity_version = Column(Integer, nullable=False, default=1, server_default="1")
    answered_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    answered_at = Column(DateTime(timezone=True), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_participant_id = Column(String(36), ForeignKey("quality_audit_participants.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    events = relationship(
        "QualityAuditChecklistExecutionEvent",
        back_populates="governance",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QualityAuditChecklistExecutionEvent.created_at",
        lazy="selectin",
    )


class QualityAuditChecklistExecutionEvent(Base):
    __tablename__ = "quality_audit_checklist_execution_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('CREATED','UPDATED')", name="ck_quality_checklist_execution_event_type"),
        Index("ix_quality_checklist_execution_events", "amo_id", "audit_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    checklist_item_id = Column(Uuid(as_uuid=True), ForeignKey("quality_audit_checklist_items.id", ondelete="CASCADE"), nullable=False)
    governance_id = Column(String(36), ForeignKey("quality_audit_checklist_execution_governance.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(16), nullable=False)
    reason = Column(Text, nullable=False)
    before_snapshot = Column(JSON, nullable=True)
    after_snapshot = Column(JSON, nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_participant_id = Column(String(36), ForeignKey("quality_audit_participants.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    governance = relationship("QualityAuditChecklistExecutionGovernance", back_populates="events", lazy="joined")


class QualityAuditFieldworkMutationReceipt(Base):
    """Append-only receipt for offline-safe, idempotent fieldwork writes."""

    __tablename__ = "quality_audit_fieldwork_mutation_receipts"
    __table_args__ = (
        UniqueConstraint("amo_id", "client_mutation_id", name="uq_quality_fieldwork_client_mutation"),
        CheckConstraint("base_version >= 0", name="ck_quality_fieldwork_base_version"),
        CheckConstraint("committed_version >= 1", name="ck_quality_fieldwork_committed_version"),
        CheckConstraint("device_sequence >= 0", name="ck_quality_fieldwork_device_sequence"),
        CheckConstraint("NOT (actor_user_id IS NOT NULL AND actor_participant_id IS NOT NULL)", name="ck_quality_fieldwork_single_actor"),
        Index("ix_quality_fieldwork_receipt_audit_item", "amo_id", "audit_id", "checklist_item_id", "created_at"),
        Index("ix_quality_fieldwork_receipt_device", "amo_id", "device_id", "device_sequence"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    checklist_item_id = Column(Uuid(as_uuid=True), ForeignKey("quality_audit_checklist_items.id", ondelete="CASCADE"), nullable=False)
    client_mutation_id = Column(String(128), nullable=False)
    device_id = Column(String(128), nullable=False)
    device_sequence = Column(BigInteger, nullable=False)
    client_timestamp = Column(DateTime(timezone=True), nullable=False)
    base_version = Column(Integer, nullable=False)
    committed_version = Column(Integer, nullable=False)
    operation = Column(String(48), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    result_snapshot = Column(JSON, nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_participant_id = Column(String(36), ForeignKey("quality_audit_participants.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class QualityAuditApplicabilityFact(Base):
    """Audit-scoped snapshot of a governed DMS applicability target selected for evaluation."""

    __tablename__ = "quality_audit_applicability_facts"
    __table_args__ = (
        UniqueConstraint("amo_id", "audit_id", "applicability_rule_id", name="uq_quality_audit_applicability_fact_rule"),
        CheckConstraint("rule_type IN ('INCLUDE','EXCLUDE','WARNING')", name="ck_quality_audit_applicability_fact_rule_type"),
        Index("ix_quality_audit_applicability_fact_audit", "amo_id", "audit_id", "target_type"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    applicability_rule_id = Column(String(36), ForeignKey("document_applicability_rules.id", ondelete="RESTRICT"), nullable=False)
    source_manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="RESTRICT"), nullable=False)
    source_revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="RESTRICT"), nullable=True)
    rule_type = Column(String(16), nullable=False)
    target_type = Column(String(64), nullable=False)
    target_id = Column(String(128), nullable=True)
    target_value = Column(String(255), nullable=True)
    source = Column(String(64), nullable=False)
    criteria_json = Column(JSON, nullable=False, default=dict)
    reason = Column(Text, nullable=False)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class QualityAuditFieldworkParticipantContribution(Base):
    """Append-only external-auditor notes/evidence attached to a governed item."""

    __tablename__ = "quality_audit_fieldwork_participant_contributions"
    __table_args__ = (
        UniqueConstraint("amo_id", "client_mutation_id", name="uq_quality_fieldwork_participant_contribution_mutation"),
        CheckConstraint(
            "canonical_response_status IN ('COMPLIANT','NONCOMPLIANT','OBSERVATION','NOT_APPLICABLE','NOT_VERIFIED')",
            name="ck_quality_fieldwork_participant_response_status",
        ),
        Index(
            "ix_quality_fieldwork_participant_contribution_item",
            "amo_id", "audit_id", "checklist_item_id", "participant_id", "created_at",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    checklist_item_id = Column(Uuid(as_uuid=True), ForeignKey("quality_audit_checklist_items.id", ondelete="CASCADE"), nullable=False)
    participant_id = Column(String(36), ForeignKey("quality_audit_participants.id", ondelete="CASCADE"), nullable=False)
    client_mutation_id = Column(String(128), nullable=False)
    canonical_response_status = Column(String(24), nullable=False)
    response_value = Column(String(64), nullable=True)
    auditor_notes = Column(Text, nullable=True)
    evidence_references = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
