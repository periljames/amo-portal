from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from amodb.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditDocumentRequestMetadata(Base):
    __tablename__ = "quality_audit_document_request_metadata"

    request_id = Column(UUID(as_uuid=True), ForeignKey("quality_audit_document_requests.id", ondelete="CASCADE"), primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    audit_id = Column(UUID(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False, index=True)
    request_type = Column(String(64), nullable=False, default="DOCUMENT")
    linked_criterion = Column(Text, nullable=True)
    is_required = Column(Boolean, nullable=False, default=True)
    source_mode = Column(String(32), nullable=False, default="UPLOAD_OR_CONTROLLED")
    controlled_document_id = Column(UUID(as_uuid=True), ForeignKey("qms_documents.id", ondelete="SET NULL"), nullable=True, index=True)
    controlled_revision_id = Column(UUID(as_uuid=True), ForeignKey("qms_document_revisions.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (Index("ix_quality_audit_doc_meta_audit", "amo_id", "audit_id"),)


class QualityAuditControlledDocumentSubmission(Base):
    __tablename__ = "quality_audit_controlled_document_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    audit_id = Column(UUID(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False, index=True)
    request_id = Column(UUID(as_uuid=True), ForeignKey("quality_audit_document_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    participant_id = Column(String(36), ForeignKey("quality_audit_participants.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("qms_documents.id", ondelete="RESTRICT"), nullable=False)
    revision_id = Column(UUID(as_uuid=True), ForeignKey("qms_document_revisions.id", ondelete="RESTRICT"), nullable=True)
    response_comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (Index("ix_quality_audit_controlled_link_request", "amo_id", "audit_id", "request_id", "created_at"),)


class QualityAuditMeeting(Base):
    __tablename__ = "quality_audit_meetings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    audit_id = Column(UUID(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False, index=True)
    meeting_type = Column(String(24), nullable=False)
    scheduled_start = Column(DateTime(timezone=True), nullable=False, index=True)
    scheduled_end = Column(DateTime(timezone=True), nullable=True)
    location = Column(String(255), nullable=True)
    conference_url = Column(String(1024), nullable=True)
    agenda = Column(Text, nullable=True)
    status = Column(String(24), nullable=False, default="PLANNED", index=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (Index("ix_quality_audit_meeting_audit", "amo_id", "audit_id", "scheduled_start"),)


class QualityAuditClosingNarrative(Base):
    __tablename__ = "quality_audit_closing_narratives"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    audit_id = Column(UUID(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False, index=True)
    conclusion = Column(Text, nullable=True)
    positive_practices = Column(Text, nullable=True)
    management_summary = Column(Text, nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("amo_id", "audit_id", name="uq_quality_audit_closing_narrative"),
        Index("ix_quality_audit_closing_narrative_audit", "amo_id", "audit_id"),
    )


class QualityAuditAssignmentDecision(Base):
    """Immutable governance record for a change to an audit's internal team.

    The occurrence itself remains authoritative for the current assignees. This
    record preserves the reason, before/after state and exact eligibility result
    that justified each assignment mutation.
    """

    __tablename__ = "quality_audit_assignment_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    audit_id = Column(UUID(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    before_snapshot = Column(JSON, nullable=False)
    after_snapshot = Column(JSON, nullable=False)
    eligibility_snapshot = Column(JSON, nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_quality_audit_assignment_decision", "amo_id", "audit_id", "created_at"),
    )
