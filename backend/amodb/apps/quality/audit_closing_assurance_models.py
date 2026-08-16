from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditOutputPolicyRevision(Base):
    __tablename__ = "quality_audit_output_policy_revisions"
    __table_args__ = (
        UniqueConstraint("amo_id", "revision_no", name="uq_quality_audit_output_policy_revision"),
        CheckConstraint("revision_no >= 1", name="ck_quality_audit_output_policy_revision_no"),
        CheckConstraint(
            "artifact_policy IN ('NONE','REPORT_ONLY','APPROVAL_LETTER','CERTIFICATE','ATTESTATION')",
            name="ck_quality_audit_output_policy_type",
        ),
        Index("ix_quality_audit_output_policy_latest", "amo_id", "revision_no"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    revision_no = Column(Integer, nullable=False)
    artifact_policy = Column(String(24), nullable=False)
    artifact_title = Column(String(255), nullable=True)
    artifact_statement = Column(Text, nullable=True)
    rationale = Column(Text, nullable=False)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class QualityAuditSignatureAttempt(Base):
    __tablename__ = "quality_audit_signature_attempts"
    __table_args__ = (
        CheckConstraint("method IN ('PASSWORD_REAUTH')", name="ck_quality_audit_signature_attempt_method"),
        Index("ix_quality_audit_signature_attempt_window", "amo_id", "audit_id", "signer_user_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    signer_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    method = Column(String(24), nullable=False, default="PASSWORD_REAUTH", server_default="PASSWORD_REAUTH")
    succeeded = Column(Boolean, nullable=False)
    failure_code = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class QualityAuditSignatureEvidence(Base):
    __tablename__ = "quality_audit_signature_evidence"
    __table_args__ = (
        CheckConstraint("method IN ('PASSWORD_REAUTH')", name="ck_quality_audit_signature_evidence_method"),
        CheckConstraint("purpose IN ('ISSUED_REPORT')", name="ck_quality_audit_signature_evidence_purpose"),
        Index("ix_quality_audit_signature_evidence_report", "amo_id", "audit_id", "report_revision_id", "signed_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    report_revision_id = Column(String(36), ForeignKey("quality_audit_report_revisions.id", ondelete="RESTRICT"), nullable=False)
    signer_user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    method = Column(String(24), nullable=False, default="PASSWORD_REAUTH", server_default="PASSWORD_REAUTH")
    purpose = Column(String(24), nullable=False, default="ISSUED_REPORT", server_default="ISSUED_REPORT")
    artifact_sha256 = Column(String(64), nullable=False)
    reason = Column(Text, nullable=False)
    signature_digest = Column(String(64), nullable=False)
    nonce = Column(String(64), nullable=False)
    signed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class QualityAuditAssuranceArtifact(Base):
    __tablename__ = "quality_audit_assurance_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "amo_id", "audit_id", "artifact_type", "source_report_revision_id", "signature_evidence_id",
            name="uq_quality_audit_assurance_artifact_source",
        ),
        CheckConstraint(
            "artifact_type IN ('APPROVAL_LETTER','CERTIFICATE','ATTESTATION')",
            name="ck_quality_audit_assurance_artifact_type",
        ),
        Index("ix_quality_audit_assurance_artifact_audit", "amo_id", "audit_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    output_policy_revision_id = Column(String(36), ForeignKey("quality_audit_output_policy_revisions.id", ondelete="RESTRICT"), nullable=False)
    artifact_type = Column(String(24), nullable=False)
    source_report_revision_id = Column(String(36), ForeignKey("quality_audit_report_revisions.id", ondelete="RESTRICT"), nullable=False)
    signature_evidence_id = Column(String(36), ForeignKey("quality_audit_signature_evidence.id", ondelete="RESTRICT"), nullable=False)
    file_ref = Column(String(1024), nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(128), nullable=False, default="application/pdf", server_default="application/pdf")
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
