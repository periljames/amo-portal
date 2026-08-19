from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, JSON, LargeBinary, String, Text, UniqueConstraint, Uuid

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditWebAuthnCredential(Base):
    __tablename__ = "quality_audit_webauthn_credentials"
    __table_args__ = (
        UniqueConstraint("amo_id", "credential_id", name="uq_quality_audit_webauthn_credential"),
        CheckConstraint("owner_type IN ('INTERNAL_USER','EXTERNAL_IDENTITY')", name="ck_quality_audit_webauthn_owner_type"),
        CheckConstraint(
            "(owner_type = 'INTERNAL_USER' AND user_id IS NOT NULL AND external_identity_id IS NULL) OR "
            "(owner_type = 'EXTERNAL_IDENTITY' AND user_id IS NULL AND external_identity_id IS NOT NULL)",
            name="ck_quality_audit_webauthn_owner_identity",
        ),
        Index(
            "ix_quality_audit_webauthn_credentials_owner",
            "amo_id", "owner_type", "user_id", "external_identity_id", "is_active",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    owner_type = Column(String(24), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    external_identity_id = Column(String(36), ForeignKey("quality_external_identities.id", ondelete="CASCADE"), nullable=True)
    credential_id = Column(LargeBinary, nullable=False)
    public_key = Column(LargeBinary, nullable=False)
    sign_count = Column(BigInteger, nullable=False, default=0, server_default="0")
    transports = Column(JSON, nullable=False, default=list)
    nickname = Column(String(80), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    last_used_at = Column(DateTime(timezone=True), nullable=True)


class QualityAuditWebAuthnChallenge(Base):
    __tablename__ = "quality_audit_webauthn_challenges"
    __table_args__ = (
        CheckConstraint("owner_type IN ('INTERNAL_USER','EXTERNAL_IDENTITY')", name="ck_quality_audit_webauthn_challenge_owner_type"),
        CheckConstraint(
            "challenge_type IN ('REGISTRATION','REPORT_SIGNATURE','EXTERNAL_ASSERTION')",
            name="ck_quality_audit_webauthn_challenge_type",
        ),
        CheckConstraint(
            "(owner_type = 'INTERNAL_USER' AND user_id IS NOT NULL AND external_identity_id IS NULL) OR "
            "(owner_type = 'EXTERNAL_IDENTITY' AND user_id IS NULL AND external_identity_id IS NOT NULL)",
            name="ck_quality_audit_webauthn_challenge_identity",
        ),
        Index(
            "ix_quality_audit_webauthn_challenge_active",
            "amo_id", "owner_type", "user_id", "external_identity_id", "challenge_type", "expires_at",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    owner_type = Column(String(24), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    external_identity_id = Column(String(36), ForeignKey("quality_external_identities.id", ondelete="CASCADE"), nullable=True)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=True)
    report_revision_id = Column(String(36), ForeignKey("quality_audit_report_revisions.id", ondelete="CASCADE"), nullable=True)
    challenge_type = Column(String(32), nullable=False)
    challenge_b64 = Column(String(256), nullable=False)
    challenge_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class QualityAuditClosingAcknowledgement(Base):
    __tablename__ = "quality_audit_closing_acknowledgements"
    __table_args__ = (
        CheckConstraint(
            "acknowledgement_status IN ('ACKNOWLEDGED','COMMENTED','DECLINED_TO_ACKNOWLEDGE')",
            name="ck_quality_audit_closing_ack_status",
        ),
        Index(
            "ix_quality_audit_closing_ack_report",
            "amo_id", "audit_id", "report_revision_id", "created_at",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    participant_id = Column(String(36), ForeignKey("quality_audit_participants.id", ondelete="RESTRICT"), nullable=False)
    grant_id = Column(String(36), ForeignKey("quality_audit_access_grants.id", ondelete="RESTRICT"), nullable=False)
    report_revision_id = Column(String(36), ForeignKey("quality_audit_report_revisions.id", ondelete="RESTRICT"), nullable=False)
    report_sha256 = Column(String(64), nullable=False)
    acknowledgement_status = Column(String(32), nullable=False)
    comments = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class QualityAuditVerificationToken(Base):
    __tablename__ = "quality_audit_verification_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_quality_audit_verification_token_hash"),
        Index(
            "ix_quality_audit_verification_token_artifact",
            "amo_id", "audit_id", "report_revision_id", "expires_at",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    report_revision_id = Column(String(36), ForeignKey("quality_audit_report_revisions.id", ondelete="RESTRICT"), nullable=False)
    signature_evidence_id = Column(String(36), ForeignKey("quality_audit_signature_evidence.id", ondelete="SET NULL"), nullable=True)
    assurance_artifact_id = Column(String(36), ForeignKey("quality_audit_assurance_artifacts.id", ondelete="SET NULL"), nullable=True)
    token_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    last_verified_at = Column(DateTime(timezone=True), nullable=True)
