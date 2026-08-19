from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditExternalFindingDraft(Base):
    __tablename__ = "quality_audit_external_finding_drafts"
    __table_args__ = (
        UniqueConstraint("amo_id", "client_mutation_id", name="uq_quality_external_finding_draft_mutation"),
        CheckConstraint("draft_type IN ('NON_CONFORMITY','OBSERVATION')", name="ck_quality_external_finding_draft_type"),
        CheckConstraint("proposed_severity IN ('MINOR','MAJOR','CRITICAL')", name="ck_quality_external_finding_draft_severity"),
        CheckConstraint("proposed_level IN ('LEVEL_1','LEVEL_2','LEVEL_3','LEVEL_4')", name="ck_quality_external_finding_draft_level"),
        CheckConstraint("device_sequence >= 0", name="ck_quality_external_finding_draft_device_sequence"),
        Index("ix_quality_external_finding_draft_audit", "amo_id", "audit_id", "checklist_item_id", "participant_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    checklist_item_id = Column(Uuid(as_uuid=True), ForeignKey("quality_audit_checklist_items.id", ondelete="CASCADE"), nullable=False)
    participant_id = Column(String(36), ForeignKey("quality_audit_participants.id", ondelete="CASCADE"), nullable=False)
    client_mutation_id = Column(String(128), nullable=False)
    device_id = Column(String(128), nullable=False)
    device_sequence = Column(BigInteger, nullable=False)
    client_timestamp = Column(DateTime(timezone=True), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    draft_type = Column(String(24), nullable=False)
    proposed_severity = Column(String(16), nullable=False)
    proposed_level = Column(String(16), nullable=False)
    requirement_ref = Column(String(255), nullable=True)
    description = Column(Text, nullable=False)
    objective_evidence = Column(Text, nullable=True)
    evidence_references = Column(JSON, nullable=False, default=list)
    supersedes_draft_id = Column(String(36), ForeignKey("quality_audit_external_finding_drafts.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    events = relationship(
        "QualityAuditExternalFindingDraftEvent",
        back_populates="draft",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QualityAuditExternalFindingDraftEvent.created_at",
        lazy="selectin",
    )


class QualityAuditExternalFindingDraftEvent(Base):
    __tablename__ = "quality_audit_external_finding_draft_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('CREATED','SUBMITTED','RETURNED','PROMOTED','WITHDRAWN')", name="ck_quality_external_finding_draft_event_type"),
        CheckConstraint("NOT (actor_user_id IS NOT NULL AND actor_participant_id IS NOT NULL)", name="ck_quality_external_finding_draft_single_actor"),
        Index("ix_quality_external_finding_draft_events", "amo_id", "audit_id", "draft_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    draft_id = Column(String(36), ForeignKey("quality_audit_external_finding_drafts.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(24), nullable=False)
    reason = Column(Text, nullable=False)
    review_note = Column(Text, nullable=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_participant_id = Column(String(36), ForeignKey("quality_audit_participants.id", ondelete="SET NULL"), nullable=True)
    promoted_finding_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audit_findings.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    draft = relationship("QualityAuditExternalFindingDraft", back_populates="events", lazy="joined")
