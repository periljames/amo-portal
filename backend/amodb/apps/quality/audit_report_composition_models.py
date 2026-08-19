from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text, Uuid

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditReportArtifact(Base):
    __tablename__ = "quality_audit_report_artifacts"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_quality_audit_report_artifact_size"),
        Index("ix_quality_audit_report_artifact_audit", "amo_id", "audit_id", "created_at"),
        Index("ix_quality_audit_report_artifact_snapshot", "amo_id", "audit_id", "source_snapshot_hash"),
        Index("ix_quality_audit_report_artifact_hash", "amo_id", "sha256"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    source_snapshot_hash = Column(String(64), nullable=False)
    template_version = Column(String(64), nullable=False)
    renderer_version = Column(String(64), nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(160), nullable=False, default="application/pdf")
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    storage_ref = Column(Text, nullable=False)
    generated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
