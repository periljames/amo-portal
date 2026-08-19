from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditEvidenceArtifact(Base):
    __tablename__ = "quality_audit_evidence_artifacts"
    __table_args__ = (
        UniqueConstraint("amo_id", "client_mutation_id", name="uq_quality_audit_evidence_client_mutation"),
        CheckConstraint("source_type IN ('INTERNAL_USER','EXTERNAL_AUDITOR','AUDITEE_GUEST')", name="ck_quality_audit_evidence_source"),
        CheckConstraint("NOT (uploaded_by_user_id IS NOT NULL AND uploaded_by_participant_id IS NOT NULL)", name="ck_quality_audit_evidence_single_actor"),
        CheckConstraint("size_bytes >= 0", name="ck_quality_audit_evidence_size"),
        Index("ix_quality_audit_evidence_audit", "amo_id", "audit_id", "created_at"),
        Index("ix_quality_audit_evidence_checklist", "amo_id", "audit_id", "checklist_item_id", "created_at"),
        Index("ix_quality_audit_evidence_finding", "amo_id", "audit_id", "finding_id", "created_at"),
        Index("ix_quality_audit_evidence_sha", "amo_id", "audit_id", "sha256"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    checklist_item_id = Column(Uuid(as_uuid=True), ForeignKey("quality_audit_checklist_items.id", ondelete="SET NULL"), nullable=True)
    finding_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audit_findings.id", ondelete="SET NULL"), nullable=True)
    source_type = Column(String(24), nullable=False)
    client_mutation_id = Column(String(128), nullable=True)
    file_ref = Column(String(1024), nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(128), nullable=True)
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    uploaded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    uploaded_by_participant_id = Column(String(36), ForeignKey("quality_audit_participants.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
