from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from amodb.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.utcnow()


class DocumentRetentionDisposition(Base):
    """Governed retention/disposition lifecycle for controlled DMS evidence.

    Disposition is recorded as an immutable lifecycle outcome; this table does
    not hard-delete the controlled document, revision, evidence asset, or audit
    trail that proves what was disposed and under which approval.
    """

    __tablename__ = "document_retention_dispositions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "manual_id",
            "source_type",
            "source_id",
            name="uq_document_retention_source",
        ),
        Index("ix_document_retention_tenant_status", "tenant_id", "status", "retention_until"),
        Index("ix_document_retention_manual", "tenant_id", "manual_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="SET NULL"), nullable=True)

    source_type = Column(String(32), nullable=False, default="DOCUMENT")
    source_id = Column(String(36), nullable=True)
    source_label = Column(String(255), nullable=False)
    retention_class = Column(String(64), nullable=False, default="STANDARD")
    retention_until = Column(DateTime(timezone=True), nullable=True)

    status = Column(String(32), nullable=False, default="ACTIVE")
    legal_hold = Column(Boolean, nullable=False, default=False)
    hold_reason = Column(Text, nullable=True)
    justification = Column(Text, nullable=True)
    disposition_method = Column(String(64), nullable=True)
    certificate_evidence_asset_id = Column(
        String(36),
        ForeignKey("document_evidence_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_json = Column(JSONB, nullable=False, default=dict)

    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    requested_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    disposed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    requested_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    disposed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
