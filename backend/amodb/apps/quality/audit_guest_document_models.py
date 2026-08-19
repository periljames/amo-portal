from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text, Uuid

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditDocumentSubmission(Base):
    __tablename__ = "quality_audit_document_submissions"
    __table_args__ = (
        CheckConstraint("source_type IN ('UPLOAD')", name="ck_quality_audit_document_submission_source"),
        CheckConstraint("size_bytes >= 0", name="ck_quality_audit_document_submission_size"),
        Index("ix_quality_audit_document_submission_request", "amo_id", "audit_id", "document_request_id", "created_at"),
        Index("ix_quality_audit_document_submission_hash", "amo_id", "sha256"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    document_request_id = Column(Uuid(as_uuid=True), ForeignKey("quality_audit_document_requests.id", ondelete="CASCADE"), nullable=False)
    participant_id = Column(String(36), ForeignKey("quality_audit_participants.id", ondelete="SET NULL"), nullable=True)
    source_type = Column(String(24), nullable=False, default="UPLOAD", server_default="UPLOAD")
    filename = Column(String(255), nullable=False)
    content_type = Column(String(160), nullable=True)
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    storage_ref = Column(Text, nullable=False)
    response_comment = Column(Text, nullable=True)
    submitted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
