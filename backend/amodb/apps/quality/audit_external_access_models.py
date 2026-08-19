from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityExternalIdentity(Base):
    __tablename__ = "quality_external_identities"
    __table_args__ = (
        UniqueConstraint("amo_id", "email", name="uq_quality_external_identity_email"),
        CheckConstraint("identity_status IN ('ACTIVE','REVOKED')", name="ck_quality_external_identity_status"),
        CheckConstraint("assurance_level IN ('EMAIL_LINK','MFA','PASSKEY')", name="ck_quality_external_identity_assurance"),
        Index("ix_quality_external_identity_tenant_status", "amo_id", "identity_status", "email"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(320), nullable=False)
    display_name = Column(String(255), nullable=False)
    organisation = Column(String(255), nullable=True)
    identity_status = Column(String(16), nullable=False, default="ACTIVE", server_default="ACTIVE")
    assurance_level = Column(String(24), nullable=False, default="EMAIL_LINK", server_default="EMAIL_LINK")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class QualityAuditParticipant(Base):
    __tablename__ = "quality_audit_participants"
    __table_args__ = (
        UniqueConstraint("amo_id", "audit_id", "external_identity_id", "role", name="uq_quality_audit_external_participant_role"),
        CheckConstraint("participant_type IN ('INTERNAL_USER','EXTERNAL_AUDITOR','AUDITEE_GUEST')", name="ck_quality_audit_participant_type"),
        CheckConstraint("status IN ('INVITED','ACTIVE','REVOKED','EXPIRED')", name="ck_quality_audit_participant_status"),
        CheckConstraint("(participant_type = 'INTERNAL_USER' AND user_id IS NOT NULL AND external_identity_id IS NULL) OR (participant_type <> 'INTERNAL_USER' AND user_id IS NULL AND external_identity_id IS NOT NULL)", name="ck_quality_audit_participant_identity"),
        Index("ix_quality_audit_participants_audit", "amo_id", "audit_id", "status"),
        Index("ix_quality_audit_participants_external", "amo_id", "external_identity_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    participant_type = Column(String(24), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    external_identity_id = Column(String(36), ForeignKey("quality_external_identities.id", ondelete="CASCADE"), nullable=True)
    role = Column(String(48), nullable=False)
    permissions_json = Column(JSON, nullable=False, default=list)
    status = Column(String(16), nullable=False, default="INVITED", server_default="INVITED")
    invited_at = Column(DateTime(timezone=True), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    external_identity = relationship("QualityExternalIdentity", lazy="joined")
    grants = relationship("QualityAuditAccessGrant", back_populates="participant", lazy="selectin", cascade="all, delete-orphan", passive_deletes=True)


class QualityAuditAccessGrant(Base):
    __tablename__ = "quality_audit_access_grants"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_quality_audit_access_grant_token_hash"),
        Index("ix_quality_audit_access_grant_audit", "amo_id", "audit_id", "expires_at"),
        Index("ix_quality_audit_access_grant_participant", "amo_id", "participant_id", "revoked_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    participant_id = Column(String(36), ForeignKey("quality_audit_participants.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(64), nullable=False)
    scope_json = Column(JSON, nullable=False, default=list)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    participant = relationship("QualityAuditParticipant", back_populates="grants", lazy="joined")


class QualityAuditAccessEvent(Base):
    __tablename__ = "quality_audit_access_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('CREATED','EXCHANGED','READ','ACKNOWLEDGED','REVOKED','EXPIRED')", name="ck_quality_audit_access_event_type"),
        Index("ix_quality_audit_access_events_audit", "amo_id", "audit_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    grant_id = Column(String(36), ForeignKey("quality_audit_access_grants.id", ondelete="CASCADE"), nullable=False)
    participant_id = Column(String(36), ForeignKey("quality_audit_participants.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(24), nullable=False)
    reason = Column(Text, nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class QualityAuditFindingReleaseEvent(Base):
    __tablename__ = "quality_audit_finding_release_events"
    __table_args__ = (
        CheckConstraint("action IN ('RELEASED','WITHDRAWN')", name="ck_quality_audit_finding_release_action"),
        Index("ix_quality_audit_finding_release_latest", "amo_id", "audit_id", "finding_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    finding_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audit_findings.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(16), nullable=False)
    include_objective_evidence = Column(Boolean, nullable=False, default=False, server_default="false")
    released_evidence_refs = Column(JSON, nullable=False, default=list)
    reason = Column(Text, nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
