from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditChecklistExecutionGovernance(Base):
    """Governance metadata for the authoritative legacy checklist execution row.

    The existing ``quality_audit_checklist_items`` row remains the execution record.
    This one-to-one record adds the canonical MD response vocabulary, auditor notes,
    structured evidence references and attributable change history without creating a
    second checklist engine or rewriting historical ``NON_CONFORMING`` values.
    """

    __tablename__ = "quality_audit_checklist_execution_governance"
    __table_args__ = (
        UniqueConstraint("amo_id", "checklist_item_id", name="uq_quality_checklist_execution_item"),
        CheckConstraint(
            "canonical_response_status IN ('COMPLIANT','NONCOMPLIANT','OBSERVATION','NOT_APPLICABLE','NOT_VERIFIED')",
            name="ck_quality_checklist_execution_canonical_status",
        ),
        Index("ix_quality_checklist_execution_audit", "amo_id", "audit_id", "canonical_response_status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    checklist_item_id = Column(Uuid(as_uuid=True), ForeignKey("quality_audit_checklist_items.id", ondelete="CASCADE"), nullable=False)
    canonical_response_status = Column(String(24), nullable=False, default="NOT_VERIFIED", server_default="NOT_VERIFIED")
    auditor_notes = Column(Text, nullable=True)
    evidence_references = Column(JSON, nullable=False, default=list)
    entity_version = Column(Integer, nullable=False, default=1, server_default="1")
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
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
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
